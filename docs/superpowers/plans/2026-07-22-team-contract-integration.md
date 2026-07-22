# MSGCTF 팀 저장소 계약 연동 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 실제 문제 저장소의 `info.yaml`과 팀별 플랫폼 저장소 구조를 사용하는 reusable CI/CD 파이프라인을 제공한다.

**Architecture:** Python 도구가 `info.yaml`을 검증하고 flag가 제거된 metadata와 container matrix를 생성한다. GitHub reusable workflow가 matrix의 각 이미지를 build 또는 pull한 뒤 검사·push하고, digest 결과를 모아 artifact v2를 만든다. 플랫폼 저장소는 공통 component workflow를 얇은 caller workflow에서 호출한다.

**Tech Stack:** Python 3.11+, PyYAML 6.x, unittest, GitHub Actions, Docker Buildx, GHCR, Gitleaks, Trivy

## Global Constraints

- `MSG-CTF/2026_MSG_CTF` default branch의 `info.yaml` 형식을 우선한다.
- `flag` 값은 stdout, artifact, output, cache, Docker metadata에 포함하지 않는다.
- `runtime_type`은 `KUBERNETES | DOCKER | VM`, `architecture`는 `AMD64 | ARM64`만 허용한다.
- GHCR image owner와 이름은 소문자여야 하며 `latest`를 생성하지 않는다.
- artifact image는 모두 `@sha256:<64자리 hex>` 참조여야 한다.
- `challenge_id`와 `healthcheck`는 현재 입력에 없으므로 추측하지 않는다.
- 기존 v1 파일은 삭제하지 않고 수동 회귀용으로 유지한다.

---

### Task 1: `info.yaml` 검증기와 안전한 matrix 생성

**Files:**
- Create: `ci/requirements.txt`
- Create: `scripts/validate_info_spec.py`
- Create: `tests/fixtures/info-valid/info.yaml`
- Create: `tests/fixtures/info-valid/web/Dockerfile`
- Create: `tests/test_validate_info_spec.py`

**Interfaces:**
- Consumes: `validate_info_spec.py <challenge_path>`
- Produces: `validate_spec(path: Path) -> dict`, `container_matrix(spec: dict) -> dict`
- CLI outputs: `--metadata-output`, `--matrix-output`, `--github-output`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_validate_info_spec.py`에 다음 동작을 검증한다.

```python
class ValidateInfoSpecTests(unittest.TestCase):
    def test_valid_spec_is_sanitized_and_build_path_is_resolved(self):
        result = validate_spec(FIXTURES / "info-valid")
        self.assertNotIn("flag", result)
        self.assertEqual(result["runtime_type"], "KUBERNETES")
        self.assertEqual(result["containers"][0]["build"], "web")

    def test_rejects_duplicate_container_names(self):
        with self.assertRaisesRegex(ValueError, "container name"):
            validate_spec(self.fixture_with_duplicate_names())

    def test_rejects_build_path_outside_challenge(self):
        with self.assertRaisesRegex(ValueError, "inside challenge directory"):
            validate_spec(self.fixture_with_build("../outside"))

    def test_rejects_invalid_port(self):
        with self.assertRaisesRegex(ValueError, "1..65535"):
            validate_spec(self.fixture_with_ports([0]))
