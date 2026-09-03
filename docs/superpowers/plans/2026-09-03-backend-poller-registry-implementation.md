# Backend Poller Registry Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** DevSecOps 공급망이 Backend API를 직접 호출하지 않고, Backend poller가 소비할 `artifact-v2.json` publish bundle을 정확히 발행하도록 PR #7을 수정한다.

**Architecture:** 문제 저장소의 GitHub Actions는 검증된 image를 GHCR digest로 고정하고 `artifact-v2.json`, `registry-publish.json`, SBOM과 검사 증거를 Actions artifact로 업로드한다. Backend poller가 이름이 `-publish-bundle`로 끝나는 artifact를 내려받아 release를 등록하며, 중복 처리와 active release 전환은 Backend가 소유한다.

**Tech Stack:** GitHub Actions reusable workflow, Python 3 표준 라이브러리, `unittest`, Docker/Buildx, GHCR, Gitleaks, Trivy, CycloneDX SBOM

**Spec:** `docs/superpowers/specs/2026-09-03-backend-poller-registry-design.md`

## Global Constraints

- `artifact-v2.json`의 `schema_version`, `registry_revision`, `containers`, digest image, `scan_result` 계약을 유지한다.
- GitHub Actions에서 Backend Release API를 직접 호출하지 않는다.
- `registry-publish.json`은 수동 호환성 검증용 `{"artifact": <artifact-v2>}` wrapper만 제공한다.
- CI는 release를 활성화하지 않는다. active release 전환과 롤백은 Backend 또는 관리자가 담당한다.
- Runtime, Scheduler, Resource Broker 저장소의 코드는 수정하지 않는다.
- 포트별 `public` 정보는 artifact에서 손실 없이 보존한다. 현재 Runtime이 표현하지 못하는 혼합 노출 포트는 임의 변환하지 않는다.
- 기존 GHCR build-once, scan, push와 K3s smoke 경로는 직접 Registry API 제거 때문에 깨지지 않아야 한다.

---

## Task 1: Backend poller용 publish 문서 생성

**Files:**
- Modify: `tests/test_generate_publish_bundle.py`
- Modify: `scripts/generate_publish_bundle.py`

**Interface:**

```python
def generate_bundle(
    metadata: dict,
    results: list[dict],
    source_ref: str,
    revision: int,
    evidence_root: Path,
) -> dict:
    """Return artifact-v2 and its Backend request wrapper."""
```

반환값은 아래 관계를 만족해야 한다.

```python
bundle["registry_publish"] == {"artifact": bundle["artifact"]}
```

- [ ] **Step 1: 기존 flat publish 문서를 거절하는 테스트 작성**

`test_generates_runtime_artifact_and_registry_publish_document`를 다음 계약으로 바꾼다.

```python
artifact = bundle["artifact"]
publish = bundle["registry_publish"]
self.assertEqual(publish, {"artifact": artifact})
for forbidden in ("activate", "operation", "preconditions", "retention"):
    self.assertNotIn(forbidden, publish)
```

`internal_connections`와 `isolation_profile` 테스트도 `registry_publish["artifact"]`를 통해 같은 artifact를 검사하게 변경한다.

- [ ] **Step 2: 변경한 테스트가 기존 구현에서 실패하는지 확인**

Run:

```bash
python3 -m unittest tests.test_generate_publish_bundle -v
```

Expected: 기존 `registry_publish`가 flat object이고 `operation`, `activate`를 포함하므로 FAIL.

- [ ] **Step 3: generator를 최소 변경으로 수정**

`artifact`를 한 번만 만든 뒤 아래처럼 wrapper를 생성한다.

```python
registry_publish = {"artifact": artifact}
return {"artifact": artifact, "registry_publish": registry_publish}
```

기존 digest, SBOM, timing, scan 검증은 변경하지 않는다.

- [ ] **Step 4: generator 테스트 통과 확인**

Run:

```bash
python3 -m unittest tests.test_generate_publish_bundle -v
```

Expected: 모든 generator 테스트 PASS.

- [ ] **Step 5: 변경 커밋**

```bash
git add scripts/generate_publish_bundle.py tests/test_generate_publish_bundle.py
git commit -m "Backend poller publish wrapper 계약 반영"
```

---

## Task 2: reusable workflow에서 Backend 직접 호출 제거

**Files:**
- Modify: `tests/test_workflow_contracts.py`
- Modify: `.github/workflows/challenge-supply-chain.yml`

