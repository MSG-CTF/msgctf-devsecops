import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts import prepare_release_transition as transition
from scripts.audit_node_image_readiness import calculate_image_set_id
from tests.test_generate_node_image_plan import sample_artifact


ROOT = Path(__file__).resolve().parents[1]
AS_OF = "2026-11-04T00:00:30Z"
OBSERVED = "2026-11-04T00:00:00Z"
A_ID = "00000000-0000-4000-8000-000000000001"
B_ID = "00000000-0000-4000-8000-000000000002"
CHALLENGE_ID = "00000000-0000-4000-8000-000000000003"


def inputs():
    a = sample_artifact()
    a.update(isolation_profile="WEB", resource_profile={"cpu_millicores": 500,
        "memory_mib": 512, "ephemeral_storage_mib": 1024})
    a["workload"]["healthcheck"] = {"container": "web", "port": 8080, "path": "/health"}
    b = copy.deepcopy(a)
    b.update(registry_revision=6, revision=6, source_sha="2" * 40)
    b["workload"]["containers"][0]["image"] = b["workload"]["containers"][0]["image"].replace("a" * 64, "d" * 64)
    b["evidence"]["containers"][0]["published_image"] = b["workload"]["containers"][0]["image"]
    def saved(bundle, release_id, current):
        return {"release_id": release_id, "challenge_id": CHALLENGE_ID,
            "challenge_slug": bundle["challenge_slug"], "registry_revision": bundle["registry_revision"],
            "runtime_type": "KUBERNETES", "architecture": "AMD64", "isolation_profile": "WEB",
            "source_ref": "refs/heads/main", "is_deployable": True, "is_current": current,
            "derived_from_release_id": None, "approved_at": OBSERVED,
            "resource_profile": copy.deepcopy(bundle["resource_profile"]),
            "healthcheck": copy.deepcopy(bundle["workload"]["healthcheck"]),
            "containers": [{"name": row["name"], "image_ref": row["image"],
                            "ports": copy.deepcopy(row["ports"]), "secret_bindings": [], "env_rules": {}}
                           for row in bundle["workload"]["containers"]]}
    snapshot = {"challenge_id": CHALLENGE_ID, "current_release_id": A_ID, "activation": None,
                "releases": [saved(a, A_ID, True), saved(b, B_ID, False)]}
    readiness = {"architecture": "AMD64", "image_set_id": calculate_image_set_id("AMD64",
                 [row["image"] for row in b["workload"]["containers"]]),
                 "targets": [{"target_id": "target-a", "ready": True,
                              "ready_node_count": 1, "eligible_node_count": 1,
                              "observed_at": OBSERVED, "valid_until": "2026-11-04T00:02:00Z"}]}
    return a, b, snapshot, readiness


def prepare(values=None, **kwargs):
    a, b, snapshot, readiness = values or inputs()
    return transition.prepare_transition(a, "a" * 64, b, "b" * 64, snapshot,
        current_release_id=kwargs.pop("current_release_id", A_ID),
        candidate_release_id=kwargs.pop("candidate_release_id", B_ID),
        target_ids=kwargs.pop("target_ids", ["target-a"]),
        backend_observed_at=kwargs.pop("backend_observed_at", OBSERVED),
        as_of=kwargs.pop("as_of", AS_OF), candidate_readiness=readiness, **kwargs)


