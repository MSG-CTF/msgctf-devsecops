import copy
import http.client
import http.server
import io
import json
from pathlib import Path
import socket
import ssl
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from scripts import observe_rollout_http as observer
from scripts.vm_image_prefetch import save_private
from tests.test_prepare_release_transition import prepare


def public_resolver(host, port, **kwargs):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", port))]


class Clock:
    def __init__(self):
        self.value = 0

    def monotonic(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds


def observe(*, replies=None, duration_seconds=3, interval_seconds=1, request=None, **kwargs):
    clock = kwargs.pop("clock", Clock())
    replies = replies or [{"http_status": 200, "error_code": None}]
    calls = []
    def call(endpoint, timeout):
        calls.append((copy.deepcopy(endpoint), timeout, clock.value))
        clock.value += 0.1
        return copy.deepcopy(replies[min(len(calls) - 1, len(replies) - 1)])
    result = observer.observe("https://example.org/health", kwargs.pop("plan", prepare()),
        duration_seconds=duration_seconds, interval_seconds=interval_seconds,
        request=request or call, resolver=public_resolver,
        monotonic=clock.monotonic, sleep=clock.sleep, **kwargs)
    return result, calls


class RolloutHTTPTests(unittest.TestCase):
    def test_passing_samples_never_claim_zero_downtime_or_b_identity(self):
        result, calls = observe()
        self.assertEqual(result["status"], "NO_HTTP_FAILURE_OBSERVED")
        self.assertEqual(result["sample_count"], 3)
        self.assertEqual([row[2] for row in calls], [0, 1, 2])
        self.assertEqual(result["failure_count"], 0)
        self.assertTrue(all(value is False for value in result["limits"].values()))
        self.assertNotIn("example.org", json.dumps(result))
        self.assertNotIn("/health", json.dumps(result))

    def test_http_failures_are_recorded_and_observation_continues(self):
        result, _ = observe(replies=[{"http_status": 200, "error_code": None},
            {"http_status": 503, "error_code": None}, {"http_status": 200, "error_code": None}])
        self.assertEqual(result["status"], "HTTP_FAILURE_OBSERVED")
        self.assertEqual(result["sample_count"], 3)
        self.assertEqual(result["failure_count"], 1)
        self.assertFalse(result["samples"][1]["passed"])

    def test_timeout_tls_and_network_errors_are_failure_not_success(self):
        for error in ("REQUEST_TIMEOUT", "TLS_FAILURE", "NETWORK_OR_PROTOCOL_FAILURE"):
            with self.subTest(error=error):
                result, _ = observe(replies=[{"http_status": None, "error_code": error}])
                self.assertEqual(result["failure_count"], 3)
                self.assertEqual(result["status"], "HTTP_FAILURE_OBSERVED")

    def test_slow_requests_do_not_cause_catch_up_bursts(self):
        clock, starts = Clock(), []
        def slow(endpoint, timeout):
            starts.append(clock.value)
            clock.value += 2.1
            return {"http_status": 200, "error_code": None}
        result, _ = observe(clock=clock, request=slow, duration_seconds=5)
        self.assertEqual(starts, [0, 3])
        self.assertGreaterEqual(result["elapsed_seconds"], 5)
        self.assertFalse(result["limits"]["between_sample_availability_proven"])

    def test_interrupt_persists_samples_and_never_succeeds(self):
        clock, count, saved = Clock(), 0, []
        def interrupted(endpoint, timeout):
            nonlocal count
            count += 1
            if count == 2:
                raise KeyboardInterrupt()
            clock.value += 0.1
            return {"http_status": 200, "error_code": None}
        result, _ = observe(clock=clock, request=interrupted,
                            on_result=lambda value: saved.append(copy.deepcopy(value)))
        self.assertEqual(result["status"], "INTERRUPTED")
        self.assertEqual(result["sample_count"], 1)
        self.assertEqual(saved[-1]["status"], "INTERRUPTED")

    def test_unexpected_reply_is_not_copied_into_report(self):
        saved = []
        with self.assertRaises(ValueError):
            observe(replies=[{"http_status": 200, "error_code": None, "body": "private-response"}],
                    on_result=lambda value: saved.append(copy.deepcopy(value)))
        self.assertEqual(saved[-1]["status"], "OBSERVER_FAILED")
        self.assertNotIn("private-response", json.dumps(saved))

    def test_malformed_status_or_error_is_rejected(self):
        for reply in ({"http_status": True, "error_code": None},
                      {"http_status": None, "error_code": None},
                      {"http_status": 200, "error_code": "TLS_FAILURE"},
                      {"http_status": None, "error_code": "private-error-text"}):
            with self.subTest(reply=reply), self.assertRaises(ValueError):
                observe(replies=[reply])

    def test_tampered_plan_does_not_send_a_request(self):
        plan = prepare()
        plan["candidate"]["registry_revision"] += 1
        with self.assertRaises(ValueError):
            observe(plan=plan, request=lambda *_: self.fail("must not request"))

    def test_request_budget_and_invalid_numeric_limits_are_rejected(self):
        for kwargs in ({"duration_seconds": 901}, {"duration_seconds": True},
                       {"duration_seconds": 100, "interval_seconds": 0.25},
                       {"interval_seconds": float("nan")}, {"timeout_seconds": 0},
                       {"timeout_seconds": float("inf")}, {"expected_status": 302}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                observe(**kwargs)

    def test_an_explicit_204_health_endpoint_is_supported(self):
        result, _ = observe(expected_status=204, replies=[{"http_status": 204, "error_code": None}])
        self.assertEqual(result["status"], "NO_HTTP_FAILURE_OBSERVED")

    def test_https_default_and_explicit_http_only(self):
        with self.assertRaises(ValueError):
            observer.validate_endpoint("http://example.org/", resolver=public_resolver)
        target = observer.validate_endpoint("http://example.org:8080/", allow_http=True, resolver=public_resolver)
        self.assertEqual(target["scheme"], "http")
        self.assertEqual(target["port"], 8080)

    def test_credentials_queries_fragments_and_unsafe_paths_are_rejected(self):
        for url in ("https://user:password@example.org/", "https://example.org/?token=private",
                    "https://example.org/#fragment", "https://example.org/?", "https://example.org/#",
                    "https://example.org/../admin", "https://example.org//admin",
                    "https://example.org/%2e%2e/admin", "https://example.org/a\nheader",
                    "https://example.org:0/", "ftp://example.org/", "https://example.org/a b"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                observer.validate_endpoint(url, resolver=public_resolver)

    def test_all_dns_answers_must_be_public_and_metadata_is_forbidden(self):
        for address in ("127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "224.0.0.1"):
            def resolver(host, port, **kwargs):
                return public_resolver(host, port) + [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port))]
            with self.subTest(address=address), self.assertRaises(ValueError):
                observer.validate_endpoint("https://example.org/", resolver=resolver)
        for url in ("https://localhost/", "https://metadata.google.internal/", "https://service.local/"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                observer.validate_endpoint(url, resolver=public_resolver)

    def test_socket_is_pinned_and_tls_checks_original_hostname(self):
        endpoint = observer.validate_endpoint("https://example.org/", resolver=public_resolver)
        connection = observer.PinnedConnection(endpoint, 2)
        self.assertTrue(connection.context.check_hostname)
        self.assertEqual(connection.context.verify_mode, ssl.CERT_REQUIRED)
        with patch("socket.create_connection") as connect, patch.object(connection.context, "wrap_socket") as wrap:
            connection.connect()
            connect.assert_called_once_with(("8.8.8.8", 443), 2)
            wrap.assert_called_once_with(connect.return_value, server_hostname="example.org")
        connection.sock = None

    def test_tls_wrapping_failure_closes_raw_socket(self):
        endpoint = observer.validate_endpoint("https://example.org/", resolver=public_resolver)
        connection = observer.PinnedConnection(endpoint, 2)
        with patch("socket.create_connection") as connect, \
             patch.object(connection.context, "wrap_socket", side_effect=ssl.SSLError("private-detail")):
            with self.assertRaises(ssl.SSLError):
                connection.connect()
            connect.return_value.close.assert_called_once()

    def test_probe_discards_body_headers_and_does_not_follow_redirect(self):
        endpoint = observer.validate_endpoint("https://example.org/", resolver=public_resolver)
        with patch.object(observer, "PinnedConnection") as factory:
            connection = factory.return_value
            connection.getresponse.return_value.status = 302
            result = observer.probe(endpoint, 2)
            self.assertEqual(result, {"http_status": 302, "error_code": None})
            connection.request.assert_called_once()
            args, kwargs = connection.request.call_args
            self.assertEqual(args, ("GET", "/"))
            self.assertFalse({"Authorization", "Cookie", "Proxy-Authorization"}.intersection(kwargs["headers"]))
            connection.getresponse.return_value.read.assert_not_called()
            connection.getresponse.return_value.getheader.assert_not_called()
            connection.close.assert_called_once()

    def test_probe_redacts_transport_errors_and_closes_connection(self):
        endpoint = observer.validate_endpoint("https://example.org/", resolver=public_resolver)
        for error, code in ((ssl.SSLError("private-token"), "TLS_FAILURE"),
                            (TimeoutError("private-token"), "REQUEST_TIMEOUT"),
                            (http.client.BadStatusLine("private-token"), "NETWORK_OR_PROTOCOL_FAILURE")):
            with self.subTest(code=code), patch.object(observer, "PinnedConnection") as factory:
                factory.return_value.request.side_effect = error
                result = observer.probe(endpoint, 2)
                self.assertEqual(result["error_code"], code)
                self.assertNotIn("private-token", json.dumps(result))
                factory.return_value.close.assert_called_once()

    def test_private_checkpoints_do_not_contain_endpoint_or_body(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "http-observation.json"
            result, _ = observe(on_result=lambda value: save_private(target, value))
            saved = json.loads(target.read_text())
            self.assertEqual(saved, result)
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            self.assertNotIn("example.org", target.read_text())

    def test_cli_writes_private_result_without_network_or_url_output(self):
        real_observe = observer.observe
        clock = Clock()
        def fake_observe(url, plan, **kwargs):
            def request(endpoint, timeout):
                clock.value += 0.1
                return {"http_status": 200, "error_code": None}
            return real_observe(url, plan, resolver=public_resolver, request=request,
                                monotonic=clock.monotonic, sleep=clock.sleep, **kwargs)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan = root / "plan.json"
            plan.write_text(json.dumps(prepare()))
            output, stdout = root / "observation", io.StringIO()
            args = ["observe", "--plan", str(plan), "--url", "https://example.org/health",
                    "--duration-seconds", "2", "--output-dir", str(output)]
            with patch("sys.argv", args), patch.object(observer, "observe", side_effect=fake_observe), redirect_stdout(stdout):
                code = observer.main()
            self.assertEqual(code, 0)
            self.assertEqual(output.stat().st_mode & 0o777, 0o700)
            self.assertEqual((output / "http-observation.json").stat().st_mode & 0o777, 0o600)
            self.assertNotIn("example.org", stdout.getvalue())
            self.assertFalse(json.loads(stdout.getvalue())["zero_downtime_proven"])

    def test_local_transport_sends_only_get_and_does_not_use_proxy_or_redirect(self):
        seen = []
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                seen.append((self.path, dict(self.headers)))
                self.send_response(302 if self.path == "/redirect" else 200)
                self.send_header("Location", "http://127.0.0.1/should-not-follow")
                self.end_headers()

            def log_message(self, *args):
                pass
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            # Transport only: the production URL validator rejects this private address.
            endpoint = {"host": "127.0.0.1", "address": "127.0.0.1", "port": server.server_port,
                        "scheme": "http", "path": "/redirect"}
            with patch.dict("os.environ", {"HTTP_PROXY": "http://private-proxy.invalid:1"}):
                result = observer.probe(endpoint, 2)
            self.assertEqual(result["http_status"], 302)
            self.assertEqual(len(seen), 1)
            self.assertEqual(seen[0][0], "/redirect")
            self.assertNotIn("Authorization", seen[0][1])
            self.assertNotIn("Cookie", seen[0][1])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
