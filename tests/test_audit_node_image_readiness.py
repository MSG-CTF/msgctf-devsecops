import copy
import hashlib
import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest

from scripts.audit_node_image_readiness import (
    audit_readiness, calculate_image_set_id, write_audit,
)
from tests.test_generate_node_image_plan import sample_artifact


ROOT = Path(__file__).resolve().parents[1]
AS_OF = "2026-10-30T00:00:30Z"
ARTIFACT_SHA = "c" * 64


def sample_response(artifact=None):
    artifact = artifact or sample_artifact()
    images = [item["image"] for item in artifact["workload"]["containers"]]
    return {
        "image_set_id": calculate_image_set_id(artifact["architecture"], images),
        "architecture": artifact["architecture"],
        "targets": [{
            "target_id": "target-a", "ready": True,
            "ready_node_count": 1, "eligible_node_count": 1,
            "observed_at": "2026-10-30T00:00:00Z",
            "valid_until": "2026-10-30T00:02:00Z",
        }],
    }


def audit(response=None, artifact=None, targets=None, **kwargs):
    artifact = artifact or sample_artifact()
    return audit_readiness(
        artifact, ARTIFACT_SHA, response if response is not None else sample_response(artifact),
        ["target-a"] if targets is None else targets,
        as_of=kwargs.pop("as_of", AS_OF), **kwargs,
    )


