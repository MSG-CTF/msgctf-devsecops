import tempfile
import unittest
from pathlib import Path

from scripts.discover_changed_challenges import discover_changed_challenges


class DiscoverChangedChallengesTests(unittest.TestCase):
    def test_returns_changed_top_level_directories_that_contain_info_yaml(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for name in ("pwn-chall1", "web-chall1", "docs"):
                (root / name).mkdir()
            (root / "pwn-chall1" / "info.yaml").write_text("name: pwn\n")
            (root / "web-chall1" / "info.yaml").write_text("name: web\n")

            result = discover_changed_challenges(
                root,
                [
                    "README.md",
                    "pwn-chall1/prob/for_organizer/chall/Dockerfile",
                    "./web-chall1/info.yaml",
                    "docs/guide.md",
                    "../outside/info.yaml",
                ],
            )

        self.assertEqual(result, ["pwn-chall1", "web-chall1"])

    def test_rejects_unsafe_challenge_directory_name(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            challenge = root / "Pwn Chall"
            challenge.mkdir()
            (challenge / "info.yaml").write_text("name: pwn\n")

            result = discover_changed_challenges(
                root,
                ["Pwn Chall/info.yaml"],
            )

        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