**Workflow contract:**

- 입력에는 `challenge_path`, `revision`, `devsecops_ref`, `publish_images`, `enable_k3s_smoke_deploy`, `runtime_target_id`만 사용한다.
- `workflow_call.secrets`에는 Runtime/K3s smoke에 필요한 AWS secret과 기존 caller 호환용 `GHCR_PULL_SECRET_ARN`만 남긴다.
- job은 검증, build/scan/push, bundle 집계, 선택형 K3s smoke로 구성한다.
- bundle artifact 이름은 `${challenge_slug}-${artifact_scope}-publish-bundle` 형식을 유지한다.

- [ ] **Step 1: 직접 API 호출이 없어야 한다는 계약 테스트 작성**

`test_challenge_supply_chain_has_required_contract`에서 아래를 검증하도록 변경한다.

```python
self.assertNotIn("publish_registry", workflow["on"]["workflow_call"]["inputs"])
self.assertNotIn("publish-registry", workflow["jobs"])
self.assertNotIn("CHALLENGE_REGISTRY_TOKEN", workflow["on"]["workflow_call"].get("secrets", {}))
self.assertNotIn("CHALLENGE_REGISTRY_URL", workflow["on"]["workflow_call"].get("secrets", {}))
for forbidden in ("Authorization: Bearer", "Idempotency-Key:", "curl --fail-with-body"):
    self.assertNotIn(forbidden, text)
self.assertIn("${{ needs.validate.outputs.artifact_scope }}-publish-bundle", text)
```

branch validation 조건 테스트의 job 목록은 `aggregate`, `k3s-smoke-deploy`만 검사하게 수정한다.

- [ ] **Step 2: 변경한 workflow 계약 테스트가 실패하는지 확인**

Run:

```bash
python3 -m unittest tests.test_workflow_contracts.WorkflowContractTests.test_challenge_supply_chain_has_required_contract -v
python3 -m unittest tests.test_workflow_contracts.WorkflowContractTests.test_branch_validation_can_disable_all_publish_and_deploy_steps -v
```

Expected: `publish_registry`, Registry secret, `publish-registry` job이 남아 있어 FAIL.

- [ ] **Step 3: reusable workflow 최소 수정**

`.github/workflows/challenge-supply-chain.yml`에서 다음을 제거한다.

- `publish_registry` input
- `CHALLENGE_REGISTRY_TOKEN`, `CHALLENGE_REGISTRY_URL` secrets
- `publish-registry` job 전체
- `Authorization`, `Idempotency-Key`, `curl` 기반 Backend 전송 코드

`aggregate` job의 publish bundle 업로드와 `k3s-smoke-deploy` job은 유지한다.

- [ ] **Step 4: workflow 계약 테스트 통과 확인**

Run:

```bash
python3 -m unittest tests.test_workflow_contracts -v
```

Expected: workflow 계약 테스트 PASS.

- [ ] **Step 5: 변경 커밋**

```bash
git add .github/workflows/challenge-supply-chain.yml tests/test_workflow_contracts.py
git commit -m "Backend poller 중심 release 등록 흐름 적용"
```

---

## Task 3: 문제 저장소 caller 예시에서 Registry push 설정 제거

**Files:**
- Modify: `docs/challenge-caller-example.yml`
- Modify: `.github/workflows/pipeline-self-test.yml`
- Modify: `tests/test_workflow_contracts.py`

- [ ] **Step 1: caller와 self-test의 새 계약을 테스트에 반영**

caller 테스트에서 `publish-main.with`에 `publish_registry`가 없고 secret mapping에 Registry URL/token이 없음을 검증한다.

```python
self.assertNotIn("publish_registry", publish["with"])
self.assertEqual(
    set(publish["secrets"]),
    {
        "AWS_ROLE_TO_ASSUME",
        "AWS_REGION",
        "AWS_K3S_INSTANCE_ID",
        "AWS_CD_ARTIFACT_BUCKET",
    },
)
```

self-test 테스트에서는 `publish_registry: false` 문자열 요구를 제거하고, self-test workflow에도 해당 입력이 없음을 검증한다.

- [ ] **Step 2: caller 계약 테스트 실패 확인**

Run:

```bash
python3 -m unittest tests.test_workflow_contracts.WorkflowContractTests.test_caller_example_separates_branch_validation_from_main_publish -v
python3 -m unittest tests.test_workflow_contracts.WorkflowContractTests.test_pipeline_self_test_calls_reusable_supply_chain -v
```

