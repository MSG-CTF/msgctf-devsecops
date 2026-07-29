# 출제 문제 검증 파이프라인 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `msgctf-devsecops`를 별도 `2026_MSG_CTF` 저장소가 호출하는 출제 문제 검증 전용 CI/CD 도구 저장소로 완성한다.

**Architecture:** 공통 검증기는 정적·서버 문제를 구분하고 서버 문제만 컨테이너 matrix를 만든다. 변경 문제 탐지기는 challenge 저장소 push 범위에서 `info.yaml`이 있는 최상위 디렉터리를 반환하며, reusable workflow가 각 서버 문제를 build·scan·publish한다.

**Tech Stack:** Python 3, PyYAML, GitHub Actions, Docker Buildx, Gitleaks, Trivy, GHCR, CycloneDX

## Global Constraints

- 문제 입력 저장소는 `2026_MSG_CTF`이고 CI 도구 저장소는 `MSG-CTF/msgctf-devsecops`다.
- `info.yaml`의 `deployment`는 정적 문제에서 생략할 수 있다.
- 현재 지원 architecture는 `AMD64`, `ARM64`다.
- Windows container와 최종 registry 정책은 확정 전까지 구현하지 않는다.
- CI는 Kubernetes 배포를 수행하지 않는다.

---

### Task 1: 정적 문제 검증

**Files:**
- Modify: `tests/test_validate_info_spec.py`
- Modify: `scripts/validate_info_spec.py`

**Interfaces:**
- Consumes: 문제 디렉터리와 `info.yaml`
- Produces: `validate_spec(path) -> metadata`, `container_matrix(metadata) -> matrix`

- [ ] 정적 문제 fixture를 만드는 실패 테스트를 추가한다.
- [ ] 테스트가 `deployment must be present`로 실패하는지 확인한다.
- [ ] `deployment`가 없으면 `is_server: false`, 빈 container matrix를 반환한다.
- [ ] 서버 문제 metadata에는 `is_server: true`를 추가한다.
- [ ] 전체 검증 테스트를 실행한다.

### Task 2: 변경 문제 탐지

**Files:**
- Create: `tests/test_discover_changed_challenges.py`
- Create: `scripts/discover_changed_challenges.py`

**Interfaces:**
- Consumes: 저장소 루트와 변경 파일 경로 목록
- Produces: `discover_changed_challenges(root, changed_paths) -> list[str]`

- [ ] 여러 문제와 비문제 파일을 구분하는 실패 테스트를 추가한다.
- [ ] 테스트가 import 실패로 실패하는지 확인한다.
- [ ] `info.yaml`이 있는 안전한 최상위 문제 디렉터리만 정렬해 반환한다.
- [ ] CLI가 GitHub matrix JSON과 output을 생성하게 한다.
- [ ] 탐지기 테스트를 실행한다.

### Task 3: workflow와 문서 정리

**Files:**
- Modify: `.github/workflows/challenge-supply-chain.yml`
- Create: `.github/workflows/pipeline-self-test.yml`
- Delete: `.github/workflows/platform-cicd.yml`
- Delete: `.github/workflows/component-cicd.yml`
- Modify: `tests/test_workflow_contracts.py`
- Modify: `docs/challenge-caller-example.yml`
- Modify: `README.md`
- Modify: `ci/README.md`

**Interfaces:**
- Consumes: `challenge_path`, `revision`
- Produces: 정적 문제 metadata 또는 서버 문제 publish bundle

- [ ] 문제 전용 workflow 계약 실패 테스트를 추가한다.
- [ ] 플랫폼 workflow가 존재해 테스트가 실패하는지 확인한다.
- [ ] 정적 문제에서 build job이 실행되지 않도록 조건을 추가한다.
- [ ] main push에서 샘플 문제를 호출하는 self-test workflow를 추가한다.
- [ ] 플랫폼 workflow와 관련 문서를 제거한다.
- [ ] `2026_MSG_CTF` caller 예시를 push 기반 탐지 구조로 수정한다.
- [ ] registry와 Windows 미확정 정책을 한국어 문서에 명시한다.

### Task 4: 검증과 GitHub Actions

**Files:**
- Verify: 전체 변경 파일

**Interfaces:**
- Consumes: 구현 완료 branch
- Produces: main GitHub Actions 실행과 artifact

- [ ] Python 단위 테스트와 문법 검사를 실행한다.
- [ ] 샘플 Dockerfile을 AMD64로 빌드하고 Trivy gate를 실행한다.
- [ ] 변경사항을 커밋하고 팀 저장소 main에 push한다.
- [ ] GitHub Actions self-test의 job, step 및 artifact를 확인한다.
