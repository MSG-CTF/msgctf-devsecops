import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.package_user_files import package_user_files


SOURCE_REF = "refs/heads/main"
SOURCE_SHA = "1" * 40


class PackageUserFilesTests(unittest.TestCase):
    def test_packages_nested_files_and_writes_integrity_manifest(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for_user = root / "challenge" / "prob" / "for_user"
            (for_user / "docs").mkdir(parents=True)
            (for_user / "README.txt").write_text("hello\n", encoding="utf-8")
            (for_user / "docs" / "hint.png").write_bytes(b"PNG")

            manifest = package_user_files(
                root / "challenge",
                root / "dist",
                "web-example",
                SOURCE_REF,
                SOURCE_SHA,
                revision=3,
            )

            archive = root / "dist" / "user-files.zip"
            manifest_path = root / "dist" / "user-files.json"
            self.assertTrue(archive.is_file())
            self.assertTrue(manifest_path.is_file())
            self.assertEqual(json.loads(manifest_path.read_text()), manifest)
            self.assertEqual(manifest["schema_version"], "1.0")
            self.assertEqual(manifest["challenge_slug"], "web-example")
            self.assertEqual(manifest["source_ref"], SOURCE_REF)
            self.assertEqual(manifest["source_sha"], SOURCE_SHA)
            self.assertEqual(manifest["registry_revision"], 3)
            self.assertEqual(
                manifest["user_files"],
                {
                    "present": True,
                    "archive": "user-files.zip",
                    "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                    "size_bytes": archive.stat().st_size,
                    "file_count": 2,
                    "uncompressed_size_bytes": 9,
                },
            )
            with zipfile.ZipFile(archive) as packaged:
                self.assertEqual(
                    packaged.namelist(),
                    ["README.txt", "docs/hint.png"],
                )

    def test_writes_absent_manifest_when_for_user_does_not_exist(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "challenge").mkdir()

            manifest = package_user_files(
                root / "challenge",
                root / "dist",
                "crypto-static",
                SOURCE_REF,
                SOURCE_SHA,
                revision=1,
            )

            self.assertEqual(manifest["user_files"], {"present": False})
            self.assertFalse((root / "dist" / "user-files.zip").exists())
            self.assertTrue((root / "dist" / "user-files.json").is_file())

    def test_rejects_symbolic_links_inside_for_user(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for_user = root / "challenge" / "prob" / "for_user"
            for_user.mkdir(parents=True)
            target = for_user / "target.txt"
            target.write_text("participant file", encoding="utf-8")
            (for_user / "alias.txt").symlink_to(target)

            with self.assertRaisesRegex(ValueError, "symbolic link"):
                package_user_files(
                    root / "challenge",
                    root / "dist",
                    "web-example",
                    SOURCE_REF,
                    SOURCE_SHA,
                    revision=1,
                )

    def test_rejects_symbolic_linked_challenge_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            challenge = root / "challenge"
            (challenge / "prob" / "for_user").mkdir(parents=True)
            linked_challenge = root / "linked-challenge"
            linked_challenge.symlink_to(challenge, target_is_directory=True)

            with self.assertRaisesRegex(ValueError, "challenge root.*symbolic link"):
                package_user_files(
                    linked_challenge,
                    root / "dist",
                    "web-example",
                    SOURCE_REF,
                    SOURCE_SHA,
                    revision=1,
                )

    def test_rejects_symbolic_linked_prob_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            challenge = root / "challenge"
            challenge.mkdir()
            outside_prob = root / "outside-prob"
            (outside_prob / "for_user").mkdir(parents=True)
            (outside_prob / "for_user" / "secret.txt").write_text(
                "secret",
                encoding="utf-8",
            )
            (challenge / "prob").symlink_to(outside_prob, target_is_directory=True)

            with self.assertRaisesRegex(ValueError, "prob.*symbolic link"):
                package_user_files(
                    challenge,
                    root / "dist",
                    "web-example",
                    SOURCE_REF,
                    SOURCE_SHA,
                    revision=1,
                )

    def test_rejects_file_that_resolves_outside_challenge_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for_user = root / "challenge" / "prob" / "for_user"
            for_user.mkdir(parents=True)
            outside = root / "secret.txt"
            outside.write_text("secret", encoding="utf-8")
            (for_user / "escape.txt").symlink_to(outside)

            with self.assertRaisesRegex(ValueError, "stay inside challenge root"):
                package_user_files(
                    root / "challenge",
                    root / "dist",
                    "web-example",
                    SOURCE_REF,
                    SOURCE_SHA,
                    revision=1,
                )

    def test_rejects_file_count_over_limit(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for_user = root / "challenge" / "prob" / "for_user"
            for_user.mkdir(parents=True)
            (for_user / "one.txt").write_text("1", encoding="utf-8")
            (for_user / "two.txt").write_text("2", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "file count"):
                package_user_files(
                    root / "challenge",
                    root / "dist",
                    "web-example",
                    SOURCE_REF,
                    SOURCE_SHA,
                    revision=1,
                    max_files=1,
                )

    def test_rejects_uncompressed_size_over_limit(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for_user = root / "challenge" / "prob" / "for_user"
            for_user.mkdir(parents=True)
            (for_user / "large.bin").write_bytes(b"12345")

            with self.assertRaisesRegex(ValueError, "total size"):
                package_user_files(
                    root / "challenge",
                    root / "dist",
                    "web-example",
                    SOURCE_REF,
                    SOURCE_SHA,
                    revision=1,
                    max_total_bytes=4,
                )

    def test_rejects_non_positive_registry_revision(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "challenge").mkdir()

            with self.assertRaisesRegex(ValueError, "revision"):
                package_user_files(
                    root / "challenge",
                    root / "dist",
                    "web-example",
                    SOURCE_REF,
                    SOURCE_SHA,
                    revision=0,
                )


if __name__ == "__main__":
    unittest.main()
