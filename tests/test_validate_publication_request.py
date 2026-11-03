import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.validate_publication_request import (
    RequestValidationError, main, validate_request,
)


class PublicationRequestTests(unittest.TestCase):
    def setUp(self):
        self.context = {
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "GITHUB_REPOSITORY": "MSG-CTF/2026_MSG_CTF",
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_SHA": "a" * 40,
            "GITHUB_WORKFLOW_SHA": "a" * 40,
            "GITHUB_RUN_ID": "123",
            "GITHUB_RUN_ATTEMPT": "1",
            "EXPECTED_SOURCE_SHA": "a" * 40,
            "SOURCE_REF": "",
            "CHALLENGE_PATH": "web-open-house",
            "PUBLICATION_REQUEST_ID": "36f71603-bfb6-4eca-b8b4-4532b7e3c07f",
        }
        self.tools_sha = "b" * 40

    def test_exact_main_request_preserves_run_and_source(self):
        result = validate_request(self.context, self.tools_sha)
        self.assertEqual(result["source_sha"], self.context["EXPECTED_SOURCE_SHA"])
        self.assertEqual(result["source_ref"], "refs/heads/main")
        self.assertEqual(result["run_id"], 123)
        self.assertEqual(result["run_attempt"], 1)
        self.assertEqual(result["devsecops_sha"], self.tools_sha)
        self.assertEqual(result["publication_status"], "NOT_YET_VERIFIED")

    def test_stale_main_is_rejected_without_switching_to_new_sha(self):
        self.context["GITHUB_SHA"] = "c" * 40
        with self.assertRaisesRegex(RequestValidationError, "SOURCE_SHA_MISMATCH"):
            validate_request(self.context, self.tools_sha)

    def test_repository_event_and_branch_are_allowlisted(self):
        for key, value in (
            ("GITHUB_REPOSITORY", "other/problems"),
            ("GITHUB_EVENT_NAME", "push"),
            ("GITHUB_EVENT_NAME", "pull_request"),
            ("GITHUB_EVENT_NAME", "schedule"),
            ("GITHUB_REF", "refs/heads/feature/test"),
            ("GITHUB_REF", "refs/tags/main"),
        ):
            with self.subTest(key=key, value=value), self.assertRaises(RequestValidationError):
                validate_request({**self.context, key: value}, self.tools_sha)

    def test_full_lowercase_commit_is_required(self):
        for value in ("", "main", "a" * 7, "A" * 40, "g" * 40, "a" * 40 + "\n"):
            with self.subTest(value=value), self.assertRaises(RequestValidationError):
                validate_request({**self.context, "EXPECTED_SOURCE_SHA": value}, self.tools_sha)

    def test_branch_source_ref_cannot_replace_pinned_publication(self):
        for value in ("feature/test", "main", "b" * 40):
            with self.subTest(value=value), self.assertRaisesRegex(RequestValidationError, "SOURCE_REF"):
                validate_request({**self.context, "SOURCE_REF": value}, self.tools_sha)
        self.assertEqual(
            validate_request({**self.context, "SOURCE_REF": "a" * 40}, self.tools_sha)["source_sha"],
            "a" * 40,
        )

    def test_challenge_is_one_canonical_slug(self):
        for value in ("", ".", "../web-test", "./web-test", "web-test/path", "/web-test", "web-test\n", "WEB-test", "web--test"):
            with self.subTest(value=value), self.assertRaises(RequestValidationError):
                validate_request({**self.context, "CHALLENGE_PATH": value}, self.tools_sha)

    def test_canonical_non_nil_request_uuid_required(self):
        for value in ("", "request-1", "../token", "00000000-0000-0000-0000-000000000000", self.context["PUBLICATION_REQUEST_ID"].upper()):
            with self.subTest(value=value), self.assertRaises(RequestValidationError):
                validate_request({**self.context, "PUBLICATION_REQUEST_ID": value}, self.tools_sha)

    def test_run_attempt_and_tools_identity_are_validated(self):
        for key in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"):
            for value in ("", "0", "-1", "1.0", "001"):
                with self.subTest(key=key, value=value), self.assertRaises(RequestValidationError):
                    validate_request({**self.context, key: value}, self.tools_sha)
        for value in ("main", "", "f" * 39):
            with self.subTest(tools=value), self.assertRaises(RequestValidationError):
                validate_request(self.context, value)

    def test_key_does_not_depend_on_delivery_id_or_attempt(self):
        first = validate_request(self.context, self.tools_sha)
        second = validate_request({**self.context, "GITHUB_RUN_ID": "124", "GITHUB_RUN_ATTEMPT": "2", "PUBLICATION_REQUEST_ID": "46f71603-bfb6-4eca-b8b4-4532b7e3c07f"}, self.tools_sha)
        self.assertEqual(first["request_key"], second["request_key"])
        self.assertNotEqual(first["run_id"], second["run_id"])

    def test_key_changes_with_problem_source_and_tools(self):
        original = validate_request(self.context, self.tools_sha)["request_key"]
        for context, tools in (
            ({**self.context, "CHALLENGE_PATH": "web-daily-point"}, self.tools_sha),
            ({**self.context, "EXPECTED_SOURCE_SHA": "c" * 40, "GITHUB_SHA": "c" * 40}, self.tools_sha),
            (self.context, "d" * 40),
        ):
            self.assertNotEqual(validate_request(context, tools)["request_key"], original)

    def test_unrelated_secret_environment_is_not_copied(self):
        result = validate_request({**self.context, "GH_TOKEN": "secret-test-value", "FLAG": "private-value"}, self.tools_sha)
        self.assertNotIn("secret-test-value", json.dumps(result))
        self.assertNotIn("private-value", json.dumps(result))
        self.assertNotIn("FLAG", result)

    def test_cli_writes_only_a_validated_receipt(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, self.context, clear=True), patch("scripts.validate_publication_request.subprocess.run") as git:
            git.return_value.stdout = self.tools_sha + "\n"
            target = Path(directory) / "request.json"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--output", str(target)]), 0)
            self.assertEqual(json.loads(target.read_text())["request_validation"], "PASS")

    def test_cli_rejects_before_creating_receipt_and_redacts_invalid_input(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {**self.context, "EXPECTED_SOURCE_SHA": "secret-test-value"}, clear=True), patch("scripts.validate_publication_request.subprocess.run") as git:
            git.return_value.stdout = self.tools_sha
            target = Path(directory) / "request.json"
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                self.assertEqual(main(["--output", str(target)]), 1)
            self.assertFalse(target.exists())
            self.assertIn("EXPECTED_SHA_REQUIRED", stderr.getvalue())
            self.assertNotIn("secret-test-value", stderr.getvalue())

    def test_existing_receipt_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, self.context, clear=True), patch("scripts.validate_publication_request.subprocess.run") as git:
            git.return_value.stdout = self.tools_sha
            target = Path(directory) / "request.json"
            target.write_text("existing", encoding="utf-8")
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["--output", str(target)]), 1)
            self.assertEqual(target.read_text(), "existing")


if __name__ == "__main__":
    unittest.main()
