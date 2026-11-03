import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

from scripts.validate_runtime_smoke_source import read_json, select_source, verify_bundle


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "MSG-CTF/2026_MSG_CTF"


class PublishedRuntimeSmokeTests(unittest.TestCase):
    def setUp(self):
        self.run = {"id": 100, "run_number": 5, "run_attempt": 1, "status": "completed", "conclusion": "success",
                    "path": ".github/workflows/challenge-validation.yml", "head_branch": "main", "head_sha": "a" * 40,
                    "event": "push", "repository": {"full_name": REPOSITORY}, "head_repository": {"full_name": REPOSITORY}}
        self.artifact = {"id": 200, "name": "web-test-100-1-abc123-publish-bundle", "expired": False, "size_in_bytes": 1000,
                         "workflow_run": {"id": 100, "head_sha": "a" * 40, "head_branch": "main"}}
        self.pages = [{"total_count": 1, "artifacts": [self.artifact]}]
        self.config = {"target_id": "ci-target", "instance_id": "11111111-1111-4111-8111-111111111111",
                       "team_id": "22222222-2222-4222-8222-222222222222"}
        self.bundle = {"schema_version": "2.0", "challenge_slug": "web-test", "source_ref": "refs/heads/main", "source_sha": "a" * 40,
                       "revision": 5, "registry_revision": 5, "category": "web", "scan_result": "PASS", "isolation_profile": "WEB",
                       "runtime_type": "KUBERNETES", "architecture": "AMD64", "resource_profile": {
                           "cpu_millicores": 500, "memory_mib": 512, "ephemeral_storage_mib": 1024},
                       "workload": {"containers": [{"name": "web", "image": "ghcr.io/msg-ctf/challenges/web-test/web@sha256:" + "b" * 64,
                                                   "ports": [{"port": 8080, "public": True}]}]}}

    def select(self):
        return select_source(self.run, self.pages, REPOSITORY, 100, "web-test")

    def test_valid_source_and_bundle_are_not_mutated_or_deployed(self):
        before = copy.deepcopy((self.run, self.pages, self.bundle))
        selection = self.select()
        verify_bundle(self.bundle, selection, self.config)
        self.assertEqual(selection["artifact_id"], 200)
        self.assertEqual(selection["registry_revision"], 5)
        self.assertEqual(before, (self.run, self.pages, self.bundle))

    def test_failed_running_cancelled_or_wrong_workflow_cannot_be_selected(self):
        for patch in ({"status": "in_progress"}, {"conclusion": "failure"}, {"conclusion": "cancelled"},
                      {"path": ".github/workflows/runtime-published-bundle-smoke.yml"}, {"head_branch": "feature"},
                      {"event": "pull_request"}, {"event": []}, {"head_sha": "../bad"}, {"run_number": True}, {"run_attempt": 0}):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                select_source({**self.run, **patch}, self.pages, REPOSITORY, 100, "web-test")

    def test_other_repository_or_fork_and_bad_metadata_type_are_rejected(self):
        for field in ("repository", "head_repository"):
            for value in ({"full_name": "other/repository"}, {"full_name": []}, []):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    select_source({**self.run, field: value}, self.pages, REPOSITORY, 100, "web-test")

    def test_other_slug_attempt_expired_and_unbounded_size_are_rejected(self):
        for patch in ({"name": "other-100-1-abc123-publish-bundle"}, {"name": "web-test-100-2-abc123-publish-bundle"},
                      {"name": "web-test-100-1-abc123-user-files-bundle"}, {"expired": True}, {"expired": "false"},
                      {"size_in_bytes": 17 * 1024 * 1024}, {"size_in_bytes": True}, {"id": True},
                      {"workflow_run": {"id": 101}}, {"workflow_run": {"id": 100, "head_sha": "c" * 40, "head_branch": "main"}}):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                select_source(self.run, [{"total_count": 1, "artifacts": [{**self.artifact, **patch}]}], REPOSITORY, 100, "web-test")

    def test_all_pages_are_considered_but_missing_and_duplicate_pages_are_rejected(self):
        unrelated = {**self.artifact, "id": 201, "name": "unrelated"}
        pages = [{"total_count": 2, "artifacts": [unrelated]}, {"total_count": 2, "artifacts": [self.artifact]}]
        self.assertEqual(select_source(self.run, pages, REPOSITORY, 100, "web-test")["artifact_id"], 200)
        for invalid in (pages[:1], [pages[0], pages[0]], [{"total_count": 2, "artifacts": [self.artifact, {**self.artifact, "id": 201}]}]):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                select_source(self.run, invalid, REPOSITORY, 100, "web-test")

    def test_failed_jobs_rerun_does_not_reuse_an_earlier_attempt_bundle(self):
        run = {**self.run, "run_attempt": 2}
        with self.assertRaisesRegex(ValueError, "현재 시도"):
            select_source(run, self.pages, REPOSITORY, 100, "web-test")
        current = {**self.artifact, "id": 201, "name": "web-test-100-2-abc123-publish-bundle"}
        pages = [{"total_count": 2, "artifacts": [self.artifact, current]}]
        self.assertEqual(select_source(run, pages, REPOSITORY, 100, "web-test")["artifact_id"], 201)

    def test_manifest_sha_revision_slug_ref_and_scan_gate_must_match(self):
        selection = self.select()
        for patch in ({"source_sha": "c" * 40}, {"registry_revision": 6}, {"revision": 6}, {"challenge_slug": "web-other"},
                      {"source_ref": "refs/heads/feature"}, {"scan_result": "FAIL"}, {"schema_version": "2.1"}):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                verify_bundle({**self.bundle, **patch}, selection, self.config)

    def test_koth_pwn_vm_and_multiple_containers_are_not_implicitly_approved(self):
        for patch in ({"category": "koth"}, {"category": "KOTH"}, {"category": []},
                      {"isolation_profile": "PWN"}, {"runtime_type": "VM"}, {"architecture": "ARM64"},
                      {"workload": {"containers": self.bundle["workload"]["containers"] * 2}}):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                verify_bundle({**self.bundle, **patch}, self.select(), self.config)

    def test_only_the_problem_container_ghcr_digest_is_allowed(self):
        for image in ("ghcr.io/msg-ctf/challenges/web-other/web@sha256:" + "b" * 64,
                      "ghcr.io/msg-ctf/challenges/web-test/web:latest", "example.org/image@sha256:" + "b" * 64):
            bundle = copy.deepcopy(self.bundle)
            bundle["workload"]["containers"][0]["image"] = image
            with self.subTest(image=image), self.assertRaises(ValueError):
                verify_bundle(bundle, self.select(), self.config)

    def test_private_healthcheck_ports_and_resource_validation_reuse_existing_contract(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["workload"]["containers"][0]["ports"].append({"port": 9090, "public": False})
        bundle["workload"]["healthcheck"] = {"container": "web", "port": 9090, "path": "/health"}
        verify_bundle(bundle, self.select(), self.config)
        bundle["resource_profile"]["cpu_millicores"] = 0
        with self.assertRaises(ValueError):
            verify_bundle(bundle, self.select(), self.config)

    def test_bad_json_and_symlinks_fail_without_echoing_secret_or_traceback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "run.json"
            source.write_text('{"SECRET-CONTENT": [', encoding="utf-8")
            linked = root / "linked.json"
            linked.symlink_to(source)
            with self.assertRaises(ValueError):
                read_json(linked)
            result = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/validate_runtime_smoke_source.py"), "select",
                                     "--run", str(source), "--pages", str(source), "--repository", REPOSITORY,
                                     "--run-id", "100", "--challenge-slug", "web-test", "--output", str(root / "result.json")],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn("SECRET-CONTENT", result.stdout + result.stderr)
            self.assertNotIn("Traceback", result.stderr)

    def test_cli_outputs_only_validated_selection_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.run["untrusted_extra"] = "DO-NOT-EXPORT"
            for name, value in (("run", self.run), ("pages", self.pages)):
                (root / f"{name}.json").write_text(json.dumps(value), encoding="utf-8")
            output = root / "selection.json"
            github_output = root / "github-output"
            result = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/validate_runtime_smoke_source.py"), "select",
                                     "--run", str(root / "run.json"), "--pages", str(root / "pages.json"),
                                     "--repository", REPOSITORY, "--run-id", "100", "--challenge-slug", "web-test",
                                     "--output", str(output), "--github-output", str(github_output)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), self.select())
            self.assertEqual(github_output.read_text(encoding="utf-8"), "artifact_id=200\n")
            self.assertNotIn("DO-NOT-EXPORT", output.read_text(encoding="utf-8") + result.stdout + result.stderr)

    def test_independent_workflow_never_builds_publishes_or_softens_failures(self):
        path = ROOT / ".github/workflows/published-runtime-smoke.yml"
        raw = path.read_text(encoding="utf-8")
        workflow = yaml.load(raw, Loader=yaml.BaseLoader)
        self.assertEqual(set(workflow["on"]), {"workflow_call"})
        self.assertEqual(workflow["permissions"], {"contents": "read", "actions": "read"})
        steps = workflow["jobs"]["smoke"]["steps"]
        download = next(step for step in steps if step.get("uses") == "actions/download-artifact@v4")
        self.assertIn("steps.source.outputs.artifact_id", download["with"]["artifact-ids"])
        self.assertEqual(download["with"]["merge-multiple"], "true")
        self.assertFalse(any("continue-on-error" in step for step in steps))
        self.assertNotIn("docker/build-push-action", raw)
        self.assertNotIn("packages: write", raw)
        self.assertNotIn("aws-actions", raw)
        for step in steps:
            if "run" in step:
                self.assertNotIn("${{ inputs.", step["run"])
                result = subprocess.run(["bash", "-n"], input=step["run"], text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)

    def run_approval_step(self, event, ref, confirm="true"):
        workflow = yaml.load((ROOT / ".github/workflows/published-runtime-smoke.yml").read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
        step = workflow["jobs"]["smoke"]["steps"][0]
        env = dict(os.environ, GITHUB_EVENT_NAME=event, GITHUB_REF=ref, CONFIRM_DEPLOY=confirm,
                   SOURCE_RUN_ID="100", CHALLENGE_SLUG="web-test", DEVSECOPS_REF="a" * 40)
        return subprocess.run(["bash", "-e", "-c", step["run"] + "\nprintf 'GATE_PASSED\\n'\n"],
                              env=env, text=True, capture_output=True, timeout=5)

    def test_approval_shell_rejects_non_manual_events_and_non_main_refs(self):
        events = ("workflow_dispatch", "push", "schedule", "pull_request", "workflow_call", "repository_dispatch", "")
        refs = ("refs/heads/main", "refs/heads/feature", "refs/tags/main", "")
        for event in events:
            for ref in refs:
                with self.subTest(event=event, ref=ref):
                    result = self.run_approval_step(event, ref)
                    allowed = event == "workflow_dispatch" and ref == "refs/heads/main"
                    self.assertEqual(result.returncode, 0 if allowed else 1, result.stderr)
                    self.assertEqual("GATE_PASSED" in result.stdout, allowed)
                    if not allowed:
                        self.assertIn("수동 실행" if event != "workflow_dispatch" else "main 실행", result.stderr)

    def test_approval_shell_requires_explicit_deployment_consent(self):
        for confirm in ("false", "", "True", "1"):
            with self.subTest(confirm=confirm):
                result = self.run_approval_step("workflow_dispatch", "refs/heads/main", confirm)
                self.assertEqual(result.returncode, 1)
                self.assertNotIn("GATE_PASSED", result.stdout)
                self.assertIn("승인 확인", result.stderr)

    def test_self_test_runs_when_only_the_runtime_workflow_changes(self):
        workflow = yaml.load((ROOT / ".github/workflows/pipeline-self-test.yml").read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
        for event in ("push", "pull_request"):
            with self.subTest(event=event):
                self.assertIn(".github/workflows/published-runtime-smoke.yml", workflow["on"][event]["paths"])


if __name__ == "__main__":
    unittest.main()