Expected: 예시와 self-test에 기존 `publish_registry` 설정이 남아 있어 FAIL.

- [ ] **Step 3: caller 예시와 self-test 수정**

`docs/challenge-caller-example.yml`에서 아래 항목을 제거한다.

```yaml
publish_registry: ${{ vars.ENABLE_CHALLENGE_REGISTRY == 'true' }}
CHALLENGE_REGISTRY_TOKEN: ${{ secrets.CHALLENGE_REGISTRY_TOKEN }}
CHALLENGE_REGISTRY_URL: ${{ secrets.CHALLENGE_REGISTRY_URL }}
```

`.github/workflows/pipeline-self-test.yml`의 reusable workflow 호출에서 `publish_registry: false`를 제거한다.

- [ ] **Step 4: caller와 전체 workflow 테스트 통과 확인**

Run:

```bash
python3 -m unittest tests.test_workflow_contracts -v
```

Expected: 모든 workflow 계약 테스트 PASS.

- [ ] **Step 5: 변경 커밋**

```bash
git add docs/challenge-caller-example.yml .github/workflows/pipeline-self-test.yml tests/test_workflow_contracts.py
git commit -m "문제 저장소 caller를 poller 방식으로 정리"
```

---

## Task 4: 문서에서 파트 간 책임과 운영 절차 정리

**Files:**
- Create: `tests/test_backend_poller_documentation.py`
- Modify: `README.md`
- Modify: `.github/workflows/README.md`
- Modify: `ci/README.md`
- Modify: `docs/README.md`
- Modify: `docs/challenge-registry-integration.md`
- Modify: `docs/devsecops-runbook.md`
- Modify: `scripts/README.md`

**Documented ownership:**

```text
DevSecOps: artifact-v2.json과 GHCR digest image 발행
Backend poller: Actions artifact 수집, challenge 매핑, release 등록, duplicate 처리
Backend/admin: active release 전환과 롤백
Runtime/Secure Provisioner: active workload의 K3s 배포와 cleanup
```

- [ ] **Step 1: 오래된 직접 push 안내를 탐지하는 문서 테스트 작성**

`tests/test_backend_poller_documentation.py`를 추가한다.

```python
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
```

- [ ] **Step 2: 문서 테스트 실패 확인**

Run:

```bash
python3 -m unittest tests.test_backend_poller_documentation -v
```

Expected: 기존 문서에 직접 API 전송용 URL, token, `Idempotency-Key` 안내가 있어 FAIL.

- [ ] **Step 3: 문서를 Backend poller 방식으로 갱신**

문서에 다음 내용을 일관되게 반영한다.

- `artifact-v2.json`이 자동 수집의 공식 입력이다.
- `registry-publish.json`은 동일 artifact를 감싼 수동 API 검증용 wrapper다.
- DevSecOps workflow에는 Backend base URL 또는 service token이 필요하지 않다.
- Backend 운영 환경의 `RELEASE_POLL_REPO`, `RELEASE_POLL_GITHUB_TOKEN`은 Backend 팀이 관리한다.
- 동일 `registry_revision`의 중복 수집과 active release 전환은 Backend가 처리한다.
- 혼합 public/private 포트는 Runtime DTO 확정 전까지 손실 변환하지 않는다.
- 실제 poller 통합 완료 증거는 Actions artifact 수집, 최초 등록, 중복 재수집, active 미변경을 함께 확인해야 한다.

`docs/challenge-registry-integration.md`의 과거 직접 API 연결 전제와 service token 대기 항목을 poller 기반 통합 상태로 교체한다. 과거 로컬 등록 결과는 호환성 증거로 남기되 운영 연결 완료로 표현하지 않는다.

- [ ] **Step 4: 문서 테스트와 전체 테스트 통과 확인**

Run:

```bash
python3 -m unittest tests.test_backend_poller_documentation -v
python3 -m unittest discover -s tests -v
```

Expected: 문서 계약과 전체 unit test PASS.

- [ ] **Step 5: 변경 커밋**

```bash
git add README.md .github/workflows/README.md ci/README.md docs/README.md docs/challenge-registry-integration.md docs/devsecops-runbook.md scripts/README.md tests/test_backend_poller_documentation.py
git commit -m "Backend poller 운영 계약 문서화"
```

---

## Task 5: 전체 검증과 PR #7 갱신

