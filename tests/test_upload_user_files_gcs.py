import base64
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import yaml

from scripts.package_user_files import package_user_files
from scripts.upload_user_files_gcs import BUCKET, prepare_upload, upload_bundle


ROOT = Path(__file__).resolve().parents[1]
SHA = "a" * 40


class Conflict(Exception):
    code = 412


class FakeBlob:
    def __init__(self, bucket, key):
        self.bucket, self.key = bucket, key

    def upload_from_string(self, data, **kwargs):
        self.bucket.calls.append((self.key, kwargs))
        if self.bucket.fail_key == self.key:
            raise RuntimeError("sensitive authentication detail")
        if self.key in self.bucket.objects:
            raise Conflict()
        self.bucket.objects[self.key] = {
            "data": data, "metadata": self.metadata,
            "cache_control": self.cache_control, "generation": 1,
        }

    def reload(self, **kwargs):
        saved = self.bucket.objects[self.key]
        self.metadata = saved["metadata"]
        self.generation = saved["generation"]
        self.size = len(saved["data"])
        self.md5_hash = base64.b64encode(hashlib.md5(saved["data"]).digest()).decode()


class FakeBucket:
    def __init__(self):
        self.objects, self.calls, self.fail_key = {}, [], None

    def blob(self, key):
        return FakeBlob(self, key)


class GcsUserFilesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.challenge = self.root / "challenge"
        self.challenge.mkdir()
        self.bundle = self.root / "bundle"
        self.bucket = FakeBucket()
        self.client = SimpleNamespace(bucket=lambda name: self.bucket if name == BUCKET else None)

    def package(self, present=True, content=b"participant file", slug="web-example"):
        if present:
            files = self.challenge / "prob" / "for_user"
            files.mkdir(parents=True, exist_ok=True)
            (files / "sample.txt").write_bytes(content)
        return package_user_files(self.challenge, self.bundle, slug, "refs/heads/main", SHA, 500)

    def edit(self, change):
        path = self.bundle / "user-files.json"
        manifest = json.loads(path.read_text())
        change(manifest)
        path.write_text(json.dumps(manifest))

    def test_dry_run_never_contacts_storage(self):
        self.package()
        report = upload_bundle(self.bundle, client=SimpleNamespace(bucket=lambda name: self.fail("contacted GCS")))
        self.assertFalse(report["upload_complete"])
        self.assertEqual(report["mode"], "DRY_RUN")
        self.assertEqual(len(report["storage"]["objects"]), 2)
        self.assertNotIn("generation", report["storage"]["objects"][0])

    def test_upload_creates_zip_before_manifest_without_overwrite_or_public_acl(self):
        self.package()
        original = (self.bundle / "user-files.json").read_bytes()
        report = upload_bundle(self.bundle, client=self.client, apply=True)
        self.assertTrue(report["upload_complete"])
        self.assertTrue(self.bucket.calls[0][0].endswith("/user-files.zip"))
        self.assertTrue(self.bucket.calls[1][0].endswith("/user-files.json"))
        for key, args in self.bucket.calls:
            self.assertEqual(args["if_generation_match"], 0)
            self.assertEqual(args["checksum"], "crc32c")
            self.assertEqual(self.bucket.objects[key]["cache_control"], "private, no-store")
            self.assertIn(f"/revisions/500/{SHA}/", key)
        self.assertEqual(self.bucket.objects[self.bucket.calls[1][0]]["data"], original)

    def test_identical_retry_reuses_objects(self):
        self.package()
        upload_bundle(self.bundle, client=self.client, apply=True)
        report = upload_bundle(self.bundle, client=self.client, apply=True)
        self.assertEqual(len(self.bucket.objects), 2)
        self.assertEqual([item["status"] for item in report["storage"]["objects"]], ["REUSED", "REUSED"])

    def test_existing_different_object_is_not_overwritten(self):
        self.package()
        upload_bundle(self.bundle, client=self.client, apply=True)
        first = next(iter(self.bucket.objects))
        self.bucket.objects[first]["data"] = b"tampered"
        with self.assertRaisesRegex(ValueError, "conflicts"):
            upload_bundle(self.bundle, client=self.client, apply=True)
        self.assertEqual(self.bucket.objects[first]["data"], b"tampered")

    def test_partial_failure_does_not_publish_completion_manifest(self):
        self.package()
        _, objects = prepare_upload(self.bundle)
        self.bucket.fail_key = objects[0][0]
        with self.assertRaisesRegex(RuntimeError, "no completion receipt"):
            upload_bundle(self.bundle, client=self.client, apply=True)
        self.assertEqual(self.bucket.objects, {})

    def test_manifest_failure_allows_retry_of_already_stored_zip(self):
        self.package()
        _, objects = prepare_upload(self.bundle)
        self.bucket.fail_key = objects[1][0]
        with self.assertRaises(RuntimeError):
            upload_bundle(self.bundle, client=self.client, apply=True)
        self.assertEqual(len(self.bucket.objects), 1)
        self.bucket.fail_key = None
        report = upload_bundle(self.bundle, client=self.client, apply=True)
        self.assertEqual([item["status"] for item in report["storage"]["objects"]], ["REUSED", "CREATED"])

    def test_absent_files_upload_only_manifest(self):
        self.package(present=False, slug="crypto-static")
        report = upload_bundle(self.bundle, client=self.client, apply=True)
        self.assertEqual(report["user_files"], {"present": False})
        self.assertEqual(len(self.bucket.objects), 1)

    def test_empty_regular_file_can_be_uploaded(self):
        self.package(content=b"")
        self.assertTrue(upload_bundle(self.bundle, client=self.client, apply=True)["upload_complete"])

    def test_static_and_dynamic_slugs_use_same_storage_contract(self):
        for slug in ("web-example", "crypto-static"):
            with self.subTest(slug=slug):
                self.package(slug=slug)
                report = upload_bundle(self.bundle)
                self.assertIn(f"/{slug}/", report["storage"]["objects"][0]["object_key"])

    def test_archive_checksum_mismatch_blocks_all_uploads(self):
        self.package()
        (self.bundle / "user-files.zip").write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            upload_bundle(self.bundle, client=self.client, apply=True)
        self.assertEqual(self.bucket.calls, [])

    def test_archive_metadata_and_path_validation(self):
        changes = [
            lambda m: m["user_files"].update(archive="../outside.zip"),
            lambda m: m["user_files"].update(file_count=2),
            lambda m: m["user_files"].update(uncompressed_size_bytes=900),
            lambda m: m["user_files"].update(size_bytes=True),
            lambda m: m["user_files"].update(sha256="bad"),
            lambda m: m["user_files"].update(extra="secret"),
        ]
        for change in changes:
            with self.subTest(change=change):
                self.package()
                self.edit(change)
                with self.assertRaises(ValueError):
                    prepare_upload(self.bundle)

    def test_manifest_identity_validation(self):
        changes = [
            lambda m: m.update(challenge_slug="../evil"),
            lambda m: m.update(source_sha="main"),
            lambda m: m.update(registry_revision=True),
            lambda m: m.update(source_ref="refs/heads/feature"),
            lambda m: m.update(schema_version="2.0"),
            lambda m: m.update(flag="secret"),
            lambda m: m["user_files"].update(present="false"),
        ]
        for change in changes:
            with self.subTest(change=change):
                self.package()
                self.edit(change)
                with self.assertRaises(ValueError):
                    prepare_upload(self.bundle)

    def test_symlinked_bundle_and_parent_are_rejected(self):
        self.package()
        link = self.root / "linked"
        link.symlink_to(self.bundle, target_is_directory=True)
        parent = self.root / "linked-parent"
        parent.symlink_to(self.root, target_is_directory=True)
        for path in (link, parent / "bundle"):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "symbolic"):
                prepare_upload(path)

    def test_symlinked_archive_is_rejected(self):
        self.package()
        archive = self.bundle / "user-files.zip"
        data = archive.read_bytes()
        archive.unlink()
        target = self.root / "outside.zip"
        target.write_bytes(data)
        archive.symlink_to(target)
        with self.assertRaisesRegex(ValueError, "symbolic"):
            prepare_upload(self.bundle)

    def test_absent_manifest_rejects_stale_zip(self):
        self.package(present=False)
        (self.bundle / "user-files.zip").write_bytes(b"stale")
        with self.assertRaisesRegex(ValueError, "absent"):
            prepare_upload(self.bundle)

    def test_fake_zip_with_matching_sha_still_fails_validation(self):
        self.package()
        data = b"not a zip"
        (self.bundle / "user-files.zip").write_bytes(data)
        self.edit(lambda m: m["user_files"].update(size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest()))
        with self.assertRaisesRegex(ValueError, "ZIP"):
            prepare_upload(self.bundle)

    def test_cli_failure_clears_stale_receipt_and_redacts_input(self):
        self.package()
        self.edit(lambda m: m.update(flag="very-sensitive-input"))
        receipt = self.root / "receipt.json"
        receipt.write_text('{"upload_complete": true}')
        result = subprocess.run([sys.executable, "-m", "scripts.upload_user_files_gcs", "--bundle-dir", str(self.bundle), "--output", str(receipt)], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertFalse(receipt.exists())
        self.assertNotIn("very-sensitive-input", result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_gcs_workflow_is_opt_in_main_only_and_waits_for_image_gates(self):
        workflow = yaml.load((ROOT / ".github/workflows/challenge-supply-chain.yml").read_text(), Loader=yaml.BaseLoader)
        config = workflow["on"]["workflow_call"]["inputs"]["enable_user_files_gcs_upload"]
        self.assertEqual(config["default"], "false")
        job = workflow["jobs"]["upload-user-files-gcs"]
        self.assertEqual(job["permissions"], {"contents": "read", "id-token": "write"})
        self.assertEqual(job["environment"], "user-files-gcs")
        self.assertEqual(job["needs"], ["validate", "build-scan-push", "package-user-files"])
        for required in ("refs/heads/main", "MSG-CTF/2026_MSG_CTF", "needs.build-scan-push.result == 'success'", "needs.package-user-files.result == 'success'"):
            self.assertIn(required, job["if"])
        auth = next(step for step in job["steps"] if step.get("uses") == "google-github-actions/auth@v3")
        self.assertNotIn("credentials_json", auth["with"])
        self.assertIn("workload_identity_provider", auth["with"])
        self.assertNotIn("continue-on-error", job)
        self.assertNotIn("secrets", json.dumps(job))


if __name__ == "__main__":
    unittest.main()
