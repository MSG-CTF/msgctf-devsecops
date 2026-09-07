# Runtime Exposed Ports Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `artifact-v2.json`의 포트별 공개 정보를 Runtime PR #39의 `ports`와 `exposed_ports` 요청 계약으로 손실 없이 변환하고 검증한다.

**Architecture:** Backend가 소비하는 publish bundle 형식은 변경하지 않는다. `runtime_api_smoke_runner.py`가 bundle 경계에서 전체 포트와 공개 포트를 분리해 Runtime 요청을 만들고, 기존 endpoint 집합 검증과 cleanup을 유지한다. 실제 K3s 호출은 service token을 받은 뒤 별도 실행한다.

**Tech Stack:** Python 3 표준 라이브러리, `unittest`, GitHub Actions, Secure Provisioner HTTP API.

**Spec:** `docs/superpowers/specs/2026-09-07-runtime-exposed-ports-integration-design.md`

## Global Constraints

- Runtime 요청의 한 컨테이너에는 `expose`와 `exposed_ports`를 함께 보내지 않는다.
- Runtime 요청의 `ports`는 전체 포트이며 `exposed_ports`는 public 포트 부분집합이다.
- `artifact-v2.json`의 `ports[].public` 형식은 유지한다.
- `target_id`는 bundle에 넣지 않고 workflow 입력으로 전달한다.
- Runtime과 Backend 저장소 코드는 수정하지 않는다.
- 실제 service token이 없으므로 K3s 실행을 완료로 표시하지 않는다.

---

### Task 1: Runtime 요청 포트 변환

**Files:**
- Modify: `tests/test_runtime_api_smoke_runner.py`
- Modify: `scripts/runtime_api_smoke_runner.py`

**Interfaces:**
- Consumes: `build_create_request(artifact, target_id, instance_id, team_id)`와 bundle의 `workload.containers[].ports[]`.
- Produces: Runtime 컨테이너 `{name, image, ports, exposed_ports, run_as_user}`.

- [x] **Step 1: 혼합 포트와 private 컨테이너의 실패 테스트 작성**

  기존 request 예상값에서 `expose`를 제거하고 `exposed_ports`를 요구한다. 별도 테스트는
  같은 컨테이너의 `8080 public`, `9000 private`가
  `ports: [8080, 9000]`, `exposed_ports: [8080]`로 변환되는지 확인한다. private DB는
  `exposed_ports: []`를 확인한다.

- [x] **Step 2: 테스트 실패 확인**

  Run: `python3 -m unittest tests.test_runtime_api_smoke_runner.RuntimeApiSmokeRunnerTests.test_builds_runtime_team_multi_container_contract tests.test_runtime_api_smoke_runner.RuntimeApiSmokeRunnerTests.test_builds_mixed_public_private_ports_with_exposed_ports -v`

  Expected: 기존 구현이 `expose`를 반환하고 혼합 포트를 거절해 FAIL.

- [x] **Step 3: 최소 변환 구현**

  `public_values`와 혼합 포트 거절을 제거한다. 각 port object를 검증하면서 전체 `ports`와
  `public: true`인 `exposed_ports`를 따로 누적하고 Runtime container에 두 배열을 넣는다.
  workload 전체 공개 여부는 `bool(exposed_ports)`로 계산한다.

- [x] **Step 4: 대상 테스트 통과 확인**

  Run: `python3 -m unittest tests.test_runtime_api_smoke_runner.RuntimeApiSmokeRunnerTests.test_builds_runtime_team_multi_container_contract tests.test_runtime_api_smoke_runner.RuntimeApiSmokeRunnerTests.test_builds_mixed_public_private_ports_with_exposed_ports -v`

  Expected: PASS.

- [x] **Step 5: 포트 변환 변경 커밋**

  ```bash
  git add scripts/runtime_api_smoke_runner.py tests/test_runtime_api_smoke_runner.py
  git commit -m "Runtime exposed_ports 계약 반영"
  ```

### Task 2: 연결 정보와 endpoint 회귀 검증

**Files:**
- Modify: `tests/test_runtime_api_smoke_runner.py`

**Interfaces:**
- Consumes: Task 1의 Runtime request와 기존 `run_smoke` endpoint 검증.
- Produces: `web -> db:5432/TCP`가 유지되고 공개 endpoint만 기대하는 회귀 테스트.

- [x] **Step 1: web과 db의 실제 계약 테스트 작성**

  web은 `8080 public`, `9000 private`, db는 `5432 private`로 구성하고
  `web -> db:5432/TCP`를 넣는다. 생성 요청에서 `expose`가 어느 컨테이너에도 없고,
  web `exposed_ports == [8080]`, db `exposed_ports == []`, 연결 배열이 원형 보존되는지
  확인한다.

- [x] **Step 2: endpoint 누락·추가·중복 실패 테스트 작성**

  현재 runner가 endpoint 배열이 비어 있지 않은지만 검사하는 반례를 먼저 재현한다.
  artifact의 공개 `(container_name, port)` 집합과 Runtime 응답의 집합이 다르거나,
  endpoint 항목이 중복되면 cleanup 후 실패하는 테스트를 추가한다.

- [x] **Step 3: endpoint 정확 일치 검증 구현**

  request의 `exposed_ports`에서 예상 집합을 만들고 Runtime 응답 각 항목의 필수 필드와
  중복을 검증한다. 실제 집합이 예상 집합과 다르면 cleanup 후 오류를 반환한다.

