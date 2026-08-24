# MSGCTF 출제 문제 검증 CI/CD


별도 `2026_MSG_CTF` 저장소에 제출된 문제의 `info.yaml`과 Dockerfile을
검증하고, Runtime이 사용할 digest 고정 workload와 Challenge Registry
revision 자료를 발행하는 reusable CI/CD 도구 저장소입니다.

## 저장소 구조

| 경로 | 역할 |
|---|---|
| [`.github/workflows`](.github/workflows/README.md) | 문제 image build·scan·GHCR 발행 workflow와 자체 검증 workflow |
| [`ci`](ci/README.md) | CI 실행 의존성과 문제 공급망 운영·보안 기준 |
| [`docs`](docs/README.md) | 문제 저장소 연동 예제와 DevSecOps 운영 문서 |
| [`scripts`](scripts/README.md) | 변경 문제 탐색, `info.yaml` 검증, Runtime·Registry 발행 자료 생성 |
| [`tests`](tests/README.md) | 명세 validator, publish bundle, GitHub Actions 계약 테스트 |

플랫폼 Backend·Frontend, Runtime, Scheduler의 애플리케이션 코드는 각 담당
저장소에서 관리합니다. 이 저장소에는 출제 문제 검증과 image 공급망에 필요한
workflow, 도구, 계약 테스트만 둡니다.

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
→ 선택적으로 Challenge Registry API에 revision 등록
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

출제 문제는 다음 구조를 사용합니다.

```text
2026_MSG_CTF/
└─ <분야>-<문제명>/
   ├─ exploit/
   ├─ README.md
   ├─ info.yaml
   └─ prob/
      ├─ for_organizer/
      │  └─ <container>/
      │     └─ Dockerfile
      └─ for_user/
```

정적 문제는 `deployment`를 생략하며 metadata만 검증합니다. 서버가 필요한
문제는 문제 디렉터리 바로 아래의 `info.yaml`에 `deployment`를 작성합니다.

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
- `deployment`가 없는 정적 문제는 Docker build와 image 발행을 수행하지 않습니다.
- 현재 Linux `AMD64`, `ARM64`만 지원하며 Windows container는 정책 확정 전까지 거부합니다.

로컬 검증:

```bash
python3 -m pip install -r ci/requirements.txt
python3 scripts/validate_info_spec.py path/to/challenge \
  --metadata-output metadata.json \
  --matrix-output matrix.json
```

## Pipeline

### Challenge Branch Validation

[`.github/workflows/challenge-branch-validation.yml`](.github/workflows/challenge-branch-validation.yml)은
출제자 branch와 PR에서 호출하는 읽기 전용 reusable workflow입니다. `info.yaml`,
Docker build context와 secret을 검사하고 image를 build한 뒤 Trivy와 CycloneDX SBOM을
생성합니다. GHCR push, publish bundle, Challenge Registry와 Runtime 호출은 포함하지
않습니다.

입력은 `challenge_path`, 검사할 commit 또는 branch인 `source_ref`, 도구 version인
`devsecops_ref`입니다. 기존 문제 branch를 다시 검사할 때 caller의 수동 실행 입력으로
`source_ref`를 전달할 수 있습니다.

### Challenge Supply Chain

[`.github/workflows/challenge-supply-chain.yml`](.github/workflows/challenge-supply-chain.yml)은 문제 저장소가 호출하는 reusable workflow입니다.

입력:

- `challenge_path`: `info.yaml`이 있는 문제 디렉터리
- `revision`: 새 Challenge Registry revision
- `devsecops_ref`: 공급망 도구 version, 기본값 `main`
- `publish_images`: 검사한 image를 GHCR에 발행하고 publish bundle을 생성할지 여부, 기본값 `true`
- `publish_registry`: Challenge Registry API 등록 여부, 기본값 `false`
- `enable_k3s_smoke_deploy`: Secure Provisioner API 경유 임시 K3s 배포 검증 여부, 기본값 `false`
- `runtime_target_id`: Secure Provisioner Registry의 K3s target ID

운영 문제 저장소는 `devsecops_ref: main`을 사용합니다. DevSecOps 기능 브랜치의
자체 검증에서는 workflow와 script가 같은 commit을 사용하도록 `github.sha`를
전달합니다.

출제자 branch와 PR 검증에서는 `publish_images: false`를 사용하고 Secret을 전달하지
않습니다. 이 모드는 Docker build, Gitleaks, Trivy와 SBOM 생성까지만 수행합니다.
GHCR push, Challenge Registry 등록과 Runtime smoke는 승인된 `main` 실행에서만
활성화합니다.

출력 artifact:

```text
<challenge_slug>-<artifact_scope>-publish-bundle/
├ artifact-v2.json
├ registry-publish.json
├ input/metadata.json
└ results/<container>/
   ├ timing.json
   └ sbom/<container>.cdx.json
```

publish bundle은 GitHub Actions artifact로 90일 보관합니다. 성공한 실행의
Summary에는 문제 slug, revision, 보안 검사 결과, 컨테이너별 GHCR 경로,
OCI digest와 단계별 소요 시간이 표시됩니다. reusable workflow 호출자는 `challenge_slug`와
`publish_bundle_name` output을 후속 job에서 사용할 수 있습니다.

`artifact_scope`는 workflow 호출마다 생성되는 고유값입니다. 같은 문제를 한
Actions run에서 중복 호출하거나 job을 재실행해도 metadata, 컨테이너 결과와 최종
publish bundle 이름이 충돌하지 않습니다.

