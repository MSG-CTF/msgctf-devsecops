import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = (
    ROOT / "README.md",
    ROOT / ".github/workflows/README.md",
    ROOT / "ci/README.md",
    ROOT / "docs/README.md",
    ROOT / "docs/challenge-registry-integration.md",
    ROOT / "docs/devsecops-runbook.md",
    ROOT / "scripts/README.md",
)


class BackendPollerDocumentationTests(unittest.TestCase):
    def test_documents_poller_without_direct_registry_push_settings(self):
        text = "\n".join(path.read_text(encoding="utf-8") for path in DOCUMENTS)
        self.assertIn("Backend poller", text)
        self.assertIn("artifact-v2.json", text)
        for forbidden in (
            "publish_registry: true",
            "CHALLENGE_REGISTRY_URL",
            "CHALLENGE_REGISTRY_TOKEN",
            "Idempotency-Key",
        ):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
