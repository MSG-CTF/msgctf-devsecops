import unittest

from scripts.render_publish_summary import render_summary


DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64


class RenderPublishSummaryTests(unittest.TestCase):
    def test_renders_digest_images_and_bundle_name(self):
        artifact = {
            "challenge_slug": "web-notebook",
            "category": "web",
            "revision": 7,
            "registry_revision": 7,
            "isolation_profile": "WEB",
            "scan_result": "PASS",
            "evidence": {
                "containers": [
                    {
                        "name": "web",
                        "timing": {
                            "build_seconds": 2.5,
                            "scan_seconds": 5.25,
                            "push_seconds": 1.75,
                            "total_seconds": 9.5,
                        },
                    },
                    {
                        "name": "db",
                        "timing": {
                            "build_seconds": 1.0,
                            "scan_seconds": 2.0,
                            "push_seconds": 3.0,
                            "total_seconds": 6.0,
                        },
                    },
                ]
            },
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
        self.assertIn("registry revision: `7`", summary)
        self.assertIn("격리 프로파일: `WEB`", summary)
        self.assertIn("| web |", summary)
        self.assertIn(DIGEST_A, summary)
        self.assertIn("| db |", summary)
        self.assertIn(DIGEST_B, summary)
        self.assertIn("| 컨테이너 | Build/Pull | Scan | GHCR Push | Total |", summary)
        self.assertIn("| web | `2.50s` | `5.25s` | `1.75s` | `9.50s` |", summary)

    def test_rejects_tag_only_image(self):
        artifact = {
            "challenge_slug": "web-notebook",
            "category": "web",
            "revision": 7,
            "registry_revision": 7,
            "isolation_profile": "WEB",
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

    def test_rejects_digest_image_outside_msg_ctf_ghcr(self):
        artifact = {
            "challenge_slug": "web-notebook",
            "category": "web",
            "revision": 7,
            "registry_revision": 7,
            "isolation_profile": "WEB",
            "scan_result": "PASS",
            "workload": {
                "containers": [
                    {
                        "name": "web",
                        "image": f"registry.internal/challenges/web@{DIGEST_A}",
                    }
                ]
            },
        }

        with self.assertRaisesRegex(ValueError, "MSG-CTF GHCR"):
            render_summary(artifact, "web-notebook-publish-bundle")

    def test_rejects_registry_revision_mismatch(self):
        artifact = {
            "challenge_slug": "web-notebook",
            "category": "web",
            "revision": 7,
            "registry_revision": 8,
            "isolation_profile": "WEB",
            "scan_result": "PASS",
            "workload": {"containers": []},
        }

        with self.assertRaisesRegex(ValueError, "registry_revision"):
            render_summary(artifact, "web-notebook-publish-bundle")

    def test_rejects_boolean_registry_revision(self):
        artifact = {
            "challenge_slug": "web-notebook",
            "category": "web",
            "revision": 1,
            "registry_revision": True,
            "isolation_profile": "WEB",
            "scan_result": "PASS",
            "workload": {"containers": []},
        }

        with self.assertRaisesRegex(ValueError, "registry_revision"):
            render_summary(artifact, "web-notebook-publish-bundle")

    def test_rejects_isolation_profile_that_does_not_match_category(self):
        artifact = {
            "challenge_slug": "pwn-example",
            "category": "pwn",
            "revision": 1,
            "registry_revision": 1,
            "isolation_profile": "WEB",
            "scan_result": "PASS",
            "workload": {"containers": []},
        }

        with self.assertRaisesRegex(ValueError, "challenge category"):
            render_summary(artifact, "pwn-example-publish-bundle")


if __name__ == "__main__":
    unittest.main()
