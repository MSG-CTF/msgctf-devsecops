import copy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import warnings
import zipfile
from unittest.mock import patch

import yaml

from scripts import collect_node_image_plans as collector
from scripts.generate_node_image_plan import generate_plan


ROOT = Path(__file__).resolve().parents[1]
SHA = "1" * 40


def artifact(slug="web-one", digest="a", arch="AMD64"):
    image = f"ghcr.io/msg-ctf/challenges/{slug}/web@sha256:{digest * 64}"
    return {"schema_version": "2.0", "category": "web", "challenge_slug": slug,
            "registry_revision": 1, "revision": 1, "architecture": arch, "runtime_type": "KUBERNETES",
            "source_sha": SHA, "source_ref": "refs/heads/main", "scan_result": "PASS",
            "workload": {"containers": [{"name": "web", "image": image}]},
            "evidence": {"containers": [{"name": "web", "published_image": image,
                                        "secret_scan": "PASS", "vulnerability_scan": "PASS"}]}}


def plan(slug="web-one", digest="a", arch="AMD64"):
    value, _ = generate_plan(artifact(slug, digest, arch), "c" * 64)
    return {**value, "publish_run_id": 100, "publish_artifact_id": 200}


def selected():
    return {"id": 200, "run_id": 100, "registry_revision": 1, "source_sha": SHA,
            "name": "web-one-100-1-abcdef-publish-bundle", "problem_tree_matches": True}


def catalog(*slugs):
    return {"repository": collector.publication.REPOSITORY, "source_ref": "refs/heads/main", "source_sha": SHA,
            "counts": {"total": len(slugs)}, "problems": [
                {"challenge_slug": slug, "runtime_required": True,
                 "status": "ARTIFACTS_MATCH_PROBLEM_TREE", "artifacts": {"publish": selected()}}
                for slug in slugs]}


def make_report(*values):
    values = values or (plan(),)
    return collector.collect(catalog(*(value["challenge_slug"] for value in values)),
                             fetch=lambda slug, _: next(value for value in values if value["challenge_slug"] == slug))


def origin():
    meta = {"id": 200, "size_in_bytes": 1000, "expired": False,
            "name": selected()["name"], "workflow_run": {"id": 100, "head_sha": SHA, "head_branch": "main"}}
    run = {"id": 100, "status": "completed", "conclusion": "success", "event": "push",
           "head_sha": SHA, "head_branch": "main", "run_number": 1,
           "path": ".github/workflows/challenge-validation.yml",
           "repository": {"full_name": collector.publication.REPOSITORY},
           "head_repository": {"full_name": collector.publication.REPOSITORY}}
    return meta, run


