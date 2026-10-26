import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

import yaml

from scripts.generate_node_image_plan import generate_plan, write_plan
from scripts.generate_publish_bundle import generate_bundle


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_SHA = "c" * 64


def sample_artifact():
    containers = [
        {"name": name, "image": f"ghcr.io/msg-ctf/challenges/web-notebook/{name}@sha256:{digest * 64}",
         "ports": [{"port": port, "public": public}]}
        for name, digest, port, public in (("web", "a", 8080, True), ("db", "b", 5432, False))
    ]
    return {
        "schema_version": "2.0",
        "challenge_slug": "web-notebook",
        "registry_revision": 5,
        "revision": 5,
        "runtime_type": "KUBERNETES",
        "architecture": "AMD64",
        "category": "web",
        "source_ref": "refs/heads/main",
        "source_sha": "1" * 40,
        "scan_result": "PASS",
        "workload": {"containers": containers},
        "evidence": {"containers": [
            {"name": item["name"], "published_image": item["image"],
             "vulnerability_scan": "PASS", "secret_scan": "PASS"}
            for item in containers
        ]},
    }


class GenerateNodeImagePlanTests(unittest.TestCase):
    def test_includes_public_and_private_containers_without_changing_artifact(self):
        artifact = sample_artifact()
        before = copy.deepcopy(artifact)
        plan, images = generate_plan(artifact, ARTIFACT_SHA)
        self.assertEqual(artifact, before)
        self.assertEqual([item["name"] for item in plan["containers"]], ["db", "web"])
        self.assertEqual(images.decode().splitlines(), [item["image"] for item in plan["containers"]])
        self.assertEqual(plan["artifact_sha256"], ARTIFACT_SHA)
        self.assertEqual(plan["image_list"]["sha256"], hashlib.sha256(images).hexdigest())
        self.assertIs(plan["plan_only"], True)
        self.assertEqual(plan["registry_revision"], 5)
        self.assertEqual(plan["architecture"], "AMD64")
        self.assertNotIn("ready", plan)

    def test_reordering_containers_does_not_change_the_image_list(self):
        artifact = sample_artifact()
        expected = generate_plan(artifact, ARTIFACT_SHA)
        artifact["workload"]["containers"].reverse()
        artifact["evidence"]["containers"].reverse()
        self.assertEqual(generate_plan(artifact, ARTIFACT_SHA), expected)

    def test_keeps_revisions_separate_and_does_not_overwrite_the_old_plan(self):
        previous = sample_artifact()
        updated = copy.deepcopy(previous)
        updated.update(registry_revision=6, revision=6, source_sha="2" * 40)
        updated["workload"]["containers"][0]["image"] = (
            "ghcr.io/msg-ctf/challenges/web-notebook/web@sha256:" + "d" * 64
        )
        updated["evidence"]["containers"][0]["published_image"] = updated["workload"]["containers"][0]["image"]
        old_plan, old_images = generate_plan(previous, ARTIFACT_SHA)
        new_plan, new_images = generate_plan(updated, "d" * 64)
        self.assertEqual(old_plan["registry_revision"], 5)
        self.assertEqual(new_plan["registry_revision"], 6)
        self.assertNotEqual(old_images, new_images)
        self.assertIn(("a" * 64).encode(), old_images)

    def test_supports_arm64_and_schema_21_without_exporting_execution_settings(self):
        artifact = sample_artifact()
        artifact.update(architecture="ARM64", schema_version="2.1")
        artifact["workload"]["containers"][0].update(
            env={"APP_MODE": "not-for-image-plan"}, secret_env={"FLAG": "secret-binding"}
        )
        plan, _ = generate_plan(artifact, ARTIFACT_SHA)
        self.assertEqual(plan["architecture"], "ARM64")
        self.assertEqual(set(plan["containers"][0]), {"name", "image"})
        for forbidden in ("not-for-image-plan", "secret-binding", "secret_env", "FLAG"):
            self.assertNotIn(forbidden, json.dumps(plan))

    def test_pwn_image_list_is_not_an_execution_approval(self):
        artifact = sample_artifact()
        artifact["category"] = "pwn"
        plan, _ = generate_plan(artifact, ARTIFACT_SHA)
        self.assertIs(plan["plan_only"], True)
        self.assertNotIn("create_enabled", plan)

    def test_plan_is_not_a_runtime_preparation_request_or_readiness_result(self):
        artifact = sample_artifact()
        artifact["isolation_profile"] = "WEB"
        before = copy.deepcopy(artifact)
        plan, _ = generate_plan(artifact, ARTIFACT_SHA)
        self.assertEqual(artifact, before)
        for container in plan["containers"]:
            self.assertEqual(set(container), {"name", "image"})
        for field in (
            "release_id", "request_id", "target_ids", "isolation_profile",
            "operation_id", "image_set_id", "ready", "ready_node_count",
            "eligible_node_count", "observed_at", "valid_until", "nodes",
        ):
            self.assertNotIn(field, plan)
        self.assertEqual(artifact["isolation_profile"], "WEB")
        self.assertEqual(artifact["workload"]["containers"][1]["ports"],
                         [{"port": 5432, "public": False}])

    def test_documented_b_contract_keeps_preparation_optional_and_owners_separate(self):
        text = (ROOT / "docs/node-image-prefetch.md").read_text(encoding="utf-8")
        for reference in (
            "https://github.com/MSG-CTF/secure-provisioner/pull/70",
            "https://github.com/MSG-CTF/secure-provisioner/issues/69",
            "https://github.com/MSG-CTF/msg-backend/issues/139",
            "https://github.com/MSG-CTF/instance-scheduler/issues/75",
            "https://github.com/MSG-CTF/resource-broker/issues/8",
        ):
            self.assertIn(reference, text)
        self.assertIn("준비 상태는 성능 선호 조건", text)
        self.assertIn("실제\n실행의 인증·digest 승인·격리·플랫폼·자원 검사는 계속 필수", text)
        self.assertIn("준비 API에 그대로 POST할 요청이 아닙니다", text)
        self.assertIn("준비 실패만으로 차단하지 않음", text)
        self.assertNotIn("준비된 release만 active 전환", text)

    def test_excludes_koth_vm_and_non_kubernetes_payloads(self):
        for change in ({"category": "koth"}, {"runtime_type": "VM"}, {"runtime_type": "DOCKER"}):
            with self.subTest(change=change):
                self.assertIsNone(generate_plan(dict(sample_artifact(), **change), ARTIFACT_SHA))

    def test_rejects_wrong_source_schema_architecture_revision_and_scan(self):
        cases = (
            {"schema_version": "3.0"}, {"source_ref": "refs/heads/feature/example"},
            {"source_sha": "invalid"}, {"source_sha": 1}, {"scan_result": "FAIL"},
            {"architecture": "WINDOWS"}, {"registry_revision": True},
            {"registry_revision": 0}, {"registry_revision": 6}, {"revision": True},
            {"challenge_slug": "../outside"}, {"challenge_slug": "koth-example"},
        )
        for change in cases:
            with self.subTest(change=change), self.assertRaises(ValueError):
                generate_plan(dict(sample_artifact(), **change), ARTIFACT_SHA)

    def test_rejects_unpinned_cross_repository_or_injected_images(self):
        for image in (
            "ghcr.io/msg-ctf/challenges/web-notebook/web:latest",
            "ghcr.io/msg-ctf/challenges/web-notebook/web:v1.0.0",
            "ghcr.io/msg-ctf/challenges/other-problem/web@sha256:" + "a" * 64,
            "ghcr.io/msg-ctf/challenges/web-notebook/other@sha256:" + "a" * 64,
            "evil.example/web@sha256:" + "a" * 64,
            sample_artifact()["workload"]["containers"][0]["image"] + "\nmalicious-command",
            1,
        ):
            with self.subTest(image=image), self.assertRaises(ValueError):
                artifact = sample_artifact()
                artifact["workload"]["containers"][0]["image"] = image
                generate_plan(artifact, ARTIFACT_SHA)

    def test_rejects_missing_duplicate_and_invalid_containers(self):
        for value in ([], {}, [None], [dict(sample_artifact()["workload"]["containers"][0])] * 2,
                      [{"name": "web\ncommand", "image": "invalid"}]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                artifact = sample_artifact()
                artifact["workload"]["containers"] = value
                generate_plan(artifact, ARTIFACT_SHA)

    def test_rejects_missing_mismatched_duplicate_or_failed_scan_evidence(self):
        cases = [None, [], [None, None]]
        cases.append(sample_artifact()["evidence"]["containers"][:1] * 2)
        for field, value in (("published_image", "wrong"), ("vulnerability_scan", "FAIL"),
                             ("secret_scan", "Not scanned"), ("name", "another-container")):
            evidence = copy.deepcopy(sample_artifact()["evidence"]["containers"])
            evidence[0][field] = value
            cases.append(evidence)
        for evidence in cases:
            with self.subTest(evidence=evidence), self.assertRaises(ValueError):
                artifact = sample_artifact()
                artifact["evidence"]["containers"] = evidence
                generate_plan(artifact, ARTIFACT_SHA)

    def test_rejects_non_objects_and_invalid_artifact_hashes(self):
        for value in (None, [], "not-json-object"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                generate_plan(value, ARTIFACT_SHA)
        for value in (None, "", "not-sha256", "a" * 63, "A" * 64):
            with self.subTest(value=value), self.assertRaises(ValueError):
                generate_plan(sample_artifact(), value)

    def test_cli_writes_exact_artifact_hash_and_only_two_output_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw = (json.dumps(sample_artifact()) + "\n").encode()
            artifact = root / "artifact-v2.json"
            artifact.write_bytes(raw)
            output = root / "node-prefetch"
            result = subprocess.run(
                [sys.executable, "-B", str(ROOT / "scripts/generate_node_image_plan.py"),
                 "--artifact", str(artifact), "--output-dir", str(output)],
                capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(artifact.read_bytes(), raw)
            self.assertEqual({path.name for path in output.iterdir()}, {"plan.json", "images.txt"})
            plan = json.loads((output / "plan.json").read_text())
            self.assertEqual(plan["artifact_sha256"], hashlib.sha256(raw).hexdigest())
            self.assertIn("실제 노드 다운로드와 활성화는 실행하지 않았습니다", result.stdout)

    def test_existing_output_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / "artifact-v2.json"
            artifact.write_text(json.dumps(sample_artifact()))
            output = root / "node-prefetch"
            self.assertTrue(write_plan(artifact, output))
            previous = (output / "plan.json").read_bytes()
            with self.assertRaises(FileExistsError):
                write_plan(artifact, output)
            self.assertEqual((output / "plan.json").read_bytes(), previous)

    def test_invalid_input_does_not_create_an_output_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / "artifact-v2.json"
            artifact.write_text(json.dumps(dict(sample_artifact(), scan_result="FAIL")))
            output = root / "node-prefetch"
            with self.assertRaises(ValueError):
                write_plan(artifact, output)
            self.assertFalse(output.exists())
            artifact.write_bytes(b"x" * (1024 * 1024 + 1))
            with self.assertRaises(ValueError):
                write_plan(artifact, output)
            self.assertFalse(output.exists())

    def test_symlinked_artifact_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original = root / "original.json"
            original.write_text(json.dumps(sample_artifact()))
            link = root / "artifact-v2.json"
            link.symlink_to(original)
            with self.assertRaises(ValueError):
                write_plan(link, root / "node-prefetch")

    def test_koth_scope_does_not_emit_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / "artifact-v2.json"
            artifact.write_text(json.dumps(dict(sample_artifact(), category="koth")))
            self.assertFalse(write_plan(artifact, root / "node-prefetch"))
            self.assertFalse((root / "node-prefetch").exists())

    def test_validation_failure_does_not_print_artifact_contents(self):
        with tempfile.TemporaryDirectory() as temporary:
            artifact = Path(temporary) / "artifact-v2.json"
            artifact.write_text(json.dumps({"private": "do-not-print-this", "schema_version": "bad"}))
            result = subprocess.run(
                [sys.executable, "-B", "-m", "scripts.generate_node_image_plan", "--artifact", str(artifact),
                 "--output-dir", str(Path(temporary) / "output")],
                cwd=ROOT, capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(result.returncode, 2)
            self.assertNotIn("do-not-print-this", result.stdout + result.stderr)
            self.assertNotIn("Traceback", result.stderr)

    def test_workflow_generates_plan_before_existing_bundle_upload(self):
        workflow = yaml.load((ROOT / ".github/workflows/challenge-supply-chain.yml").read_text(), Loader=yaml.BaseLoader)
        aggregate = workflow["jobs"]["aggregate"]
        steps = aggregate["steps"]
        plan_index = next(index for index, step in enumerate(steps) if step.get("name") == "노드 이미지 사전 다운로드 목록 생성")
        artifact_index = next(index for index, step in enumerate(steps) if step.get("name") == "Runtime artifact와 Registry publish document 생성")
        upload_index = next(index for index, step in enumerate(steps) if step.get("name") == "Atomic Publish bundle 업로드")
        self.assertLess(artifact_index, plan_index)
        self.assertLess(plan_index, upload_index)
        self.assertIn("github.ref == 'refs/heads/main'", steps[plan_index]["if"])
        self.assertIn("workflow_dispatch", steps[plan_index]["if"])
        self.assertIn("--output-dir dist/node-prefetch", steps[plan_index]["run"])
        self.assertEqual(steps[upload_index]["with"]["path"], "dist/")
        self.assertEqual(aggregate["permissions"], {"contents": "read"})
        for forbidden in ("ssh ", "kubectl ", "docker pull", "k3s ", "RUNTIME_API_TOKEN", "curl "):
            self.assertNotIn(forbidden, steps[plan_index]["run"])

    def test_actual_workflow_command_generates_plan_without_network_or_node_access(self):
        workflow = yaml.load((ROOT / ".github/workflows/challenge-supply-chain.yml").read_text(), Loader=yaml.BaseLoader)
        step = next(step for step in workflow["jobs"]["aggregate"]["steps"]
                    if step.get("name") == "노드 이미지 사전 다운로드 목록 생성")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".msgctf-ci").symlink_to(ROOT, target_is_directory=True)
            (root / "dist").mkdir()
            artifact_path = root / "dist/artifact-v2.json"
            artifact_path.write_text(json.dumps(sample_artifact()))
            result = subprocess.run(["bash", "-eu", "-c", step["run"]], cwd=root,
                                    env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((root / "dist/node-prefetch/plan.json").is_file())

    def test_existing_poller_file_selection_still_reads_original_artifact(self):
        artifact = sample_artifact()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact_path = root / "artifact-v2.json"
            artifact_path.write_text(json.dumps(artifact))
            write_plan(artifact_path, root / "node-prefetch")
            archive_path = root / "bundle.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                for path in (artifact_path, *(root / "node-prefetch").iterdir()):
                    archive.write(path, path.relative_to(root))
            with zipfile.ZipFile(archive_path) as archive:
                # 현재 Backend Poller의 파일 선택에서 원본 bundle이 유지됩니다.
                selected = next(name for name in archive.namelist() if name.split("/")[-1] == "artifact-v2.json")
                self.assertEqual(json.loads(archive.read(selected)), artifact)

    def test_bundle_generator_output_is_supported_without_changing_schema(self):
        artifact = sample_artifact()
        metadata = {key: artifact[key] for key in ("challenge_slug", "category", "runtime_type", "architecture")}
        metadata.update(name="Web Notebook", containers=[
            {"name": "web", "ports": [8080], "expose": True},
            {"name": "db", "ports": [5432], "expose": False},
        ], resource_profile={"cpu_millicores": 700, "memory_mib": 768, "ephemeral_storage_mib": 1024})
        results = [{"name": item["name"], "image": item["image"],
                    "source_digest": item["image"].split("@", 1)[1],
                    "sbom": f"results/{item['name']}/sbom/{item['name']}.cdx.json", "scan_result": "PASS",
                    "timing": {"build_seconds": 1, "scan_seconds": 1, "push_seconds": 1, "total_seconds": 3}}
                   for item in artifact["workload"]["containers"]]
        generated = generate_bundle(metadata, results, "refs/heads/main", "1" * 40, 5,
                                    ROOT / "tests/fixtures/publish-evidence")["artifact"]
        plan, _ = generate_plan(generated, ARTIFACT_SHA)
        self.assertEqual(generated["schema_version"], "2.0")
        self.assertEqual(len(plan["containers"]), 2)
        self.assertNotIn("node-prefetch", generated)


if __name__ == "__main__":
    unittest.main()