```

- [ ] **Step 2: 테스트 실패 확인**

Run:

```bash
python3 -m unittest tests.test_validate_info_spec -v
```

Expected: `ModuleNotFoundError: No module named 'scripts.validate_info_spec'`

- [ ] **Step 3: 최소 검증기 구현**

`ci/requirements.txt`:

```text
PyYAML>=6.0,<7.0
```

`validate_info_spec.py`는 `yaml.safe_load`, `Path.resolve`, 정규식 `^[a-z0-9][a-z0-9-]{0,62}$`를 사용한다. 반환 dict는 다음 키만 포함한다.

```python
{
    "challenge_slug": challenge_dir.name,
    "name": raw["name"],
    "category": raw["category"],
    "runtime_type": deployment["runtime_type"],
    "architecture": deployment["architecture"],
    "containers": sanitized_containers,
    "resource_profile": sanitized_resource_profile,
}
```

`flag`는 존재 여부와 문자열 타입만 검사하고 변수 내용을 exception 또는 print에 넣지 않는다. matrix는 `{"include": sanitized_containers}` 형식으로 출력한다.

- [ ] **Step 4: 테스트 통과 확인**

```bash
python3 -m pip install -r ci/requirements.txt
python3 -m unittest tests.test_validate_info_spec -v
```

Expected: 모든 validation test `OK`

- [ ] **Step 5: 커밋**

```bash
git add ci/requirements.txt scripts/validate_info_spec.py tests/fixtures tests/test_validate_info_spec.py
git commit -m "info.yaml 문제 사양 검증기 추가"
```

### Task 2: 컨테이너 결과 집계와 artifact v2 생성

**Files:**
- Create: `scripts/generate_artifact_v2.py`
- Create: `tests/test_generate_artifact_v2.py`

**Interfaces:**
- Consumes: sanitized metadata JSON, container result JSON directory, source commit SHA
- Produces: `generate_artifact(metadata: dict, results: list[dict], source_ref: str) -> dict`

- [ ] **Step 1: 실패 테스트 작성**

```python
class GenerateArtifactV2Tests(unittest.TestCase):
    def test_generates_multicontainer_digest_artifact(self):
        artifact = generate_artifact(METADATA, RESULTS, "abc123")
        self.assertEqual(artifact["schema_version"], "2.0")
        self.assertEqual(len(artifact["workload"]["containers"]), 2)
        self.assertTrue(all("@sha256:" in item["image"] for item in artifact["workload"]["containers"]))
        self.assertNotIn("flag", json.dumps(artifact))

    def test_rejects_tag_only_image(self):
        with self.assertRaisesRegex(ValueError, "digest"):
            generate_artifact(METADATA, [{"name": "web", "image": "ghcr.io/x/web:tag"}], "abc123")

    def test_rejects_missing_container_result(self):
        with self.assertRaisesRegex(ValueError, "result set"):
            generate_artifact(METADATA, RESULTS[:1], "abc123")
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
python3 -m unittest tests.test_generate_artifact_v2 -v
```

Expected: `ModuleNotFoundError: No module named 'scripts.generate_artifact_v2'`

- [ ] **Step 3: 최소 생성기 구현**

생성기는 container 이름 집합이 metadata와 정확히 일치하는지 확인하고 다음 구조를 만든다.

```python
artifact = {
    "schema_version": "2.0",
    "challenge_slug": metadata["challenge_slug"],
    "name": metadata["name"],
    "category": metadata["category"],
    "runtime_type": metadata["runtime_type"],
    "architecture": metadata["architecture"],
    "workload": {"containers": containers},
    "resource_profile": metadata["resource_profile"],
    "source_ref": source_ref,
    "scan_result": "PASS",
}
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
python3 -m unittest tests.test_generate_artifact_v2 -v
```

Expected: 모든 artifact test `OK`

- [ ] **Step 5: 커밋**

```bash
git add scripts/generate_artifact_v2.py tests/test_generate_artifact_v2.py
git commit -m "멀티 컨테이너 artifact v2 생성기 추가"
```

### Task 3: 문제 이미지 reusable workflow 추가

**Files:**
- Create: `.github/workflows/challenge-v2.yml`
- Create: `docs/challenge-caller-example.yml`
- Test: `tests/test_workflow_contracts.py`

**Interfaces:**
- `workflow_call.inputs.challenge_path`: required string
- `workflow_call.inputs.registry`: optional string, default `ghcr.io`
- Produces artifact: `<challenge_slug>-deployment-v2`

- [ ] **Step 1: workflow 계약 실패 테스트 작성**

```python
class WorkflowContractTests(unittest.TestCase):
    def test_challenge_v2_has_validate_matrix_and_aggregate_jobs(self):
        text = Path(".github/workflows/challenge-v2.yml").read_text()
        for required in ["workflow_call", "challenge_path", "validate", "build-scan-push", "aggregate"]:
            self.assertIn(required, text)

    def test_challenge_v2_does_not_push_latest(self):
        text = Path(".github/workflows/challenge-v2.yml").read_text()
        self.assertNotIn(":latest", text)
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
python3 -m unittest tests.test_workflow_contracts.WorkflowContractTests.test_challenge_v2_has_validate_matrix_and_aggregate_jobs -v
```

Expected: `FileNotFoundError`

- [ ] **Step 3: workflow 구현**

세 job을 구현한다.

```text
validate
  checkout caller
  checkout MSG-CTF/msgctf-devsecops to .msgctf-ci
  install .msgctf-ci/ci/requirements.txt
  run validate_info_spec.py
  upload sanitized metadata

build-scan-push (matrix)
  build from challenge_path/build or pull image
  pin source image
  Trivy vuln gate
  Trivy secret gate
  login and push commit SHA tag only
  inspect promoted digest
  upload one container-result.json

aggregate
  download metadata and container results
  run generate_artifact_v2.py
  upload artifact-v2.json
```

`docs/challenge-caller-example.yml`에는 다음 caller를 제공한다.

```yaml
name: 문제 이미지 CI
on:
  workflow_dispatch:
    inputs:
      challenge_path:
        required: true
        type: string
jobs:
  challenge:
    uses: MSG-CTF/msgctf-devsecops/.github/workflows/challenge-v2.yml@main
    with:
      challenge_path: ${{ inputs.challenge_path }}