class CollectNodeImagePlansTests(unittest.TestCase):
    def test_groups_complete_lists_by_architecture(self):
        report, changes, files = make_report(plan(), plan("web-two", "b", "ARM64"))
        self.assertEqual(report["counts"]["selected_problems"], 2)
        self.assertEqual(set(files), {"images-amd64.txt", "images-arm64.txt"})
        self.assertTrue(report["complete"])
        self.assertTrue(report["plan_only"])
        self.assertFalse(changes["deletion_authorized"])
        for name, raw in files.items():
            self.assertEqual(report["image_lists"][name]["sha256"], hashlib.sha256(raw).hexdigest())

    def test_initial_plan_does_not_pretend_to_have_a_previous_baseline(self):
        report, changes, _ = make_report()
        self.assertFalse(changes["baseline_present"])
        self.assertEqual(len(changes["added"]), 1)
        self.assertIn("최초 목록", collector.summary(report, changes))

    def test_diffs_added_changed_unchanged_and_no_longer_listed(self):
        old, _, _ = make_report(plan(), plan("web-keep", "b"), plan("web-old", "c"))
        new, _, _ = make_report(plan(digest="d"), plan("web-keep", "b"), plan("web-new", "e"))
        diff = collector.compare(new, old)
        for key in ("added", "changed", "unchanged", "no_longer_listed"):
            self.assertEqual(len(diff[key]), 1)
        self.assertEqual(diff["changed"][0]["previous_image"], old["plans"][2]["containers"][0]["image"])
        self.assertFalse(diff["deletion_authorized"])

    def test_architecture_change_is_a_change_even_for_the_same_digest(self):
        old, _, _ = make_report(plan())
        new, _, _ = make_report(plan(arch="ARM64"))
        self.assertEqual(len(collector.compare(new, old)["changed"]), 1)

    def test_excludes_static_koth_windows_and_non_kubernetes(self):
        source = catalog("web-one", "rev-static", "koth-real", "pwn-msgdriver", "web-vm")
        source["problems"][1]["runtime_required"] = False
        fetched = []
        def fetch(slug, _):
            fetched.append(slug)
            return None if slug == "web-vm" else plan(slug)
        report, _, _ = collector.collect(source, fetch=fetch)
        self.assertEqual(fetched, ["web-one", "web-vm"])
        self.assertEqual(len(report["excluded"]), 4)

    def test_no_eligible_image_cannot_be_reported_as_complete(self):
        source = catalog("rev-static")
        source["problems"][0]["runtime_required"] = False
        with self.assertRaises(ValueError):
            collector.collect(source)

    def test_unsupported_runtime_stays_visible_and_is_not_silently_converted(self):
        source = catalog("web-one", "pwn-docker")
        def fetch(slug, _):
            if slug == "pwn-docker":
                raise collector.UnsupportedWorkload("DOCKER")
            return plan(slug)
        report, changes, _ = collector.collect(source, fetch=fetch)
        self.assertEqual(report["counts"]["general_dynamic"], 2)
        self.assertEqual(report["counts"]["selected_problems"], 1)
        self.assertEqual(report["counts"]["unsupported_dynamic"], 1)
        self.assertIn("DOCKER", collector.summary(report, changes))
        self.assertEqual(report["excluded"][0]["runtime_type"], "DOCKER")

    def test_reports_every_missing_or_failed_problem_without_partial_success(self):
        source = catalog("web-one", "web-missing", "web-broken")
        source["problems"][1]["status"] = "MISSING_SUCCESSFUL_ARTIFACT"
        def fetch(slug, _):
            if slug == "web-broken":
                raise RuntimeError("do-not-print-secret")
            return plan(slug)
        with self.assertRaises(collector.CollectionFailure) as caught:
            collector.collect(source, fetch=fetch)
        self.assertEqual({row["challenge_slug"] for row in caught.exception.failures}, {"web-missing", "web-broken"})
        self.assertNotIn("do-not-print-secret", str(caught.exception.failures))

    def test_unconfirmed_problem_tree_is_rejected(self):
        source = catalog("web-one")
        source["problems"][0]["artifacts"]["publish"]["problem_tree_matches"] = False
        with self.assertRaises(collector.CollectionFailure):
            collector.collect(source)

    def test_detects_duplicate_or_truncated_catalogs(self):
        for source in (catalog("web-one", "web-one"), dict(catalog("web-one"), counts={"total": 2})):
            with self.subTest(source=source), self.assertRaises(ValueError):
                collector.collect(source, fetch=lambda slug, _: plan(slug))

    def test_expected_commit_and_mid_collection_main_change_are_rejected(self):
        with self.assertRaises(ValueError):
            collector.collect(catalog("web-one"), expected_sha="2" * 40)
        with self.assertRaises(ValueError):
            collector.collect(catalog("web-one"), fetch=lambda slug, _: plan(slug), head=lambda: "2" * 40)

    def test_fetches_and_checks_real_publication_shape_before_generating(self):
        meta, run = origin()
        data = artifact()
        result = collector.fetch_plan("web-one", selected(), api=lambda path: meta if "artifacts/" in path else run,
                                      download=lambda *_: (data, json.dumps(data).encode()))
        self.assertEqual(result["publish_artifact_id"], 200)
        self.assertEqual(result["artifact_sha256"], hashlib.sha256(json.dumps(data).encode()).hexdigest())

    def test_failed_expired_foreign_or_misbound_sources_are_rejected(self):
        mutations = (lambda m, r: m.update(expired=True), lambda m, r: r.update(conclusion="failure"),
                     lambda m, r: r.update(head_branch="feature/example"), lambda m, r: r.update(run_number=2),
                     lambda m, r: r.update(repository={"full_name": "outside/repo"}),
                     lambda m, r: r.update(path="other.yml"), lambda m, r: m.update(name="other-bundle"),
                     lambda m, r: m["workflow_run"].update(head_sha="2" * 40))
        for mutate in mutations:
            meta, run = origin()
            mutate(meta, run)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                collector.fetch_plan("web-one", selected(), api=lambda path: meta if "artifacts/" in path else run)

    def test_wrong_payload_slug_revision_digest_or_scan_is_rejected(self):
        for mutation in ({"challenge_slug": "web-two"}, {"registry_revision": 2}, {"scan_result": "FAIL"}):
            data = dict(artifact(), **mutation)
            meta, run = origin()
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                collector.fetch_plan("web-one", selected(), api=lambda path: meta if "artifacts/" in path else run,
                                     download=lambda *_: (data, json.dumps(data).encode()))

    def test_invalid_baselines_fail_instead_of_becoming_initial_lists(self):
        valid, _, _ = make_report()
        for update in ({"complete": False}, {"scope": "OTHER"}, {"repository": "other/repo"},
                       {"plans": []}, {"source_sha": "invalid"}, {"plan_only": False}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                collector.compare(valid, dict(valid, **update))

    def test_baseline_rejects_tag_paths_duplicates_and_mismatched_checksum(self):
        valid, _, _ = make_report()
        for mode in ("tag", "checksum", "duplicate", "outside"):
            old = copy.deepcopy(valid)
            if mode == "tag":
                old["plans"][0]["containers"][0]["image"] = "ghcr.io/msg-ctf/challenges/web-one/web:latest"
            elif mode == "checksum":
                old["plans"][0]["image_list"]["sha256"] = "0" * 64
            elif mode == "duplicate":
                old["plans"].append(old["plans"][0])
            else:
                old["plans"][0]["challenge_slug"] = "koth-real"
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                collector.compare(valid, old)

    def test_previous_artifact_requires_successful_official_collector_run(self):
        meta, run = origin()
        meta["name"] = "node-image-prefetch-100-1"
        run["path"] = ".github/workflows/node-image-prefetch.yml"
        previous, _, _ = make_report()
        api = lambda path: meta if "artifacts/" in path else run
        self.assertEqual(collector.fetch_previous(200, api=api, download=lambda *_: (previous, b"")), previous)
        run["conclusion"] = "failure"
        with self.assertRaises(ValueError):
            collector.fetch_previous(200, api=api, download=lambda *_: (previous, b""))

    def test_previous_artifact_commit_mismatch_is_rejected(self):
        meta, run = origin()
        meta["name"] = "node-image-prefetch-100-1"
        run["path"] = ".github/workflows/node-image-prefetch.yml"
        previous, _, _ = make_report()
        previous["source_sha"] = "2" * 40
        with self.assertRaises(ValueError):
            collector.fetch_previous(200, api=lambda path: meta if "artifacts/" in path else run,
                                     download=lambda *_: (previous, b""))

    def test_success_output_is_atomic_and_does_not_overwrite(self):
        report, diff, files = make_report()
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "result"
            collector.write_result(output, report, diff, files)
            self.assertTrue((output / "images-amd64.txt").is_file())
            with self.assertRaises(FileExistsError):
                collector.write_result(output, report, diff, files)
            self.assertEqual(json.loads((output / "prefetch-inventory.json").read_text()), report)

    def test_write_failure_leaves_no_partial_image_list(self):
        report, diff, files = make_report()
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "result"
            with patch.object(Path, "write_bytes", side_effect=OSError("disk-full")), self.assertRaises(OSError):
                collector.write_result(output, report, diff, files)
            self.assertFalse(output.exists())
            self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_cli_failure_only_publishes_sanitized_failure_report(self):
        error = collector.CollectionFailure([{"challenge_slug": "web-one", "error_code": "PUBLISH_NOT_CURRENT"}])
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "result"
            with patch.object(collector, "collect", side_effect=error), patch.object(collector.sys, "argv", ["tool", "--output-dir", str(output)]):
                self.assertEqual(collector.main(), 2)
            self.assertEqual({path.name for path in output.iterdir()}, {"failure-report.json", "summary.md"})
            self.assertFalse(json.loads((output / "failure-report.json").read_text())["complete"])

    def test_cli_missing_baseline_is_a_failure_not_an_initial_run(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "result"
            with patch.object(collector.sys, "argv", ["tool", "--output-dir", str(output), "--previous-plan", str(Path(temporary) / "missing.json")]):
                self.assertEqual(collector.main(), 2)
            self.assertFalse((output / "prefetch-inventory.json").exists())

    def test_success_cli_keeps_existing_node_and_runtime_out_of_scope(self):
        report, diff, files = make_report()
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "result"
            with patch.object(collector, "collect", return_value=(report, diff, files)), patch.object(collector.sys, "argv", ["tool", "--output-dir", str(output)]):
                self.assertEqual(collector.main(), 0)
            self.assertTrue((output / "summary.md").exists())
            self.assertNotIn("token", (output / "prefetch-inventory.json").read_text())

    def test_workflow_is_read_only_and_has_no_backend_or_runtime_credentials(self):
        workflow = yaml.load((ROOT / ".github/workflows/node-image-prefetch-plan.yml").read_text(), Loader=yaml.BaseLoader)
        self.assertEqual(set(workflow["on"]), {"workflow_call"})
        self.assertEqual(workflow["permissions"], {"contents": "read", "actions": "read"})
        self.assertNotIn("secrets", workflow["on"]["workflow_call"])
        text = str(workflow)
        for forbidden in ("RUNTIME_API_TOKEN", "packages: write", "id-token: write", "docker pull", "kubectl", "ssh ", "--method DELETE"):
            self.assertNotIn(forbidden, text)
        self.assertIn("github.token", text)
        self.assertIn("GITHUB_STEP_SUMMARY", text)
        self.assertIn("--expected-source-sha", text)

    def test_guard_executes_event_repository_branch_and_sha_checks(self):
        workflow = yaml.load((ROOT / ".github/workflows/node-image-prefetch-plan.yml").read_text(), Loader=yaml.BaseLoader)
        guard = workflow["jobs"]["plan"]["steps"][0]["run"]
        cases = ({}, {"GITHUB_EVENT_NAME": "push"}, {"GITHUB_REPOSITORY": "outside/repo"},
                 {"GITHUB_REF": "refs/heads/feature/test"}, {"DEVSECOPS_REF": "main"}, {"PREVIOUS_ARTIFACT_ID": "0"})
        for change in cases:
            env = {**os.environ, "GITHUB_REPOSITORY": collector.publication.REPOSITORY,
                   "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_REF": "refs/heads/main",
                   "DEVSECOPS_REF": SHA, "PREVIOUS_ARTIFACT_ID": "", **change}
            result = subprocess.run(["bash", "-c", guard], env=env, capture_output=True, timeout=10)
            with self.subTest(change=change):
                self.assertEqual(result.returncode == 0, not change)

    def test_new_workflow_changes_trigger_self_test_and_caller_uses_no_secrets(self):
        workflow = yaml.load((ROOT / ".github/workflows/pipeline-self-test.yml").read_text(), Loader=yaml.BaseLoader)
        for event in ("push", "pull_request"):
            self.assertIn(".github/workflows/node-image-prefetch-plan.yml", workflow["on"][event]["paths"])
        caller = yaml.load((ROOT / "docs/node-image-prefetch-caller-example.yml").read_text(), Loader=yaml.BaseLoader)
        self.assertEqual(set(caller["on"]), {"workflow_dispatch"})
        self.assertNotIn("secrets", caller["jobs"]["plan"])
        self.assertIn("previous_artifact_id", caller["jobs"]["plan"]["with"])

    def test_download_reads_only_one_bounded_json_without_extracting_zip(self):
        raw = io.BytesIO()
        with zipfile.ZipFile(raw, "w") as archive:
            archive.writestr("artifact-v2.json", json.dumps(artifact()))
            archive.writestr("../not-extracted", "unused")
        def run(*_, **kwargs):
            kwargs["stdout"].write(raw.getvalue())
            return subprocess.CompletedProcess([], 0)
        with patch.object(collector.subprocess, "run", side_effect=run):
            data, original = collector.download_json(200, "artifact-v2.json")
        self.assertEqual(data, artifact())
        self.assertEqual(json.loads(original), artifact())

    def test_corrupt_duplicate_and_oversized_manifest_are_rejected(self):
        archives = [b"not-a-zip"]
        for duplicate in (False, True):
            raw = io.BytesIO()
            with warnings.catch_warnings(), zipfile.ZipFile(raw, "w") as archive:
                warnings.simplefilter("ignore")
                archive.writestr("artifact-v2.json", "x" * 100)
                if duplicate:
                    archive.writestr("artifact-v2.json", "{}")
            archives.append(raw.getvalue())
        for raw in archives:
            def run(*_, **kwargs):
                kwargs["stdout"].write(raw)
                return subprocess.CompletedProcess([], 0)
            with self.subTest(size=len(raw)), patch.object(collector.subprocess, "run", side_effect=run), \
                    patch.object(collector, "MAX_ARTIFACT_BYTES", 32), \
                    self.assertRaises((ValueError, zipfile.BadZipFile)):
                collector.download_json(200, "artifact-v2.json")


if __name__ == "__main__":
    unittest.main()