**Files:**
- Verify: `.github/workflows/challenge-supply-chain.yml`
- Verify: `scripts/generate_publish_bundle.py`
- Verify: `tests/`
- Verify: documentation files from Task 4

- [ ] **Step 1: Python 전체 테스트 실행**

Run:

```bash
python3 -W error::ResourceWarning -m unittest discover -s tests -v
```

Expected: 모든 테스트 PASS, warning 없음.

- [ ] **Step 2: Python 문법과 diff 검사**

Run:

```bash
python3 -m py_compile scripts/*.py
git diff --check
```

Expected: 출력 없이 exit code 0.

- [ ] **Step 3: repository secret scan 실행**

Run:

```bash
gitleaks detect --source . --no-banner --redact --exit-code 1
```

Expected: leak 없음, exit code 0.

- [ ] **Step 4: 운영 workflow와 문서의 오래된 설정 잔존 여부 확인**

Run:

```bash
rg -n "publish_registry|CHALLENGE_REGISTRY_URL|CHALLENGE_REGISTRY_TOKEN|Idempotency-Key|activate: true" \
  .github README.md ci docs scripts tests \
  -g '!docs/superpowers/**'
```

Expected: 운영 workflow와 사용자 문서에서는 결과가 없어야 한다. 테스트의 금지 문자열 목록만 결과에 나타날 수 있다.

- [ ] **Step 5: 생성 결과의 wrapper 관계 확인**

테스트 fixture로 bundle을 생성하는 계약 테스트를 단독 실행한다.

Run:

```bash
python3 -m unittest tests.test_generate_publish_bundle.GeneratePublishBundleTests.test_generates_runtime_artifact_and_registry_publish_document -v
```

이 테스트는 아래 조건을 검사한다.

```python
registry_publish == {"artifact": artifact_v2}
artifact_v2["scan_result"] == "PASS"
all("@sha256:" in item["image"] for item in artifact_v2["workload"]["containers"])
```

Expected: wrapper 동일성, PASS gate, digest 고정 모두 충족.

- [ ] **Step 6: 최종 수정 커밋과 원격 branch push**

검증이 실패하면 해당 Task로 돌아가 수정, targeted test와 전체 검증을 다시 통과시킨 뒤 그 Task의 파일 목록으로 커밋한다. 모든 검증이 통과하면 작업 상태를 확인하고 branch를 push한다.

```bash
git status --short
git push -u msg-ctf registry-integration
```

- [ ] **Step 7: PR #7에 검증 결과 공유**

PR comment에 아래 내용을 기록한다.

- Backend 직접 API push 제거
- `artifact-v2.json` publish bundle이 poller의 공식 입력임
- `registry-publish.json`은 `{"artifact": ...}` wrapper임
- 실행한 테스트와 결과
- active 전환은 Backend 소유임
- 혼합 포트는 Runtime 계약 확정이 필요한 별도 항목임

PR은 리뷰 전 자동 merge하지 않는다.

---

## 완료 기준

- reusable workflow가 Backend URL/token 없이 publish bundle을 발행한다.
- publish bundle artifact 이름이 `-publish-bundle`로 끝난다.
- `artifact-v2.json`에 `registry_revision`, 전체 `containers`, digest 고정 GHCR image가 포함된다.
- `registry-publish.json`이 Backend PR #26 요청 wrapper와 일치한다.
- release 자동 활성화와 직접 API 호출 코드가 없다.
- 전체 unit test, Python 문법 검사, diff 검사, Gitleaks가 통과한다.
- PR #7에 변경 이유와 검증 결과가 남고 리뷰 가능한 상태가 된다.

## 후속 통합 검증

Backend PR #26이 poller 포함 상태로 배포된 환경에서 Backend 팀과 다음 네 가지를 공동 확인한다.

1. 실제 Actions publish bundle 한 건이 자동 수집되어 release로 등록된다.
2. 같은 bundle을 다시 수집하면 duplicate로 처리되고 poll 전체는 실패하지 않는다.
3. 등록 직후 active release는 자동 변경되지 않는다.
4. Backend/admin이 활성화한 release의 `release_id`와 digest가 인스턴스 생성 요청까지 동일하게 전달된다.

Runtime 팀이 포트별 공개 여부를 표현하는 DTO를 확정하면 PR #6에서 exact `(container_name, port)` endpoint set 검증과 실제 K3s cold pull, 인증 실패, `ImagePullBackOff`, cleanup 증거를 별도로 수행한다.