측정 시간은 컨테이너별 `Build/Pull`, `Scan`, `GHCR Push`와 세 구간의 합계입니다.
GitHub runner 대기 시간과 job 준비 시간은 포함하지 않습니다. 원본 수치는
`artifact-v2.json`의 `evidence.containers[].timing`에도 기록합니다.

최종 image 경로:

```text
ghcr.io/<owner>/challenges/<challenge_slug>/<container>@sha256:<digest>
```

`latest`는 생성하지 않습니다.

문제 저장소 caller 예시는 [`docs/challenge-caller-example.yml`](docs/challenge-caller-example.yml)에 있습니다.

## KOTH 문제

백엔드팀의 `koth-template`은 일반 문제와 동일한 `info.yaml` 공급망 계약을
사용합니다. `category: koth`, `deployment.containers[].build`, 참가자 포트,
healthcheck 포트와 `resource_profile`을 검증한 뒤 다음 경로로 발행합니다.

```text
ghcr.io/<owner>/challenges/<koth_slug>/service@sha256:<digest>
```

`prob/for_organizer/docker-compose.yml`은 출제자 로컬 테스트용입니다. GHCR에는
`info.yaml`의 `deployment.containers`에 선언된 컨테이너만 발행하므로 Compose의
보조 `checker`는 자동 발행하지 않습니다.

## Atomic Publish

`artifact-v2.json`은 Runtime이 읽을 digest workload입니다. `registry-publish.json`은 Challenge Registry의 원자적 revision 등록 API가 소비할 자료입니다.

발행 조건:

- 모든 container image가 존재합니다.
- 모든 image가 digest로 고정돼 있습니다.
- Gitleaks와 Trivy 검사가 통과했습니다.
- 모든 container의 CycloneDX SBOM이 생성됐습니다.
- 위 조건을 모두 만족해야 active revision 전환을 요청합니다.

`publish_registry: true`이면 workflow가 검증된 `registry-publish.json`을
`CHALLENGE_REGISTRY_URL` secret에 설정된 HTTPS API로 `POST`합니다. 인증에는
`CHALLENGE_REGISTRY_TOKEN` secret을 사용하고, 문제, revision, 요청 body SHA-256을
조합한 `Idempotency-Key`를 전달합니다. API 오류는 성공으로 처리하지 않으며
Registry 등록 job이 실패합니다.

이 기능은 Backend의 등록 API가 준비될 때까지 기본적으로 비활성화합니다. CI는
Backend DB를 직접 수정하지 않고 API 계약만 사용합니다. 선택형 K3s smoke job만
SSM을 통해 Secure Provisioner API를 호출하며 Scheduler와 Broker의 운영 흐름은
직접 호출하지 않습니다.

## Runtime K3s Smoke

`enable_k3s_smoke_deploy: true`이면 GitHub Actions가 AWS OIDC와 SSM을 사용해 K3s
노드 내부의 Secure Provisioner API에 임시 instance 생성을 요청합니다. 생성
Operation이 성공하면 같은 API로 즉시 삭제하고, 두 결과를 Actions Summary에
기록합니다. CI는 Kubernetes manifest, Namespace, Service와 보안 정책을 직접
만들지 않습니다.

필요한 Secret은 `AWS_ROLE_TO_ASSUME`, `AWS_REGION`, `AWS_K3S_INSTANCE_ID`,
`AWS_CD_ARTIFACT_BUCKET`입니다. caller는 `runtime_target_id`도 전달해야 합니다.
자세한 설정은 [`docs/aws-k3s-cd-smoke.md`](docs/aws-k3s-cd-smoke.md)에 있습니다.

## 보안 기준

- Critical 취약점 발견 시 발행을 차단합니다.
- High 또는 Critical image secret 발견 시 발행을 차단합니다.
- `latest` 기반 Runtime 배포를 금지합니다.
- secret을 Docker build arg, image layer, GitHub Actions 로그에 남기지 않습니다.
- Runtime·격리보안 계약은 challenge Namespace에 Kubernetes Pod Security `restricted`를 강제해야 합니다.
- 실행 중 instance가 참조하는 이전 revision과 digest는 삭제하지 않습니다.

## Image 저장소와 architecture 정책

2026년 8월 MVP의 원본 OCI Registry는 GHCR입니다. 출제자는 Registry 주소를
`info.yaml`의 `build` 항목에 적지 않으며, CI가 검사한 image만 GHCR에 push하고
digest로 고정합니다. Runtime은 instance 생성 시 선택된 node에서 해당 digest를
pull합니다. 전체 node 사전 pull은 MVP 필수 범위가 아니며, node에 같은 digest가
있으면 container runtime cache를 재사용할 수 있습니다.

K3s는 향후 containerd mirror 설정을 통해 내부 OCI mirror를 사용할 수 있습니다.
사전 pull, mirror 또는 별도 Registry 도입은 MVP 이후 결정하며, 이 경우에도
Runtime에는 digest 고정 reference만 전달합니다.

신규 아키텍처 기준 공급망은 `info.yaml`, 멀티 컨테이너, digest, SBOM, publish bundle을 지원합니다. Challenge Registry API는 Backend endpoint가 준비된 뒤 활성화하고, Runtime 배포 smoke는 Secure Provisioner API를 경유합니다. OCI mirror와 Terraform/Ansible 인프라는 각 담당 팀의 계약에 맞춰 통합 테스트합니다.

Windows container는 Linux image와 같은 build job에서 처리하지 않습니다.
Windows runner, node pool, Runtime 및 Registry 계약이 확정된 뒤 별도 workflow로
추가합니다.

## 검증

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile scripts/*.py
```