class ReleaseTransitionTests(unittest.TestCase):
    def test_full_sets_and_current_are_preserved_without_mutation_or_network(self):
        values = inputs()
        original = copy.deepcopy(values)
        with patch("socket.create_connection", side_effect=AssertionError("network forbidden")), \
             patch("subprocess.Popen", side_effect=AssertionError("process forbidden")):
            result = prepare(values)
        self.assertEqual(values, original)
        self.assertEqual(result["status"], "READY_FOR_REPRESENTATIVE_QA")
        self.assertEqual(len(result["preserve_images"]), 3)
        self.assertEqual(len(result["current"]["containers"]), 2)
        self.assertEqual(result["current"]["release_id"], A_ID)
        self.assertEqual(result["plan_sha256"], transition.plan_hash(result))
        self.assertTrue(all(value is False for value in result["limits"].values()))
        self.assertEqual(result["live_instance_handover"]["status"], "BLOCKED_PENDING_CONSUMER_CONTRACTS")

    def test_exact_existing_preparation_path_never_generates_activate_or_replace(self):
        handoff = prepare()["preparation_handoff"]
        self.assertEqual(handoff["method"], "POST")
        self.assertEqual(handoff["path"], f"/api/v1/admin/challenges/{CHALLENGE_ID}/releases/{B_ID}/image_preparations")
        self.assertEqual(handoff["body"], {})
        self.assertFalse(handoff["call_performed"])
        self.assertTrue(handoff["requires_operator_approval"])
        self.assertNotIn("/activate", json.dumps(prepare()))
        self.assertNotIn("replace_instance_id", json.dumps(prepare()))
        test_handoff = prepare()["representative_test_handoff"]
        self.assertEqual(test_handoff["path"], f"/api/v1/admin/challenges/{CHALLENGE_ID}/releases/{B_ID}/deployment_tests")
        self.assertEqual(set(test_handoff["body"]), {"request_id"})
        self.assertFalse(test_handoff["call_performed"])
        self.assertFalse(test_handoff["traffic_switch"])

    def test_missing_readiness_is_a_plan_not_permission_to_switch(self):
        a, b, snapshot, _ = inputs()
        result = prepare((a, b, snapshot, None))
        self.assertEqual(result["status"], "IMAGE_READINESS_REQUIRED")
        self.assertIsNone(result["candidate_readiness"])
        self.assertFalse(result["limits"]["automatic_switch_allowed"])

    def test_partial_missing_and_expired_readiness_stay_blocked(self):
        for change in ({"eligible_node_count": 2}, {"valid_until": AS_OF},
                       {"observed_at": None}, {"target_id": "unexpected"}):
            values = inputs()
            values[3]["targets"][0].update(change)
            with self.subTest(change=change):
                if "target_id" in change:
                    with self.assertRaises(ValueError):
                        prepare(values)
                else:
                    self.assertEqual(prepare(values)["status"], "IMAGE_READINESS_REQUIRED")

    def test_a_readiness_cannot_be_used_for_b(self):
        values = inputs()
        values[3]["image_set_id"] = calculate_image_set_id("AMD64", [row["image"] for row in values[0]["workload"]["containers"]])
        with self.assertRaises(ValueError):
            prepare(values)

    def test_changed_active_and_same_release_are_rejected(self):
        values = inputs()
        values[2]["current_release_id"] = B_ID
        with self.assertRaises(ValueError):
            prepare(values)
        with self.assertRaises(ValueError):
            prepare(candidate_release_id=A_ID)

    def test_old_future_and_boundary_snapshot_are_rejected(self):
        for observed in ("2026-11-03T23:59:30Z", "2026-11-04T00:00:31Z", "2026-11-03T00:00:00Z"):
            with self.subTest(observed=observed), self.assertRaises(ValueError):
                prepare(backend_observed_at=observed)

    def test_pending_and_unknown_activation_are_rejected_but_history_is_allowed(self):
        for status in ("PENDING", "UNKNOWN", "ACTIVATED", "SUPERSEDED", "FAILED"):
            values = inputs()
            values[2]["activation"] = {"status": status}
            with self.subTest(status=status):
                if status in ("PENDING", "UNKNOWN"):
                    with self.assertRaises(ValueError):
                        prepare(values)
                else:
                    self.assertEqual(prepare(values)["status"], "READY_FOR_REPRESENTATIVE_QA")

    def test_duplicate_release_ids_and_container_names_are_rejected(self):
        for duplicate in ("release", "container"):
            values = inputs()
            if duplicate == "release":
                values[2]["releases"].append(copy.deepcopy(values[2]["releases"][0]))
            else:
                values[2]["releases"][1]["containers"][1] = copy.deepcopy(values[2]["releases"][1]["containers"][0])
            with self.subTest(duplicate=duplicate), self.assertRaises(ValueError):
                prepare(values)

    def test_candidate_approval_and_deployability_are_required(self):
        for change in ({"approved_at": None}, {"approved_at": "2026-11-05T00:00:00Z"},
                       {"is_deployable": False}, {"is_current": True}, {"registry_revision": True}):
            values = inputs()
            values[2]["releases"][1].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                prepare(values)

    def test_wrong_problem_architecture_or_backend_revision_are_rejected(self):
        for key, value in (("challenge_id", A_ID), ("challenge_slug", "other-problem"),
                           ("architecture", "ARM64"), ("registry_revision", 7),
                           ("source_ref", "refs/heads/feature"), ("runtime_type", "DOCKER")):
            values = inputs()
            values[2]["releases"][1][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                prepare(values)

    def test_unscanned_tagged_pwn_vm_and_koth_are_rejected(self):
        for change in ({"scan_result": "FAIL"}, {"isolation_profile": "PWN"},
                       {"runtime_type": "VM"}, {"category": "koth"}):
            values = inputs()
            values[1].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                prepare(values)
        values = inputs()
        values[1]["workload"]["containers"][0]["image"] = "ghcr.io/msg-ctf/challenges/web-notebook/web:latest"
        with self.assertRaises(ValueError):
            prepare(values)

    def test_private_container_omission_and_wrong_digest_are_rejected(self):
        for mode in ("missing", "digest"):
            values = inputs()
            if mode == "missing":
                values[2]["releases"][1]["containers"].pop()
            else:
                values[2]["releases"][1]["containers"][1]["image_ref"] = "incorrect"
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                prepare(values)

    def test_port_visibility_boolean_duplicates_and_health_loss_are_rejected(self):
        for mode in ("public", "bool", "duplicate", "health"):
            values = inputs()
            saved = values[2]["releases"][1]
            if mode == "health":
                saved["healthcheck"] = None
            elif mode == "duplicate":
                saved["containers"][0]["ports"] *= 2
            else:
                saved["containers"][0]["ports"][0]["public" if mode == "public" else "port"] = False
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                prepare(values)

    def test_resource_and_environment_drift_are_rejected(self):
        for mode in ("resource", "env"):
            values = inputs()
            saved = values[2]["releases"][1]
            if mode == "resource":
                saved["resource_profile"]["memory_mib"] = 1024
            else:
                saved["containers"][0]["env"] = {"APP_MODE": "unexpected"}
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                prepare(values)

    def test_schema_21_settings_are_fingerprinted_without_exporting_values(self):
        values = inputs()
        values[1]["schema_version"] = "2.1"
        values[1]["workload"]["containers"][0].update(env={"APP_MODE": "private-app-value"}, secret_env={"FLAG": "flag"})
        saved = values[2]["releases"][1]["containers"][0]
        saved.update(env={"APP_MODE": "private-app-value"}, secret_ref=CHALLENGE_ID,
                     secret_bindings=[{"env_name": "FLAG", "name": "flag", "version": 2, "status": "registered"}])
        result = prepare(values)
        self.assertTrue(result["execution_settings_changed"])
        for value in ("private-app-value", "secret_bindings", "secret_ref"):
            self.assertNotIn(value, json.dumps(result))
        saved["secret_bindings"][0]["status"] = "missing"
        with self.assertRaises(ValueError):
            prepare(values)

    def test_unmodeled_derived_release_and_environment_rules_require_review(self):
        for mode in ("derived", "rules"):
            values = inputs()
            saved = values[2]["releases"][1]
            if mode == "derived":
                saved["derived_from_release_id"] = A_ID
            else:
                saved["containers"][0]["env_rules"] = {"FLAG": {"kind": "unknown"}}
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                prepare(values)

    def test_unmodeled_workload_and_container_fields_cannot_be_ignored(self):
        for key in ("storage", "network_policy", "internal_connections", "command", "run_as_user"):
            values = inputs()
            target = values[1]["workload"] if key in ("storage", "network_policy", "internal_connections") else values[1]["workload"]["containers"][0]
            target[key] = "unmodeled"
            with self.subTest(key=key), self.assertRaises(ValueError):
                prepare(values)

    def test_execution_settings_require_schema_21(self):
        values = inputs()
        values[1]["workload"]["containers"][0]["env"] = {"APP_MODE": "private-value"}
        values[2]["releases"][1]["containers"][0]["env"] = {"APP_MODE": "private-value"}
        with self.assertRaises(ValueError):
            prepare(values)

    def test_missing_backend_contract_fields_cannot_be_assumed_safe(self):
        for field in ("activation", "derived_from_release_id"):
            values = inputs()
            if field == "activation":
                del values[2][field]
            else:
                del values[2]["releases"][1][field]
            with self.subTest(field=field), self.assertRaises(ValueError):
                prepare(values)

    def test_secrets_cannot_appear_as_plain_env_or_undeclared_binding(self):
        for change in ({"env": {"FLAG": "private-flag"}}, {"secret_ref": A_ID}):
            values = inputs()
            values[2]["releases"][1]["containers"][0].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                prepare(values)

    def test_explicit_rollback_and_no_implicit_downgrade(self):
        a, b, snapshot, _ = inputs()
        snapshot["current_release_id"] = B_ID
        snapshot["releases"][0]["is_current"] = False
        snapshot["releases"][1]["is_current"] = True
        with self.assertRaises(ValueError):
            prepare((b, a, snapshot, None), current_release_id=B_ID, candidate_release_id=A_ID)
        result = prepare((b, a, snapshot, None), current_release_id=B_ID, candidate_release_id=A_ID, direction="rollback")
        self.assertEqual(result["direction"], "rollback")
        self.assertEqual(result["candidate"]["release_id"], A_ID)

    def test_targets_and_reordering_are_handled_without_losing_private_images(self):
        values = inputs()
        expected = prepare(values)
        values[2]["releases"].reverse()
        for row in values[2]["releases"]:
            row["containers"].reverse()
        self.assertEqual(prepare(values), expected)
        with self.assertRaises(ValueError):
            prepare(target_ids=["target-a", "target-a"])

    def test_private_files_exact_raw_checksum_and_no_overwrite(self):
        a, b, snapshot, readiness = inputs()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = [root / name for name in ("a.json", "b.json", "backend.json", "readiness.json")]
            for path, value in zip(paths, (a, b, snapshot, readiness)):
                path.write_text(json.dumps(value, indent=4) + "\n")
            output = root / "private"
            kwargs = dict(current_release_id=A_ID, candidate_release_id=B_ID, target_ids=["target-a"],
                          backend_observed_at=OBSERVED, as_of=AS_OF, readiness_path=paths[3])
            report = transition.write_plan(*paths[:3], output, **kwargs)
            self.assertEqual(report["current"]["artifact_sha256"], hashlib.sha256(paths[0].read_bytes()).hexdigest())
            self.assertEqual(output.stat().st_mode & 0o777, 0o700)
            self.assertEqual((output / "transition-plan.json").stat().st_mode & 0o777, 0o600)
            self.assertEqual(report["time_basis"], "EXPLICIT_REPLAY_TIME")
            with self.assertRaises(FileExistsError):
                transition.write_plan(*paths[:3], output, **kwargs)

    def test_cli_error_does_not_print_path_or_payload(self):
        command = [sys.executable, "-B", "-m", "scripts.prepare_release_transition",
            "--current-artifact", "/private-operator-source/missing", "--candidate-artifact", "/missing",
            "--backend-releases", "/missing", "--current-release-id", A_ID, "--candidate-release-id", B_ID,
            "--backend-observed-at", OBSERVED, "--target-id", "target-a", "--output-dir", "/unused"]
        result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("private-operator-source", result.stderr)

    def test_cli_ready_and_missing_readiness_have_distinct_exit_codes(self):
        values = inputs()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = [root / name for name in ("a.json", "b.json", "backend.json", "ready.json")]
            for path, value in zip(paths, values):
                path.write_text(json.dumps(value))
            command = [sys.executable, "-B", "-m", "scripts.prepare_release_transition",
                "--current-artifact", str(paths[0]), "--candidate-artifact", str(paths[1]),
                "--backend-releases", str(paths[2]), "--current-release-id", A_ID,
                "--candidate-release-id", B_ID, "--backend-observed-at", OBSERVED,
                "--as-of", AS_OF, "--target-id", "target-a"]
            waiting = subprocess.run(command + ["--output-dir", str(root / "waiting")],
                                     cwd=ROOT, text=True, capture_output=True)
            self.assertEqual(waiting.returncode, 1)
            self.assertEqual(json.loads(waiting.stdout)["status"], "IMAGE_READINESS_REQUIRED")
            ready = subprocess.run(command + ["--candidate-readiness", str(paths[3]),
                                   "--output-dir", str(root / "ready")], cwd=ROOT, text=True, capture_output=True)
            self.assertEqual(ready.returncode, 0, ready.stderr)
            self.assertFalse(json.loads(ready.stdout)["automatic_switch_allowed"])


if __name__ == "__main__":
    unittest.main()
