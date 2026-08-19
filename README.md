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

publish bundle은 GitHub Actions artifact로 90일 보관합니다. 성공한 실행의
Summary에는 문제 slug, revision, 보안 검사 결과와 컨테이너별 GHCR 경로 및
OCI digest가 표시됩니다. reusable workflow 호출자는 `challenge_slug`와
`publish_bundle_name` output을 후속 job에서 사용할 수 있습니다.

최종 image 경로:

```text
ghcr.io/<owner>/challenges/<challenge_slug>/<container>@sha256:<digest>
```

`latest`는 생성하지 않습니다.

문제 저장소 caller 예시는 [`docs/challenge-caller-example.yml`](docs/challenge-caller-example.yml)에 있습니다.

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

## Image 저장소와 architecture 정책

2026년 8월 MVP의 원본 OCI Registry는 GHCR입니다. 출제자는 Registry 주소를
`info.yaml`의 `build` 항목에 적지 않으며, CI가 검사한 image만 GHCR에 push하고
digest로 고정합니다. Runtime은 instance 생성 시 선택된 node에서 해당 digest를
pull합니다. 전체 node 사전 pull은 MVP 필수 범위가 아니며, node에 같은 digest가
있으면 container runtime cache를 재사용할 수 있습니다.

K3s는 향후 containerd mirror 설정을 통해 내부 OCI mirror를 사용할 수 있습니다.
사전 pull, mirror 또는 별도 Registry 도입은 MVP 이후 결정하며, 이 경우에도
Runtime에는 digest 고정 reference만 전달합니다.

신규 아키텍처 기준 공급망은 `info.yaml`, 멀티 컨테이너, digest, SBOM, publish bundle을 지원합니다. 실제 Challenge Registry API 호출, Runtime 배포, OCI mirror 및 Terraform/Ansible 인프라는 각 담당 팀의 계약이 확정된 뒤 통합 테스트합니다.

Windows container는 Linux image와 같은 build job에서 처리하지 않습니다.
Windows runner, node pool, Runtime 및 Registry 계약이 확정된 뒤 별도 workflow로
추가합니다.

## 검증

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile scripts/*.py
```
