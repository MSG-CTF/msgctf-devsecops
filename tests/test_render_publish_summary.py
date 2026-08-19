import unittest

from scripts.render_publish_summary import render_summary


DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64


class RenderPublishSummaryTests(unittest.TestCase):
    def test_renders_digest_images_and_bundle_name(self):
        artifact = {
            "challenge_slug": "web-notebook",
            "revision": 7,
            "scan_result": "PASS",
            "workload": {
                "containers": [
                    {
                        "name": "web",
                        "image": f"ghcr.io/msg-ctf/challenges/web-notebook/web@{DIGEST_A}",
                    },
                    {
                        "name": "db",
                        "image": f"ghcr.io/msg-ctf/challenges/web-notebook/db@{DIGEST_B}",
                    },
                ]
            },
        }

        summary = render_summary(artifact, "web-notebook-publish-bundle")

        self.assertIn("# 문제 이미지 발행 결과", summary)
        self.assertIn("`web-notebook-publish-bundle`", summary)
        self.assertIn("| web |", summary)
        self.assertIn(DIGEST_A, summary)
        self.assertIn("| db |", summary)
        self.assertIn(DIGEST_B, summary)

    def test_rejects_tag_only_image(self):
        artifact = {
            "challenge_slug": "web-notebook",
            "revision": 7,
            "scan_result": "PASS",
            "workload": {
                "containers": [
                    {
                        "name": "web",
                        "image": "ghcr.io/msg-ctf/challenges/web-notebook/web:latest",
                    }
                ]
            },
        }

        with self.assertRaisesRegex(ValueError, "digest-pinned"):
            render_summary(artifact, "web-notebook-publish-bundle")


if __name__ == "__main__":
    unittest.main()
