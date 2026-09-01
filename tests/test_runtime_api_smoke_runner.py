import json
import copy
import socket
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from scripts.runtime_api_smoke_runner import build_create_request, run_smoke


DIGEST = "sha256:" + "a" * 64
INSTANCE_ID = "018f3f1e-21b8-7a91-a30b-63b3400fd001"
TEAM_ID = "00000000-0000-4000-8000-000000000018"
ARTIFACT = {
    "schema_version": "2.0",
    "challenge_slug": "koth-template",
    "revision": 11,
    "registry_revision": 11,
    "category": "koth",
    "runtime_type": "KUBERNETES",
    "architecture": "AMD64",
    "isolation_profile": "WEB",
    "scan_result": "PASS",
    "workload": {
        "containers": [
            {
                "name": "service",
                "image": f"ghcr.io/msg-ctf/challenges/koth-template/service@{DIGEST}",
                "ports": [
                    {"port": 8080, "public": True},
                    {"port": 9090, "public": True},
                ],
            }
        ],
        "healthcheck": {"container": "service", "port": 9090, "path": "/healthz"},
    },
    "resource_profile": {
        "cpu_millicores": 500,
        "memory_mib": 512,
        "ephemeral_storage_mib": 1024,
    },
}


class RuntimeHandler(BaseHTTPRequestHandler):
    requests = []
    create_polls = 0
    delete_polls = 0
    create_result = {
        "runtime_workload_id": "aws-k3s-001/ctf-test/challenge",
        "service_url": "http://203.0.113.10:31042",
        "endpoints": [
            {
                "container_name": "service",
                "port": 8080,
                "protocol": "HTTP",
                "service_url": "http://203.0.113.10:31042",
            }
        ],
    }
    drop_create_response_once = False
    drop_delete_response_once = False
    omit_create_operation_id_once = False
    omit_delete_operation_id_once = False
    omit_create_result_once = False
    echo_auth_error = False

    def log_message(self, _format, *_args):
        return

    def _json_body(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return None
        return json.loads(self.rfile.read(length))

    def _respond(self, status, body):
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_POST(self):
        type(self).requests.append(("POST", self.path, self.headers, self._json_body()))
        if type(self).echo_auth_error:
            self._respond(400, {"error": self.headers.get("Authorization")})
            return
        if type(self).drop_create_response_once:
            type(self).drop_create_response_once = False
            self.connection.shutdown(socket.SHUT_RDWR)
            self.connection.close()
            return
        if type(self).omit_create_operation_id_once:
            type(self).omit_create_operation_id_once = False
            self._respond(202, {"status": "QUEUED"})
            return
        self._respond(202, {"operation_id": "op-create", "status": "QUEUED"})

    def do_DELETE(self):
        type(self).requests.append(("DELETE", self.path, self.headers, self._json_body()))
        if type(self).drop_delete_response_once:
            type(self).drop_delete_response_once = False
            self.connection.shutdown(socket.SHUT_RDWR)
            self.connection.close()
            return
        if type(self).omit_delete_operation_id_once:
            type(self).omit_delete_operation_id_once = False
            self._respond(202, {"status": "QUEUED"})
            return
        self._respond(202, {"operation_id": "op-delete", "status": "QUEUED"})

    def do_GET(self):
        type(self).requests.append(("GET", self.path, self.headers, None))
        if self.path.endswith("op-create"):
            type(self).create_polls += 1
            result = type(self).create_result
            if type(self).omit_create_result_once:
                type(self).omit_create_result_once = False
                result = None
            self._respond(
                200,
                {
                    "operation_id": "op-create",
                    "status": "SUCCEEDED",
                    "result": result,
                },
            )
            return
        type(self).delete_polls += 1
        self._respond(
            200,
            {
                "operation_id": "op-delete",
                "status": "SUCCEEDED",
                "result": {
                    "runtime_workload_id": "aws-k3s-001/ctf-test/challenge",
                    "status": "SUCCESS",
                },
            },
        )


class RuntimeApiSmokeRunnerTests(unittest.TestCase):
    def start_server(self):
        RuntimeHandler.requests = []
        RuntimeHandler.create_polls = 0
        RuntimeHandler.delete_polls = 0
        RuntimeHandler.create_result = {
            "runtime_workload_id": "aws-k3s-001/ctf-test/challenge",
            "service_url": "http://203.0.113.10:31042",
            "endpoints": [
                {
                    "container_name": "service",
                    "port": 8080,
                    "protocol": "HTTP",
                    "service_url": "http://203.0.113.10:31042",
                }
            ],
        }
        RuntimeHandler.drop_create_response_once = False
        RuntimeHandler.drop_delete_response_once = False
        RuntimeHandler.omit_create_operation_id_once = False
        RuntimeHandler.omit_delete_operation_id_once = False
        RuntimeHandler.omit_create_result_once = False
        RuntimeHandler.echo_auth_error = False
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), RuntimeHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        if not hasattr(self, "server"):
            return
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def test_builds_runtime_team_multi_container_contract(self):
        request = build_create_request(
            ARTIFACT,
            target_id="aws-k3s-001",
            instance_id=INSTANCE_ID,
            team_id=TEAM_ID,
        )

        self.assertEqual(request["isolation_profile"], "WEB")
        self.assertEqual(
            request["target"],
            {"runtime_type": "KUBERNETES", "target_id": "aws-k3s-001"},
        )
        self.assertEqual(
            request["workload"],
            {
                "containers": [
                    {
                        "name": "service",
                        "image": ARTIFACT["workload"]["containers"][0]["image"],
                        "ports": [8080, 9090],
                        "expose": True,
                        "run_as_user": 10001,
                    }
                ],
                "resource_limits": ARTIFACT["resource_profile"],
            },
        )

    def test_preserves_internal_connections_in_runtime_request(self):
        artifact = copy.deepcopy(ARTIFACT)
        artifact["workload"]["containers"].append(
            {
                "name": "db",
                "image": f"ghcr.io/msg-ctf/challenges/koth-template/db@{DIGEST}",
                "ports": [{"port": 5432, "public": False}],
            }
        )
        artifact["workload"]["internal_connections"] = [
            {
                "source_container": "service",
                "destination_container": "db",
                "protocol": "TCP",
                "port": 5432,
            }
        ]

        request = build_create_request(
            artifact,
            target_id="aws-k3s-001",
            instance_id=INSTANCE_ID,
            team_id=TEAM_ID,
        )

        self.assertEqual(
            request["workload"]["internal_connections"],
            artifact["workload"]["internal_connections"],
        )

    def test_creates_polls_and_always_deletes_runtime_workload(self):
        self.start_server()
        with tempfile.TemporaryDirectory() as directory:
            token_file = Path(directory) / "service-token"
            token_file.write_text("A" * 43 + "\n", encoding="utf-8")
            result = run_smoke(
                ARTIFACT,
                api_url=f"http://127.0.0.1:{self.server.server_port}",
                token_file=token_file,
                target_id="aws-k3s-001",
                instance_id=INSTANCE_ID,
                team_id=TEAM_ID,
                poll_interval=0,
                timeout=2,
            )

        self.assertEqual(result["create_status"], "SUCCEEDED")
        self.assertEqual(result["delete_status"], "SUCCEEDED")
        self.assertEqual(result["runtime_workload_id"], "aws-k3s-001/ctf-test/challenge")
        self.assertEqual(
            [(method, path) for method, path, _headers, _body in RuntimeHandler.requests],
            [
                ("POST", "/internal/v1/instances"),
                ("GET", "/internal/v1/operations/op-create"),
                ("DELETE", f"/internal/v1/instances/{INSTANCE_ID}"),
                ("GET", "/internal/v1/operations/op-delete"),
            ],
        )
        for _method, _path, headers, _body in RuntimeHandler.requests:
            self.assertEqual(headers["Authorization"], f"Bearer {'A' * 43}")
        delete_body = RuntimeHandler.requests[2][3]
        self.assertEqual(delete_body["runtime_workload_id"], "aws-k3s-001/ctf-test/challenge")
        self.assertEqual(delete_body["delete_reason"], "ADMIN_FORCED")

    def test_reports_digest_images_and_runtime_endpoints(self):
        self.start_server()
        RuntimeHandler.create_result = {
            "runtime_workload_id": "aws-k3s-001/ctf-test/challenge",
            "service_url": "http://203.0.113.10:31042",
            "endpoints": [
                {
                    "container_name": "service",
                    "port": 8080,
                    "protocol": "HTTP",
                    "service_url": "http://203.0.113.10:31042",
                }
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            token_file = Path(directory) / "service-token"
            token_file.write_text("A" * 43, encoding="utf-8")
            result = run_smoke(
                ARTIFACT,
                api_url=f"http://127.0.0.1:{self.server.server_port}",
                token_file=token_file,
                target_id="aws-k3s-001",
                instance_id=INSTANCE_ID,
                team_id=TEAM_ID,
                poll_interval=0,
                timeout=2,
            )

        self.assertEqual(
            result["images"],
            [
                {
                    "name": "service",
                    "image": ARTIFACT["workload"]["containers"][0]["image"],
                }
            ],
        )
        self.assertEqual(result["endpoints"], RuntimeHandler.create_result["endpoints"])
        self.assertEqual(result["registry_revision"], 11)
        self.assertNotIn("A" * 43, json.dumps(result))

    def test_rejects_registry_revision_mismatch_before_runtime_request(self):
        artifact = dict(ARTIFACT, registry_revision=12)

        with self.assertRaisesRegex(ValueError, "registry_revision"):
            build_create_request(
                artifact,
                target_id="aws-k3s-001",
                instance_id=INSTANCE_ID,
                team_id=TEAM_ID,
            )

    def test_rejects_isolation_profile_mismatch_before_runtime_request(self):
        artifact = dict(ARTIFACT, isolation_profile="PWN")

        with self.assertRaisesRegex(ValueError, "isolation_profile"):
            build_create_request(
                artifact,
                target_id="aws-k3s-001",
                instance_id=INSTANCE_ID,
                team_id=TEAM_ID,
            )

    def test_reports_create_and_delete_elapsed_seconds(self):
        self.start_server()
        evidence_times = iter([10.0, 12.5, 20.0, 21.25])
        with tempfile.TemporaryDirectory() as directory:
            token_file = Path(directory) / "service-token"
            token_file.write_text("A" * 43, encoding="utf-8")
            result = run_smoke(
                ARTIFACT,
                api_url=f"http://127.0.0.1:{self.server.server_port}",
                token_file=token_file,
                target_id="aws-k3s-001",
                instance_id=INSTANCE_ID,
                team_id=TEAM_ID,
                poll_interval=0,
                timeout=2,
                evidence_clock=lambda: next(evidence_times),
            )

        self.assertEqual(result["create_elapsed_seconds"], 2.5)
        self.assertEqual(result["delete_elapsed_seconds"], 1.25)

    def test_rejects_success_without_endpoints_after_cleanup(self):
        self.start_server()
        RuntimeHandler.create_result = {
            "runtime_workload_id": "aws-k3s-001/ctf-test/challenge",
            "service_url": None,
            "endpoints": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            token_file = Path(directory) / "service-token"
            token_file.write_text("A" * 43, encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "endpoints"):
                run_smoke(
                    ARTIFACT,
                    api_url=f"http://127.0.0.1:{self.server.server_port}",
                    token_file=token_file,
                    target_id="aws-k3s-001",
                    instance_id=INSTANCE_ID,
                    team_id=TEAM_ID,
                    poll_interval=0,
                    timeout=2,
                )

        methods = [(method, path) for method, path, _headers, _body in RuntimeHandler.requests]
        self.assertIn(("DELETE", f"/internal/v1/instances/{INSTANCE_ID}"), methods)

    def test_redacts_service_token_from_runtime_error_details(self):
        self.start_server()
        RuntimeHandler.echo_auth_error = True
        service_token = "A" * 43
        with tempfile.TemporaryDirectory() as directory:
            token_file = Path(directory) / "service-token"
            token_file.write_text(service_token, encoding="utf-8")
            with self.assertRaises(RuntimeError) as raised:
                run_smoke(
                    ARTIFACT,
                    api_url=f"http://127.0.0.1:{self.server.server_port}",
                    token_file=token_file,
                    target_id="aws-k3s-001",
                    instance_id=INSTANCE_ID,
                    team_id=TEAM_ID,
                    poll_interval=0,
                    timeout=2,
                )

        self.assertNotIn(service_token, str(raised.exception))
        self.assertIn("[REDACTED]", str(raised.exception))

    def test_maps_pwn_category_to_pwn_isolation_profile(self):
        artifact = dict(ARTIFACT, category="pwn", isolation_profile="PWN")

        request = build_create_request(
            artifact,
            target_id="aws-k3s-pwn-001",
            instance_id=INSTANCE_ID,
            team_id=TEAM_ID,
        )

        self.assertEqual(request["isolation_profile"], "PWN")

    def test_rejects_malformed_create_result_without_invalid_delete_request(self):
        self.start_server()
        RuntimeHandler.create_result = None
        with tempfile.TemporaryDirectory() as directory:
            token_file = Path(directory) / "service-token"
            token_file.write_text("A" * 43, encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "did not return a result"):
                run_smoke(
                    ARTIFACT,
                    api_url=f"http://127.0.0.1:{self.server.server_port}",
                    token_file=token_file,
                    target_id="aws-k3s-001",
                    instance_id=INSTANCE_ID,
                    team_id=TEAM_ID,
                    poll_interval=0,
                    timeout=0.01,
                    cleanup_timeout=0.01,
                )

        methods = [(method, path) for method, path, _headers, _body in RuntimeHandler.requests]
        self.assertNotIn(("DELETE", f"/internal/v1/instances/{INSTANCE_ID}"), methods)

    def test_recovers_timed_out_create_operation_and_deletes_workload(self):
        self.start_server()
        with tempfile.TemporaryDirectory() as directory:
            token_file = Path(directory) / "service-token"
            token_file.write_text("A" * 43, encoding="utf-8")

            result = run_smoke(
                ARTIFACT,
                api_url=f"http://127.0.0.1:{self.server.server_port}",
                token_file=token_file,
                target_id="aws-k3s-001",
                instance_id=INSTANCE_ID,
                team_id=TEAM_ID,
                poll_interval=0,
                timeout=0,
                cleanup_timeout=2,
            )

        self.assertEqual(result["create_status"], "SUCCEEDED")
        self.assertEqual(result["delete_status"], "SUCCEEDED")
        methods = [(method, path) for method, path, _headers, _body in RuntimeHandler.requests]
        self.assertIn(("GET", "/internal/v1/operations/op-create"), methods)
        self.assertIn(("DELETE", f"/internal/v1/instances/{INSTANCE_ID}"), methods)

    def test_retries_ambiguous_create_and_delete_submissions_with_same_request_ids(self):
        self.start_server()
        RuntimeHandler.drop_create_response_once = True
        RuntimeHandler.drop_delete_response_once = True
        with tempfile.TemporaryDirectory() as directory:
            token_file = Path(directory) / "service-token"
            token_file.write_text("A" * 43, encoding="utf-8")

            result = run_smoke(
                ARTIFACT,
                api_url=f"http://127.0.0.1:{self.server.server_port}",
                token_file=token_file,
                target_id="aws-k3s-001",
                instance_id=INSTANCE_ID,
                team_id=TEAM_ID,
                poll_interval=0,
                timeout=2,
                cleanup_timeout=2,
            )

        self.assertEqual(result["create_status"], "SUCCEEDED")
        self.assertEqual(result["delete_status"], "SUCCEEDED")
        create_bodies = [body for method, _path, _headers, body in RuntimeHandler.requests if method == "POST"]
        delete_bodies = [body for method, _path, _headers, body in RuntimeHandler.requests if method == "DELETE"]
        self.assertEqual(len(create_bodies), 2)
        self.assertEqual(len(delete_bodies), 2)
        self.assertEqual(create_bodies[0]["request_id"], create_bodies[1]["request_id"])
        self.assertEqual(delete_bodies[0]["request_id"], delete_bodies[1]["request_id"])

    def test_retries_missing_operation_ids_and_repolls_missing_create_result(self):
        self.start_server()
        RuntimeHandler.omit_create_operation_id_once = True
        RuntimeHandler.omit_delete_operation_id_once = True
        RuntimeHandler.omit_create_result_once = True
        with tempfile.TemporaryDirectory() as directory:
            token_file = Path(directory) / "service-token"
            token_file.write_text("A" * 43, encoding="utf-8")

            result = run_smoke(
                ARTIFACT,
                api_url=f"http://127.0.0.1:{self.server.server_port}",
                token_file=token_file,
                target_id="aws-k3s-001",
                instance_id=INSTANCE_ID,
                team_id=TEAM_ID,
                poll_interval=0,
                timeout=2,
                cleanup_timeout=2,
            )

        self.assertEqual(result["create_status"], "SUCCEEDED")
        self.assertEqual(result["delete_status"], "SUCCEEDED")
        methods = [method for method, _path, _headers, _body in RuntimeHandler.requests]
        self.assertEqual(methods.count("POST"), 2)
        self.assertEqual(methods.count("DELETE"), 2)
        self.assertGreaterEqual(RuntimeHandler.create_polls, 2)

    def test_recovers_create_submission_after_primary_deadline(self):
        self.start_server()
        RuntimeHandler.drop_create_response_once = True
        with tempfile.TemporaryDirectory() as directory:
            token_file = Path(directory) / "service-token"
            token_file.write_text("A" * 43, encoding="utf-8")

            result = run_smoke(
                ARTIFACT,
                api_url=f"http://127.0.0.1:{self.server.server_port}",
                token_file=token_file,
                target_id="aws-k3s-001",
                instance_id=INSTANCE_ID,
                team_id=TEAM_ID,
                poll_interval=0,
                timeout=0,
                cleanup_timeout=2,
            )

        self.assertTrue(result["recovered_after_timeout"])
        methods = [method for method, _path, _headers, _body in RuntimeHandler.requests]
        self.assertEqual(methods.count("POST"), 2)
        self.assertEqual(result["delete_status"], "SUCCEEDED")


if __name__ == "__main__":
    unittest.main()