class NodeReadinessAuditTests(unittest.TestCase):
    def test_canonical_identity_matches_runtime_published_example(self):
        images = [
            "ghcr.io/msg-ctf/challenges/example/web@sha256:" + "a" * 64,
            "ghcr.io/msg-ctf/challenges/example/db@sha256:" + "b" * 64,
        ]
        expected = "sha256:a96c344635195e2a40715531e3d420180ab28ce838ab88130364ad51bbb7c4c1"
        self.assertEqual(calculate_image_set_id("AMD64", images), expected)
        self.assertEqual(calculate_image_set_id("AMD64", images[::-1] + images), expected)
        self.assertNotEqual(calculate_image_set_id("ARM64", images), expected)

    def test_runtime_example_has_partial_coverage_and_a_missing_target(self):
        fixtures = ROOT / "tests/fixtures/runtime-readiness"
        query = json.loads((fixtures / "query.json").read_text())
        response = json.loads((fixtures / "response.json").read_text())
        artifact = sample_artifact()
        artifact["challenge_slug"] = "example"
        for container in artifact["workload"]["containers"]:
            container["image"] = container["image"].replace("/web-notebook/", "/example/")
        for entry in artifact["evidence"]["containers"]:
            entry["published_image"] = entry["published_image"].replace("/web-notebook/", "/example/")
        self.assertEqual(
            calculate_image_set_id(query["architecture"], query["images"]),
            response["image_set_id"],
        )
        report = audit_readiness(
            artifact, ARTIFACT_SHA, response, query["target_ids"],
            as_of="2026-10-24T00:00:30Z",
        )
        self.assertEqual(report["status"], "PARTIAL")
        self.assertEqual([entry["state"] for entry in report["targets"]],
                         ["SOME_NODES_READY", "NOT_READY", "UNKNOWN"])
        self.assertFalse(report["all_reported_eligible_nodes_ready"])

        expired = audit_readiness(
            artifact, ARTIFACT_SHA, response, query["target_ids"],
            as_of="2026-10-30T00:00:00Z",
        )
        self.assertEqual(expired["status"], "UNKNOWN")
        self.assertEqual(expired["counts"]["fresh_targets"], 0)

    def test_complete_fresh_image_set_and_no_input_mutation(self):
        artifact, response = sample_artifact(), sample_response()
        originals = copy.deepcopy((artifact, response))
        report = audit(response, artifact)
        self.assertEqual((artifact, response), originals)
        self.assertEqual(report["status"], "ALL_ELIGIBLE_READY")
        self.assertTrue(report["all_reported_eligible_nodes_ready"])
        self.assertEqual(report["bundle"]["container_count"], 2)
        self.assertEqual(report["bundle"]["artifact_sha256"], ARTIFACT_SHA)
        self.assertTrue(report["all_requested_targets_have_ready_hint"])
        self.assertTrue(all(value is False for value in report["limits"].values()))

    def test_true_ready_with_partial_node_coverage_is_not_complete(self):
        response = sample_response()
        response["targets"][0]["eligible_node_count"] = 2
        report = audit(response)
        self.assertEqual(report["status"], "PARTIAL")
        self.assertTrue(report["all_requested_targets_have_ready_hint"])
        self.assertFalse(report["all_reported_eligible_nodes_ready"])
        self.assertEqual(report["counts"]["ready_nodes_in_fresh_reports"], 1)
        self.assertEqual(report["counts"]["eligible_nodes_in_fresh_reports"], 2)

    def test_missing_target_is_not_assumed_ready(self):
        report = audit(targets=["target-a", "target-b"])
        self.assertEqual(report["status"], "PARTIAL")
        self.assertEqual(report["targets"][1]["reason"], "MISSING_TARGET")
        self.assertFalse(report["all_requested_targets_have_ready_hint"])

    def test_all_missing_targets_are_unknown_not_zero_real_nodes(self):
        response = sample_response()
        response["targets"] = []
        report = audit(response)
        self.assertEqual(report["status"], "UNKNOWN")
        self.assertEqual(report["counts"]["unknown_targets"], 1)
        self.assertIsNone(report["targets"][0]["eligible_node_count_as_reported"])

    def test_multiple_targets_are_checked_in_requested_order(self):
        response = sample_response()
        other = dict(response["targets"][0], target_id="target-b")
        response["targets"].insert(0, other)
        report = audit(response, targets=["target-a", "target-b"])
        self.assertEqual([item["target_id"] for item in report["targets"]], ["target-a", "target-b"])
        self.assertEqual(report["status"], "ALL_ELIGIBLE_READY")
        self.assertEqual(report["counts"]["ready_nodes_in_fresh_reports"], 2)

    def test_unobserved_and_absent_timestamps_are_unknown(self):
        for change in (
            {"ready": False, "ready_node_count": 0, "eligible_node_count": 0,
             "observed_at": None, "valid_until": None},
            {"observed_at": None}, {"valid_until": None},
        ):
            with self.subTest(change=change):
                response = sample_response()
                response["targets"][0].update(change)
                report = audit(response)
                self.assertEqual(report["status"], "UNKNOWN")
                self.assertEqual(report["counts"]["fresh_targets"], 0)

    def test_expiry_boundary_is_not_ready_and_counts_are_not_fresh(self):
        response = sample_response()
        response["targets"][0]["valid_until"] = AS_OF
        report = audit(response)
        self.assertEqual(report["targets"][0]["reason"], "EXPIRED")
        self.assertEqual(report["counts"]["ready_nodes_in_fresh_reports"], 0)
        self.assertFalse(report["all_reported_eligible_nodes_ready"])

    def test_repeated_reads_do_not_extend_original_observation(self):
        response = sample_response()
        before = copy.deepcopy(response)
        fresh = audit(response)
        stale = audit(response, as_of="2026-10-30T00:02:00Z")
        self.assertEqual(response, before)
        self.assertEqual(fresh["targets"][0]["valid_until"],
                         stale["targets"][0]["valid_until"])
        self.assertEqual(fresh["targets"][0]["observed_at"],
                         stale["targets"][0]["observed_at"])
        self.assertEqual(stale["status"], "UNKNOWN")

    def test_old_observation_is_unknown_even_with_later_runtime_expiry(self):
        response = sample_response()
        report = audit(response, as_of="2026-10-30T00:01:00Z")
        self.assertEqual(report["targets"][0]["reason"], "OBSERVATION_TOO_OLD")
        self.assertEqual(audit(response, as_of="2026-10-30T00:01:00Z",
                               max_age_seconds=120)["status"], "ALL_ELIGIBLE_READY")

    def test_future_observation_and_invalid_time_window(self):
        for observed, until, reason in (
            ("2026-10-30T00:00:31Z", "2026-10-30T00:02:00Z", "FUTURE_OBSERVATION"),
            ("2026-10-30T00:00:00Z", "2026-10-30T00:00:00Z", "INVALID_TIME_WINDOW"),
        ):
            with self.subTest(reason=reason):
                response = sample_response()
                response["targets"][0].update(observed_at=observed, valid_until=until)
                self.assertEqual(audit(response)["targets"][0]["reason"], reason)

    def test_rfc3339_nanoseconds_do_not_truncate_future_or_expiry(self):
        response = sample_response()
        response["targets"][0]["observed_at"] = "2026-10-30T00:00:30.000000001Z"
        self.assertEqual(audit(response)["targets"][0]["reason"], "FUTURE_OBSERVATION")
        response["targets"][0].update(
            observed_at="2026-10-30T00:00:00Z",
            valid_until="2026-10-30T00:00:30.000000001Z",
        )
        self.assertEqual(audit(response)["status"], "ALL_ELIGIBLE_READY")

    def test_timezone_offsets_represent_the_same_instant(self):
        response = sample_response()
        response["targets"][0].update(
            observed_at="2026-10-30T09:00:00+09:00",
            valid_until="2026-10-30T09:02:00+09:00",
        )
        self.assertEqual(audit(response)["status"], "ALL_ELIGIBLE_READY")

    def test_invalid_timestamp_is_not_echoed(self):
        for value in ("secret-value", "2026-10-30T00:00:00", 1,
                      "2026-10-30T00:00:00-00:00", "2026-10-30T00:00:00+09:60",
                      "2026-02-30T00:00:00Z", "2026-10-30T00:00:00.\u0661Z"):
            with self.subTest(value=value):
                response = sample_response()
                response["targets"][0]["observed_at"] = value
                report = audit(response)
                self.assertEqual(report["targets"][0]["reason"], "INVALID_TIMESTAMPS")
                self.assertNotIn("secret-value", json.dumps(report))

    def test_fresh_negative_observation_is_not_ready(self):
        response = sample_response()
        response["targets"][0].update(ready=False, ready_node_count=0)
        self.assertEqual(audit(response)["status"], "NOT_READY")
        response["targets"][0]["eligible_node_count"] = 0
        self.assertEqual(audit(response)["status"], "NOT_READY")

    def test_wrong_architecture_and_image_set_are_rejected(self):
        for change in ({"architecture": "ARM64"}, {"image_set_id": "sha256:" + "f" * 64}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                audit(dict(sample_response(), **change))

    def test_missing_helper_or_new_digest_cannot_reuse_old_response(self):
        for images in (
            [sample_artifact()["workload"]["containers"][0]["image"]],
            [item["image"].replace("a" * 64, "d" * 64)
             for item in sample_artifact()["workload"]["containers"]],
        ):
            with self.subTest(images=images), self.assertRaises(ValueError):
                response = sample_response()
                response["image_set_id"] = calculate_image_set_id("AMD64", images)
                audit(response)

    def test_unexpected_and_duplicate_response_targets_are_rejected(self):
        for targets in (
            [dict(sample_response()["targets"][0], target_id="different-target")],
            sample_response()["targets"] * 2,
            [None],
        ):
            with self.subTest(targets=targets), self.assertRaises(ValueError):
                audit(dict(sample_response(), targets=targets))

    def test_invalid_counts_and_boolean_types_are_rejected(self):
        changes = (
            {"ready": "true"}, {"ready": 1}, {"ready_node_count": True},
            {"eligible_node_count": True}, {"ready_node_count": -1},
            {"eligible_node_count": -1}, {"ready_node_count": 2},
            {"ready_node_count": 0}, {"ready": False},
            {"eligible_node_count": 2**31}, {"ready_node_count": 1.0},
        )
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ValueError):
                response = sample_response()
                response["targets"][0].update(change)
                audit(response)

    def test_operation_history_is_not_a_current_readiness_response(self):
        response = sample_response()
        response.pop("targets")
        response.update(status="SUCCEEDED", nodes=[{"status": "READY"}])
        with self.assertRaises(ValueError):
            audit(response)

    def test_unsupported_bundle_or_failed_evidence_is_rejected(self):
        for change in (
            {"category": "koth"}, {"runtime_type": "VM"}, {"scan_result": "FAIL"},
            {"registry_revision": 9}, {"source_ref": "refs/heads/feature/example"},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                artifact = dict(sample_artifact(), **change)
                audit(artifact=artifact)

    def test_image_and_target_runtime_limits_are_enforced(self):
        for targets in ([], ["target-a"] * 2, ["target-" + str(i) for i in range(51)],
                        [" target-a"], ["target-a\nvalue"], [1], ["x" * 129]):
            with self.subTest(targets=targets), self.assertRaises(ValueError):
                audit(targets=targets)
        response = dict(sample_response(), targets=[sample_response()["targets"][0]] * 51)
        with self.assertRaises(ValueError):
            audit(response)
        artifact = sample_artifact()
        container = artifact["workload"]["containers"][0]
        artifact["workload"]["containers"] = [
            dict(container, name=f"web-{i}", image=container["image"].replace("/web@", f"/web-{i}@"))
            for i in range(33)
        ]
        artifact["evidence"]["containers"] = [
            {"name": item["name"], "published_image": item["image"],
             "vulnerability_scan": "PASS", "secret_scan": "PASS"}
            for item in artifact["workload"]["containers"]
        ]
        with self.assertRaises(ValueError):
            audit(artifact=artifact)

    def test_invalid_age_and_audit_time_are_rejected(self):
        for value in (0, -1, True, 1.0, 86401):
            with self.subTest(value=value), self.assertRaises(ValueError):
                audit(max_age_seconds=value)
        with self.assertRaises(ValueError):
            audit(as_of="not-a-timestamp")

    def test_execution_values_and_response_cache_metadata_are_not_copied(self):
        artifact = sample_artifact()
        artifact["schema_version"] = "2.1"
        artifact["workload"]["containers"][0].update(
            env={"PASSWORD": "private-value"}, secret_env={"FLAG": "secret-reference"})
        response = dict(sample_response(artifact), readinessCache="miss",
                        token="do-not-copy", operation_status="SUCCEEDED")
        response["targets"][0]["private"] = "hidden-body"
        report = audit(response, artifact)
        self.assertEqual(report["status"], "ALL_ELIGIBLE_READY")
        for value in ("private-value", "secret-reference", "do-not-copy", "hidden-body", "PASSWORD"):
            self.assertNotIn(value, json.dumps(report))
        self.assertFalse(report["limits"]["operation_success_proven"])
        self.assertFalse(report["limits"]["cold_pull_proven"])

    def input_files(self, root, response=None):
        artifact_path, response_path = root / "artifact.json", root / "response.json"
        artifact_path.write_text(json.dumps(sample_artifact()) + "\n")
        response_path.write_text(json.dumps(response or sample_response()))
        return artifact_path, response_path

    def test_private_output_keeps_exact_bundle_hash_and_time_basis(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact, response = self.input_files(root)
            output = root / "private-report"
            report = write_audit(artifact, response, ["target-a"], output, as_of=AS_OF)
            self.assertEqual(report["bundle"]["artifact_sha256"],
                             hashlib.sha256(artifact.read_bytes()).hexdigest())
            self.assertEqual(report["time_basis"], "EXPLICIT_AS_OF")
            self.assertEqual({p.name for p in output.iterdir()}, {"readiness-audit.json"})
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE((output / "readiness-audit.json").stat().st_mode), 0o600)
            self.assertIn("generated_at", report)

    def test_default_audit_time_is_explicitly_marked_as_system_utc(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact, response = self.input_files(root)
            report = write_audit(artifact, response, ["target-a"], root / "out")
            self.assertEqual(report["time_basis"], "SYSTEM_UTC_NOW")
            self.assertEqual(report["as_of"], report["generated_at"])

    def test_empty_explicit_time_is_not_silently_replaced_with_current_time(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact, response = self.input_files(root)
            with self.assertRaises(ValueError):
                write_audit(artifact, response, ["target-a"], root / "out", as_of="")
            self.assertFalse((root / "out").exists())

    def test_existing_output_directory_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact, response = self.input_files(root)
            output = root / "report"
            write_audit(artifact, response, ["target-a"], output, as_of=AS_OF)
            previous = (output / "readiness-audit.json").read_bytes()
            with self.assertRaises(FileExistsError):
                write_audit(artifact, response, ["target-a"], output, as_of=AS_OF)
            self.assertEqual((output / "readiness-audit.json").read_bytes(), previous)

    def test_invalid_input_does_not_create_output_and_rejects_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact, response = self.input_files(root)
            response.write_text("{}")
            with self.assertRaises(ValueError):
                write_audit(artifact, response, ["target-a"], root / "out", as_of=AS_OF)
            self.assertFalse((root / "out").exists())
            response.write_text(json.dumps(sample_response()))
            link = root / "linked.json"
            link.symlink_to(artifact)
            with self.assertRaises(ValueError):
                write_audit(link, response, ["target-a"], root / "out", as_of=AS_OF)
            response.write_bytes(b"x" * (1024 * 1024 + 1))
            with self.assertRaises(ValueError):
                write_audit(artifact, response, ["target-a"], root / "out", as_of=AS_OF)

    def test_ambiguous_or_nonfinite_json_is_rejected(self):
        for contents in ('{"private":"hidden","private":"hidden-again"}',
                         '{"private":NaN}', '{"private":Infinity}'):
            with self.subTest(contents=contents), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                artifact, response = self.input_files(root)
                response.write_text(contents)
                with self.assertRaises(ValueError):
                    write_audit(artifact, response, ["target-a"], root / "out", as_of=AS_OF)
                self.assertFalse((root / "out").exists())

    def run_cli(self, root, response):
        artifact_path, response_path = self.input_files(root, response)
        return subprocess.run(
            [sys.executable, "-B", "-m", "scripts.audit_node_image_readiness",
             "--artifact", str(artifact_path), "--readiness-response", str(response_path),
             "--target-id", "target-a", "--output-dir", str(root / "out"),
             "--as-of", AS_OF],
            cwd=ROOT, capture_output=True, text=True, timeout=10,
        )

    def test_cli_exit_codes_distinguish_complete_unknown_and_invalid(self):
        for response, expected in (
            (sample_response(), 0),
            (dict(sample_response(), targets=[]), 1),
            (dict(sample_response(), image_set_id="sha256:" + "f" * 64), 2),
        ):
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                result = self.run_cli(root, response)
                self.assertEqual(result.returncode, expected, result.stderr)
                self.assertEqual((root / "out").exists(), expected != 2)
                self.assertNotIn("target-a", result.stdout + result.stderr)
                self.assertNotIn("Traceback", result.stderr)

    def test_direct_script_cli_also_imports(self):
        result = subprocess.run(
            [sys.executable, "-B", str(ROOT / "scripts/audit_node_image_readiness.py"), "--help"],
            cwd=ROOT, capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--readiness-response", result.stdout)

    def test_cli_errors_do_not_print_private_response(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = self.run_cli(Path(temporary), {"private": "do-not-print-this"})
            self.assertEqual(result.returncode, 2)
            self.assertNotIn("do-not-print-this", result.stdout + result.stderr)
            self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
