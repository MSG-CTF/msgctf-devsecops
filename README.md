# MSGCTF DevSecOps

MSGCTF DevSecOps는 문제 저장소의 `info.yaml`을 기준으로 OCI image를 빌드·검사하고, Runtime이 사용할 digest 고정 workload와 Challenge Registry revision 자료를 발행합니다.

## 전체 흐름

```text
Challenge Repo
→ GitHub Actions
→ info.yaml 및 build context 검증
→ 컨테이너별 Docker build 또는 외부 image pull
→ Gitleaks
→ Trivy 취약점·image secret 검사
→ CycloneDX SBOM 생성
→ OCI Registry에 commit SHA tag로 push
→ OCI digest 추출
→ Runtime artifact + Registry publish document 생성
```

Platform 실행 흐름은 다음과 같습니다.

```text
Scheduler가 Challenge Registry의 active revision 조회
→ Resource Broker가 target 선택
→ Runtime API가 digest workload 수신
→ Runtime이 K3s Namespace·Pod·Service·보안 정책 생성
→ 참가자 URL 또는 TCP endpoint 반환
```

CI는 Kubernetes manifest, Namespace, Service, NetworkPolicy 또는 cleanup을 소유하지 않습니다. 해당 영역은 Runtime 및 격리보안팀의 책임입니다.

## 문제 저장소 계약

서버가 필요한 문제는 문제 디렉터리 바로 아래에 `info.yaml`을 둡니다.

```yaml
name: Web Notebook
category: web
description: |-
  문제 설명
flag: msgctf2026{...}

deployment:
  runtime_type: KUBERNETES
  architecture: AMD64
  containers:
    - name: web
      build: ./prob/for_organizer/web
      ports: [8080, 9090]
      expose: true
    - name: db
      image: postgres:16
      ports: [5432]
      expose: false
  healthcheck:
    container: web
    port: 9090
    path: /healthz
  resource_profile:
    cpu_millicores: 700
    memory_mib: 768
    ephemeral_storage_mib: 1024
```

주요 규칙:

- `info.yaml`이 문제 사양의 단일 소스입니다.
- `build`와 `image`는 컨테이너마다 하나만 사용합니다.
- `build`는 문제 디렉터리 내부의 Docker build context만 가리킬 수 있습니다.
- 외부 `image`는 `latest`나 암묵적 tag를 사용할 수 없으며 명시적 non-latest tag 또는 digest가 필요합니다.
- `expose: true`인 컨테이너의 포트만 참가자에게 공개합니다.
- `resource_profile`은 문제의 모든 컨테이너를 합산한 값입니다.
- `flag`는 존재 여부만 검증하며 로그, output, artifact에 기록하지 않습니다.

로컬 검증:

```bash
python3 -m pip install -r ci/requirements.txt
python3 scripts/validate_info_spec.py path/to/challenge \
  --metadata-output metadata.json \
  --matrix-output matrix.json
```

## Pipeline

### Challenge Supply Chain

[`.github/workflows/challenge-supply-chain.yml`](.github/workflows/challenge-supply-chain.yml)은 문제 저장소가 호출하는 reusable workflow입니다.

입력:

- `challenge_path`: `info.yaml`이 있는 문제 디렉터리
- `revision`: 새 Challenge Registry revision

출력 artifact:

```text
<challenge_slug>-publish-bundle/
├ artifact-v2.json
├ registry-publish.json
├ input/metadata.json
└ results/<container>/sbom/<container>.cdx.json
```

최종 image 경로:

```text
ghcr.io/<owner>/challenges/<challenge_slug>/<container>@sha256:<digest>
```

`latest`는 생성하지 않습니다.

문제 저장소 caller 예시는 [`docs/challenge-caller-example.yml`](docs/challenge-caller-example.yml)에 있습니다.

### Platform Component CI

[`.github/workflows/component-cicd.yml`](.github/workflows/component-cicd.yml)은 Backend, Frontend, Scheduler, Broker, Runtime, Monitoring 저장소가 공통으로 호출하는 workflow입니다.

각 팀은 다음 값만 전달합니다.

- `component_name`
- `context`
- `dockerfile`
- `test_command`
- `push_image`

호출 예시는 [`docs/component-caller-examples.md`](docs/component-caller-examples.md)에 있습니다.

## Atomic Publish

`artifact-v2.json`은 Runtime이 읽을 digest workload입니다. `registry-publish.json`은 Challenge Registry의 원자적 revision 등록 API가 소비할 자료입니다.

발행 조건:

- 모든 container image가 존재합니다.
- 모든 image가 digest로 고정돼 있습니다.
- Gitleaks와 Trivy 검사가 통과했습니다.
- 모든 container의 CycloneDX SBOM이 생성됐습니다.
- 위 조건을 모두 만족해야 active revision 전환을 요청합니다.

Challenge Registry API 계약은 Backend와 확정한 뒤 연결합니다. 현재 workflow는 임의의 DB 쓰기를 수행하지 않고 검증된 publish bundle을 생성합니다.

## 보안 기준

- Critical 취약점 발견 시 발행을 차단합니다.
- High 또는 Critical image secret 발견 시 발행을 차단합니다.
- `latest` 기반 Runtime 배포를 금지합니다.
- secret을 Docker build arg, image layer, GitHub Actions 로그에 남기지 않습니다.
- Runtime·격리보안 계약은 challenge Namespace에 Kubernetes Pod Security `restricted`를 강제해야 합니다.
- 실행 중 instance가 참조하는 이전 revision과 digest는 삭제하지 않습니다.

## 현재 상태

MVP의 source registry는 GHCR입니다. K3s는 containerd mirror 설정을 통해 내부 OCI mirror를 사용할 수 있으며 CI에 GHCR 이외의 credential을 전달하지 않습니다.

신규 아키텍처 기준 공급망은 `info.yaml`, 멀티 컨테이너, digest, SBOM, publish bundle을 지원합니다. 실제 Challenge Registry API 호출, Runtime 배포, OCI mirror 및 Terraform/Ansible 인프라는 각 담당 팀의 계약이 확정된 뒤 통합 테스트합니다.

기존 `.github/workflows/challenge-deployment.yml`과 `.github/workflows/platform-cicd.yml`은 이전 PoC 회귀 확인을 위한 수동 workflow입니다.

## 검증

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile scripts/*.py
make -C frontend test
make -C backend test
make -C runtime test
make -C scheduler test
```
