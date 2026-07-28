# MSGCTF 아키텍처 기준 공급망 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `info.yaml`을 단일 소스로 사용해 문제별 멀티 컨테이너 이미지를 빌드 또는 가져오고, 보안 검사와 SBOM 생성을 거쳐 OCI digest와 Challenge Registry revision 자료를 원자적으로 발행하는 공급망을 구현한다.

**Architecture:** Python 도구가 `info.yaml`을 검증해 flag가 제거된 metadata와 container matrix를 만든다. Reusable GitHub Actions workflow가 각 컨테이너를 한 번만 build/pull하고, 동일 이미지를 Trivy로 검사하고 SBOM을 생성한 뒤 GHCR에 commit tag로 push한다. 집계 job은 digest 고정 workload와 revision publish document를 생성하며 Kubernetes manifest, namespace, policy, cleanup은 Runtime 소유로 남긴다.

**Tech Stack:** Python 3.11+, PyYAML 6.x, unittest, GitHub Actions, Docker Buildx, GHCR/OCI Registry, Gitleaks, Trivy, CycloneDX SBOM

## Global Constraints

- 문제 사양의 단일 소스는 문제 디렉터리의 `info.yaml`이다.
- `flag` 값은 stdout, GitHub output, artifact, cache key, image metadata에 포함하지 않는다.
- `runtime_type`은 `KUBERNETES | DOCKER | VM`, `architecture`는 `AMD64 | ARM64`만 허용한다.
- 각 container는 `build` 또는 `image` 중 정확히 하나만 가진다.
- OCI image는 `latest`를 만들지 않고 최종 workload에는 `@sha256:<digest>`만 기록한다.
- 이미지 검사가 모두 통과하기 전에는 publish document를 생성하지 않는다.
- 실행 중 revision 보존과 active 전환을 위해 publish document는 immutable revision 자료와 active 전환 요청을 분리해 표현한다.
- CI는 Kubernetes manifest, Namespace, NetworkPolicy, Service, cleanup을 생성하거나 적용하지 않는다.
- 기존 v1 workflow는 수동 회귀용으로만 유지한다.

---

### Task 1: `info.yaml` 검증과 container matrix

**Files:**
- Create: `ci/requirements.txt`
- Create: `scripts/validate_info_spec.py`
- Create: `tests/fixtures/info-valid/info.yaml`
- Create: `tests/fixtures/info-valid/prob/for_organizer/web/Dockerfile`
- Create: `tests/test_validate_info_spec.py`

**Interfaces:**
- Produces: `validate_spec(challenge_path: Path) -> dict`
- Produces: `container_matrix(metadata: dict) -> dict`
- CLI: `validate_info_spec.py CHALLENGE_PATH --metadata-output FILE --matrix-output FILE --github-output FILE`

- [ ] Write tests for valid multi-container metadata, flag redaction, duplicate names, path escape, missing Dockerfile, invalid enums, invalid ports, and invalid resources.
- [ ] Run `python3 -m unittest tests.test_validate_info_spec -v` and confirm the module is missing.
- [ ] Implement validation with `yaml.safe_load()`, resolved-path containment checks, safe lowercase identifiers, and sanitized output.
- [ ] Run the validation tests and confirm they pass.

### Task 2: digest workload와 Atomic Publish 자료

**Files:**
- Create: `scripts/generate_publish_bundle.py`
- Create: `tests/test_generate_publish_bundle.py`

**Interfaces:**
- Produces: `generate_bundle(metadata: dict, results: list[dict], source_ref: str, revision: int) -> dict`
- CLI outputs `artifact-v2.json` and `registry-publish.json`.

- [ ] Write tests that require an exact container result set, digest-only images, SBOM references, positive revision, no flag, and port visibility mapping.
- [ ] Run `python3 -m unittest tests.test_generate_publish_bundle -v` and confirm the module is missing.
- [ ] Implement schema `2.0` workload output and registry publish document containing `revision`, `is_active`, `source_ref`, `workload`, `resource_profile`, and scan evidence.
- [ ] Run the bundle tests and confirm they pass.

### Task 3: Challenge reusable workflow

**Files:**
- Create: `.github/workflows/challenge-supply-chain.yml`
- Create: `tests/test_workflow_contracts.py`
- Create: `docs/challenge-caller-example.yml`

**Interfaces:**
- Inputs: `challenge_path`, `revision`
- Outputs: `<challenge_slug>-publish-bundle`

- [ ] Write workflow contract tests for validate, matrix build/pull, Gitleaks, Trivy vulnerability/secret gates, CycloneDX SBOM, digest extraction, aggregate publish, and absence of `latest`, `kubectl`, and manifest rendering.
- [ ] Run the workflow tests and confirm the workflow is missing.
- [ ] Implement caller checkout, DevSecOps tool checkout, metadata validation, matrix image processing, scan/SBOM result upload, and aggregate publish bundle creation.
- [ ] Parse workflow YAML and run contract tests.

### Task 4: 플랫폼 reusable workflow와 legacy 경계

**Files:**
- Create: `.github/workflows/component-cicd.yml`
- Modify: `.github/workflows/challenge-deployment.yml`
- Modify: `.github/workflows/platform-cicd.yml`
- Create: `docs/component-caller-examples.md`

**Interfaces:**
- Component inputs: `component_name`, `context`, `dockerfile`, `test_command`, `push_image`
- Legacy workflows: manual invocation only

- [ ] Add tests requiring commit-only image tags, Gitleaks, Trivy, SBOM, and manual-only legacy triggers.
- [ ] Confirm the tests fail against the current workflows.
- [ ] Implement the reusable component workflow and remove automatic push/PR triggers from legacy sample workflows.
- [ ] Run workflow contract and YAML parsing tests.

### Task 5: 보안 경계와 문서

**Files:**
- Modify: `README.md`
- Modify: `ci/README.md`
- Modify: `docs/devsecops-runbook.md`
- Delete: `artifact.json`
- Delete: `dist/challenge-manifest.yaml`

**Interfaces:**
- Runtime owns Namespace, runtime manifests, policies, and cleanup.

- [ ] Remove CI-owned Kubernetes manifests and document the Runtime ownership boundary.
- [ ] Remove stale generated deployment files from version control.
- [ ] Document the architecture flow, team ownership boundaries, revision retention, registry failure handling, and local validation commands in Korean.
- [ ] Run all Python tests, Python syntax checks, YAML parsing, component sample tests, and `git diff --check`.

### Task 6: 최종 검증

**Files:**
- Verify all files changed by Tasks 1-5.

- [ ] Run `python3 -m unittest discover -s tests -v`.
- [ ] Run `python3 -m py_compile scripts/*.py`.
- [ ] Parse every workflow and Kubernetes YAML file.
- [ ] Run `make test` for frontend, backend, runtime, and scheduler samples.
- [ ] Run `git diff --check`.
- [ ] Review the diff for flag leakage, mutable tags, Kubernetes ownership violations, and unrelated changes.