- [x] **Step 4: Runtime smoke runner 테스트 실행**

  Run: `python3 -m unittest tests.test_runtime_api_smoke_runner -v`

  Expected: 모든 Runtime smoke runner 테스트 PASS. endpoint 불일치 테스트는 내부적으로
  오류와 cleanup을 기대하므로 테스트 자체는 PASS.

- [x] **Step 5: 회귀 테스트 커밋**

  ```bash
  git add tests/test_runtime_api_smoke_runner.py
  git commit -m "Runtime 멀티 컨테이너 연결 회귀 검증"
  ```

### Task 3: 운영 문서와 target 계약 정리

**Files:**
- Modify: `docs/aws-k3s-cd-smoke.md`
- Modify: PR #6 description after push.

**Interfaces:**
- Consumes: Runtime PR #39의 `exposed_ports` 계약과 운영 target `aws-k3s-lab`.
- Produces: 토큰 준비 전후를 구분한 실행 안내.

- [x] **Step 1: 문서 수정**

  caller 예시의 `runtime_target_id`를 `aws-k3s-lab`으로 바꾼다. 혼합 포트 거절 제약을
  제거하고 `ports[].public`이 Runtime `exposed_ports`로 변환되며 `expose`를 보내지
  않는다고 설명한다. service token 미수령으로 실제 K3s smoke가 미실행임을 명시한다.

- [x] **Step 2: 문서 계약 검사**

  Run: `rg -n "aws-k3s-lab|exposed_ports|실제 K3s" docs/aws-k3s-cd-smoke.md`

  Expected: 세 계약이 문서에 존재하며 기존 “혼합 포트 거절” 설명은 없음.

- [x] **Step 3: 문서 커밋**

  ```bash
  git add docs/aws-k3s-cd-smoke.md
  git commit -m "Runtime 포트별 공개 smoke 문서화"
  ```

### Task 4: 전체 검증과 PR #6 갱신

**Files:**
- Verify: `scripts/*.py`
- Verify: `tests/`
- Update: `MSG-CTF/msgctf-devsecops` PR #6 metadata.

**Interfaces:**
- Consumes: Tasks 1-3의 코드·테스트·문서.
- Produces: 검증된 PR #6 커밋과 정확한 미완료 항목.

- [x] **Step 1: 전체 단위 테스트 실행**

  Run: `python3 -W error::ResourceWarning -m unittest discover -s tests -v`

  Expected: PASS.

- [x] **Step 2: 정적 검증 실행**

  Run: `python3 -m py_compile scripts/*.py`

  Run: `git diff --check`

  Run: `gitleaks detect --source . --no-banner --redact --exit-code 1`

  Expected: 모두 exit code 0.

- [ ] **Step 3: 브랜치 push**

  Run: `git push msg-ctf runtime-smoke-evidence`

  Expected: PR #6 head가 새 커밋으로 갱신됨.

- [ ] **Step 4: PR 설명과 댓글 갱신**

  PR #6에 Runtime PR #39 계약 반영, `target_id=aws-k3s-lab`, Backend PR #62 호환,
  service token 미수령 때문에 실제 K3s smoke는 남아 있다는 사실을 기록한다.

- [ ] **Step 5: GitHub Actions 결과 확인**

  Run: `gh pr checks 6 --repo MSG-CTF/msgctf-devsecops --watch`

  Expected: 실행된 check PASS. 실제 K3s smoke는 token과 배포 환경이 없으면 실행하지
  않았다고 구분해 기록한다.

### Task 5: 독립 코드리뷰 보완

**Files:**
- Modify: `scripts/runtime_api_smoke_runner.py`
- Modify: `scripts/validate_info_spec.py`
- Modify: `tests/test_runtime_api_smoke_runner.py`
- Modify: `tests/test_validate_info_spec.py`
- Modify: `docs/aws-k3s-cd-smoke.md`
- Modify: `docs/devsecops-runbook.md`
- Modify: `docs/superpowers/specs/2026-09-07-runtime-exposed-ports-integration-design.md`

**Interfaces:**
- Consumes: Runtime PR #39 OpenAPI의 endpoint schema, PWN 포트 제한, runtime-status 조회.
- Produces: 잘못된 Runtime 응답 차단, PWN 조기 차단, 불완전 create 결과 cleanup 복구.

- [x] **Step 1: 실패 테스트 작성과 RED 확인**

  잘못된 endpoint protocol·URI·추가 필드, 공개 PWN 컨테이너 다중 포트,
  runtime-status를 통한 `runtime_workload_id` 복구 후 cleanup 완료를 테스트한다.

- [x] **Step 2: 최소 구현과 GREEN 확인**

  endpoint의 정확한 키·`HTTP|TCP`·URI를 검사한다. PWN 공개 컨테이너는 전체 포트가
  정확히 하나인지 info 검증과 Runtime 변환 경계에서 확인한다. create operation 결과가
  불완전하면 runtime-status에서 workload ID를 복구해 삭제한다.

- [x] **Step 3: cleanup 완료와 token 문서 계약 보완**

  endpoint 오류 테스트에서 delete operation 조회 완료까지 확인한다. service token은
  GitHub Secret이 아니라 Runtime node의 `/etc/secure-provisioner/service-token`에서만
  읽는 것으로 설계·운영 문서를 통일하고 기존 `expose` 설명을 갱신한다.

- [x] **Step 4: 전체 검증과 커밋**

  76개 이상의 전체 테스트, Python 문법, diff, Gitleaks 검사를 통과한 뒤 커밋한다.
