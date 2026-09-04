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
POLLER_CONTRACT_DOCUMENT = ROOT / "docs/challenge-registry-integration.md"


class BackendPollerDocumentationTests(unittest.TestCase):
    def test_documents_poller_without_direct_registry_push_settings(self):
        text = "\n".join(path.read_text(encoding="utf-8") for path in DOCUMENTS)
        for forbidden in (
            "publish_registry: true",
            "CHALLENGE_REGISTRY_URL",
            "CHALLENGE_REGISTRY_TOKEN",
            "Idempotency-Key",
        ):
            self.assertNotIn(forbidden, text)

    def test_challenge_registry_document_records_backend_poller_contracts(self):
        text = " ".join(POLLER_CONTRACT_DOCUMENT.read_text(encoding="utf-8").split())

        self.assertIn(
            "`artifact-v2.json`은 성공한 `-publish-bundle` Actions artifact에서 수집하는 공식 입력입니다.",
            text,
        )
        self.assertIn("수동 API 검증용 `registry-publish.json` wrapper", text)
        self.assertIn(
            "reusable workflow와 caller에는 Backend base URL, service token, 직접 전송이 없습니다.",
            text,
        )
        self.assertIn(
            "Backend 운영 환경의 `RELEASE_POLL_REPO`와 `RELEASE_POLL_GITHUB_TOKEN`은 Backend 팀이 관리합니다.",
            text,
        )
        self.assertIn("`registry_revision`의 중복 처리를 소유합니다.", text)
        self.assertIn("Backend/admin은 active release 전환과 롤백을 소유하고", text)
        self.assertIn("혼합 public/private port는 Runtime DTO가 확정될 때까지 손실 변환하지 않고 보존합니다.", text)
        self.assertIn("성공한 Actions artifact 수집", text)
        self.assertIn("최초 release 등록", text)
        self.assertIn("같은 `registry_revision`의 중복 재수집", text)
        self.assertIn("active release가 변하지 않음", text)


if __name__ == "__main__":
    unittest.main()