```

- [ ] **Step 4: workflow 계약과 YAML 확인**

```bash
python3 -m unittest tests.test_workflow_contracts -v
ruby -e 'require "yaml"; YAML.parse_file(".github/workflows/challenge-v2.yml")'
```

Expected: test `OK`, YAML exit code `0`

- [ ] **Step 5: 커밋**

```bash
git add .github/workflows/challenge-v2.yml docs/challenge-caller-example.yml tests/test_workflow_contracts.py
git commit -m "info.yaml 문제 이미지 reusable workflow 추가"
```

### Task 4: 플랫폼 component reusable workflow 추가

**Files:**
- Create: `.github/workflows/component-cicd.yml`
- Create: `docs/component-caller-examples.md`
- Modify: `tests/test_workflow_contracts.py`

**Interfaces:**
- Inputs: `component_name`, `context`, `dockerfile`, `test_command`, `push_image`
- Output artifact: `<component_name>-image-metadata`

- [ ] **Step 1: 실패 테스트 추가**

```python
def test_component_workflow_defines_required_inputs(self):
    text = Path(".github/workflows/component-cicd.yml").read_text()
    for required in ["component_name", "context", "dockerfile", "test_command", "push_image"]:
        self.assertIn(required, text)
    self.assertNotIn(":latest", text)
```

- [ ] **Step 2: 실패 확인**

```bash
python3 -m unittest tests.test_workflow_contracts -v
```

Expected: `component-cicd.yml` 관련 test FAIL

- [ ] **Step 3: workflow와 caller 예시 구현**

workflow는 PR에서 test/build/scan까지만 수행하고, `push_image == true`이며 event가 PR이 아닐 때만 GHCR에 commit SHA tag를 push한다. image 이름은 `${GITHUB_REPOSITORY_OWNER,,}`와 검증된 `component_name`으로 만든다.

`docs/component-caller-examples.md`에는 Django와 Scheduler 예시를 각각 제공한다.

```yaml
jobs:
  ci:
    uses: MSG-CTF/msgctf-devsecops/.github/workflows/component-cicd.yml@main
    with:
      component_name: backend
      context: .
      dockerfile: Dockerfile
      test_command: python manage.py test
      push_image: true
```

- [ ] **Step 4: 테스트와 YAML 확인**

```bash
python3 -m unittest tests.test_workflow_contracts -v
ruby -e 'require "yaml"; YAML.parse_file(".github/workflows/component-cicd.yml")'
```

Expected: test `OK`, YAML exit code `0`

- [ ] **Step 5: 커밋**

```bash
git add .github/workflows/component-cicd.yml docs/component-caller-examples.md tests/test_workflow_contracts.py
git commit -m "플랫폼 component reusable workflow 추가"
```

### Task 5: 기존 pipeline 경계와 문서 정리 및 전체 검증

**Files:**
- Modify: `.github/workflows/challenge-deployment.yml`
- Modify: `.github/workflows/platform-cicd.yml`
- Modify: `README.md`
- Modify: `ci/README.md`
- Modify: `docs/devsecops-runbook.md`

**Interfaces:**
- v1 workflows: `workflow_dispatch` 전용
- v2 workflows: 다른 팀 저장소의 기본 통합 지점

- [ ] **Step 1: v1 자동 trigger 금지 테스트 추가**

`tests/test_workflow_contracts.py`에서 v1 파일의 top-level event가 `workflow_dispatch`와 필요한 `workflow_call`만 가지는지 YAML node 또는 제한된 text assertion으로 검증한다.

- [ ] **Step 2: 실패 확인**

```bash
python3 -m unittest tests.test_workflow_contracts -v
```

Expected: 기존 `push` 또는 `pull_request` trigger 때문에 FAIL

- [ ] **Step 3: v1 trigger와 문서 수정**

- `challenge-deployment.yml`: `workflow_call`, `workflow_dispatch`만 유지
- `platform-cicd.yml`: `workflow_dispatch`만 유지
- README 첫 화면에 v2가 실제 팀 저장소 기준임을 명시
- `challenge_id` 미확정, Scheduler 단일 container 한계, Registry API 미구현을 현재 제약으로 기록
- `info.yaml`, artifact v2, reusable caller 사용법을 한국어로 기록

- [ ] **Step 4: 전체 검증**

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile scripts/*.py
git diff --check
ruby -e 'require "yaml"; Dir[".github/workflows/*.{yml,yaml}"].each { |f| YAML.parse_file(f) }'
make -C frontend test
make -C backend test
make -C runtime test
make -C scheduler test
```

Expected: 모든 명령 exit code `0`

- [ ] **Step 5: 최종 커밋과 push**

```bash
git add .github/workflows README.md ci/README.md docs scripts tests
git commit -m "실제 팀 저장소 계약을 DevSecOps 파이프라인에 반영"
git push msg-ctf main
```

push 후 `gh run list --repo MSG-CTF/msgctf-devsecops`로 자동 실행되지 않은 v1과 수동으로 호출 가능한 v2 workflow 등록 상태를 확인한다.
