import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

from scripts.collect_user_files import collect_user_files


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "info-valid"


class CollectUserFilesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / "source"
        self.source.mkdir()
        self.output = self.root / "output"
        for slug in ("web-files", "web-empty", "crypto-files", "crypto-empty"):
            path = self.source / slug
            shutil.copytree(FIXTURE, path)
            info = yaml.safe_load((path / "info.yaml").read_text())
            if slug.startswith("crypto"):
                info.pop("deployment")
                info["category"] = "crypto"
            (path / "info.yaml").write_text(yaml.safe_dump(info))
            if slug.endswith("empty"):
                shutil.rmtree(path / "prob" / "for_user")
        self.git("init", "-b", "main")
        self.commit()

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.source), *args], check=True, capture_output=True, text=True).stdout.strip()

    def commit(self):
        self.git("add", ".")
        self.git("-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "test input")
        self.sha = self.git("rev-parse", "HEAD")
        self.git("update-ref", "refs/remotes/origin/main", self.sha)

    def test_collects_four_static_dynamic_file_cases_without_cloud_calls(self):
        report = collect_user_files(self.source, self.output, self.sha, 900)
        self.assertEqual(report["problem_count"], 4)
        self.assertEqual(report["with_files"], 2)
        self.assertEqual(report["without_files"], 2)
        self.assertEqual(sum(row["is_server"] for row in report["problems"]), 2)
        self.assertFalse(report["upload_complete"])
        for row in report["problems"]:
            manifest = json.loads((self.output / row["challenge_slug"] / "user-files.json").read_text())
            self.assertEqual(manifest["source_sha"], self.sha)
            self.assertEqual(manifest["registry_revision"], 900)
            self.assertEqual((self.output / row["challenge_slug"] / "user-files.zip").exists(), row["present"])

    def test_dirty_checkout_is_rejected(self):
        (self.source / "unexpected.txt").write_text("untracked input")
        with self.assertRaisesRegex(ValueError, "clean source"):
            collect_user_files(self.source, self.output, self.sha, 900)

    def test_wrong_source_sha_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "matching source_sha"):
            collect_user_files(self.source, self.output, "a" * 40, 900)

    def test_ignored_untracked_file_is_not_part_of_the_commit_snapshot(self):
        (self.source / ".gitignore").write_text("extra.bin\n")
        self.commit()
        (self.source / "web-files" / "prob" / "for_user" / "extra.bin").write_bytes(b"not committed")
        with self.assertRaisesRegex(ValueError, "clean source"):
            collect_user_files(self.source, self.output, self.sha, 900)

    def test_non_main_snapshot_is_rejected(self):
        self.git("update-ref", "-d", "refs/remotes/origin/main")
        with self.assertRaises(subprocess.CalledProcessError):
            collect_user_files(self.source, self.output, self.sha, 900)

    def test_output_inside_source_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "outside"):
            collect_user_files(self.source, self.source / "output", self.sha, 900)


if __name__ == "__main__":
    unittest.main()
