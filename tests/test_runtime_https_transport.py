import io
import json
import ssl
import unittest
from urllib.error import HTTPError, URLError
from unittest.mock import Mock, patch

from scripts.runtime_api_smoke_runner import RuntimeClient, normalize_api_origin, NoRedirectHandler
from scripts.runtime_connection_probe import probe_connection


class RuntimeHttpsTransportTests(unittest.TestCase):
    def test_normalizes_gcp_origin_and_internal_prefix_without_double_path(self):
        self.assertEqual(normalize_api_origin("https://34.67.93.98:443/internal/v1/"), "https://34.67.93.98:443")
        self.assertEqual(normalize_api_origin("https://runtime.example.test"), "https://runtime.example.test")

    def test_preserves_local_http_for_existing_ssm_runner(self):
        self.assertEqual(normalize_api_origin("http://127.0.0.1:8080"), "http://127.0.0.1:8080")

    def test_rejects_unsafe_origins(self):
        for url in (
            "http://34.67.93.98:8080", "https://name:password@34.67.93.98",
            "https://34.67.93.98?token=secret", "https://34.67.93.98#fragment",
            "https://34.67.93.98/other", "https://34.67.93.98:bad",
            "https://34.67.93.98:0", "https://34.67.93.98/ internal/v1",
            "https://34.67.93.98\\other", "https:///internal/v1",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                normalize_api_origin(url)

    def test_https_client_verifies_certificate_and_hostname(self):
        client = RuntimeClient("https://34.67.93.98/internal/v1", "a" * 43, timeout=5)
        self.assertEqual(client.tls_context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(client.tls_context.check_hostname)
        self.assertTrue(any(isinstance(handler, NoRedirectHandler) for handler in client.opener.handlers))

    def test_auth_header_is_sent_to_single_internal_path(self):
        client = RuntimeClient("https://34.67.93.98/internal/v1", "a" * 43, timeout=5)
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'{"operation_id":"op-test"}'
        with patch.object(client.opener, "open", return_value=response) as opened:
            client.request("GET", "/internal/v1/operations/op-test")
        request = opened.call_args.args[0]
        self.assertEqual(request.full_url, "https://34.67.93.98/internal/v1/operations/op-test")
        self.assertEqual(request.get_header("Authorization"), "Bearer " + "a" * 43)

    def test_redirects_never_forward_service_credentials(self):
        handler = NoRedirectHandler()
        with self.assertRaises(HTTPError) as caught:
            handler.redirect_request(None, None, 302, "redirect", {}, "https://other.example.test/")
        caught.exception.close()

    def test_preflight_workflow_is_manual_read_only_and_uses_no_secrets(self):
        from pathlib import Path
        import yaml
        root = Path(__file__).resolve().parents[1]
        workflow = yaml.load((root / ".github/workflows/pipeline-self-test.yml").read_text(), Loader=yaml.BaseLoader)
        job = workflow["jobs"]["runtime-https-preflight"]
        self.assertIn("workflow_dispatch", job["if"])
        self.assertIn("check_gcp_runtime_connection", job["if"])
        self.assertEqual(job["permissions"], {"contents": "read"})
        self.assertNotIn("secrets", json.dumps(job))
        self.assertNotIn("internal_connections", json.dumps(job))

    def test_probe_accepts_only_401_and_never_sends_authorization(self):
        opener = Mock()
        opener.open.side_effect = HTTPError("https://34.67.93.98", 401, "Unauthorized", {}, io.BytesIO(b"secret response"))
        with patch("scripts.runtime_connection_probe.build_runtime_opener", return_value=(opener, ssl.create_default_context())):
            result = probe_connection("https://34.67.93.98/internal/v1")
        request = opener.open.call_args.args[0]
        self.assertIsNone(request.get_header("Authorization"))
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(result["http_status"], 401)
        self.assertFalse(result["authenticated_smoke_executed"])
        self.assertNotIn("secret response", json.dumps(result))

    def test_probe_rejects_unexpected_status_redirect_and_tls_failure(self):
        for error in (
            HTTPError("https://34.67.93.98", 302, "Redirect", {}, None),
            HTTPError("https://34.67.93.98", 403, "Forbidden", {}, None),
            URLError(ssl.SSLCertVerificationError("bad certificate")),
        ):
            opener = Mock()
            opener.open.side_effect = error
            with patch("scripts.runtime_connection_probe.build_runtime_opener", return_value=(opener, ssl.create_default_context())):
                result = probe_connection("https://34.67.93.98/internal/v1")
            self.assertEqual(result["status"], "FAILED")
            self.assertFalse(result["authenticated_smoke_executed"])

    def test_probe_does_not_mislabel_unprotected_200_as_success(self):
        opener = Mock()
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.status = 200
        opener.open.return_value = response
        with patch("scripts.runtime_connection_probe.build_runtime_opener", return_value=(opener, ssl.create_default_context())):
            self.assertEqual(probe_connection("https://34.67.93.98")["status"], "FAILED")


if __name__ == "__main__":
    unittest.main()
