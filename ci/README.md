# MSGCTF DevSecOps CI/CD

## 역할

DevSecOps는 문제 이미지를 안전하고 추적 가능하며 반복적으로 배포할 수 있는 상태로 만든다. 문제 변경 시 다음 정보를 확인할 수 있어야 한다.

- 어떤 문제에서 생성된 이미지인지
- 어떤 commit 또는 제출 이미지에서 만들어졌는지
- Runtime이 사용할 Registry URL과 digest가 무엇인지
- Secret Scan과 Vulnerability Scan을 통과했는지
- 배포 가능한 상태인지

MSGCTF의 CI/CD는 단순한 빌드 자동화가 아니다. 이미지 내부의 secret 유출과 심각한 취약점을 차단하고, 이미지 출처를 기록하며, Runtime과 Scheduler가 사용할 배포 artifact를 생성한다.

## 문제 접수 방식

### Mode A: Source Build Pipeline

출제자가 문제 저장소에 소스코드를 제출하고 CI가 이미지를 빌드하는 방식이다.

```text
Challenge Repo Push
→ Metadata Validation
→ Docker Build
→ Gitleaks Scan
→ Trivy Scan
→ Registry Push
→ Digest Extraction
→ artifact.json Generation
```

소스부터 재현 가능한 빌드를 만들 수 있지만 언어와 빌드 도구별 환경을 관리해야 한다.

### Mode B: Submitted Image Pipeline

출제자가 직접 빌드한 Docker 이미지와 문제 메타데이터를 제출하는 방식이다.

```text
Challenge Metadata Push
→ challenge.toml Validation
→ Docker Image Pull
→ Gitleaks Scan
→ Trivy Scan
→ Health Check
→ GHCR Promotion
→ Digest Extraction
→ artifact.json Generation
```

언어와 프레임워크에 독립적이므로 현재 MVP는 Mode B를 사용한다. Mode A는 향후 관리형 문제 저장소가 필요할 때 확장한다.

## 파이프라인 구성

### Challenge Deployment Pipeline

관련 파일:

- `.github/workflows/challenge-deployment.yml`
- `challenge.toml`
- `scripts/validate_challenge_spec.py`
- `scripts/generate_artifact.py`
- `scripts/render_challenge_manifest.py`

주요 작업:

1. `challenge.toml`을 검증한다.
2. 메타데이터 저장소에서 Gitleaks를 실행한다.
3. 제출 이미지를 pull하고 digest로 고정한다.
4. Trivy로 취약점과 이미지 secret을 검사한다.
5. 제한된 권한으로 컨테이너를 실행해 health endpoint를 확인한다.
6. 통과한 이미지를 MSGCTF GHCR로 승격한다.
7. 배포용 `artifact.json`과 Kubernetes manifest를 생성한다.

### Platform CI/CD Pipeline

관련 파일:

- `.github/workflows/platform-cicd.yml`
- `frontend/`
- `backend/`
- `runtime/`
- `scheduler/`
- `k8s/`

주요 작업:

1. 각 컴포넌트의 테스트를 실행한다.
2. 컴포넌트별 Docker 이미지를 빌드한다.
3. Gitleaks와 Trivy를 실행한다.
4. 통과한 이미지를 GHCR에 push한다.
5. 배포 기능이 활성화된 경우 GKE에 배포한다.

## Registry 정책

Registry는 GHCR를 사용한다.

```text
ghcr.io/msgctf/<challenge_id>:<commit_sha>
ghcr.io/msgctf/<challenge_id>@sha256:<digest>
```

- Runtime은 digest 기반 참조를 사용한다.
- mutable tag에 의존해 배포하지 않는다.
- 승격된 이미지는 하나의 `challenge_id`와 연결되어야 한다.
- Registry credential은 저장소에 커밋하지 않는다.

## 보안 검사 정책

사용 도구:

- Gitleaks: 저장소 secret 탐지
- Trivy: 이미지 취약점과 이미지 내부 secret 탐지

기본 정책:

- Critical 취약점이 발견되면 배포를 차단한다.
- High 취약점 처리 기준은 운영팀과 확정한다.
- 보안 검사에 실패한 이미지는 배포 가능한 상태로 표시하지 않는다.
- 예외 승인은 담당자와 사유가 기록되어야 한다.

## 배포 artifact

Runtime과 Scheduler는 tag를 추측하지 않고 CI가 생성한 artifact를 사용한다.

```json
{
  "schema_version": "1.0",
  "challenge_id": "web100",
  "submitted_image": "ghcr.io/author/web100:v1",
  "image": "ghcr.io/msgctf/web100",
  "digest": "sha256:abcd...",
  "image_ref": "ghcr.io/msgctf/web100@sha256:abcd...",
  "scan_result": "PASS",
  "resource_profile": "small",
  "container_port": 5000,
  "health_path": "/health"
}
```

필수 정보:

- `challenge_id`
- `image_ref`
- `digest`
- `resource_profile`
- `container_port`
- `health_path`
- `scan_result`

## Secret 관리

- 장기 secret을 Docker build arg로 전달하지 않는다.
- secret을 Docker image layer에 저장하지 않는다.
- CI 로그에 secret을 출력하지 않는다.
- Registry credential, cloud credential, challenge runtime secret을 분리한다.
- 대회 전 Registry token과 cloud credential을 교체한다.
- 실행 시 필요한 secret은 Kubernetes Secret 또는 외부 Secret Manager로 주입한다.

## 팀 간 합의 항목

Runtime 및 격리보안팀:

- digest 기반 이미지 참조
- pull secret 전달 방식
- Pod SecurityContext와 NetworkPolicy

Backend 및 Platform팀:

- `challenge_id` 형식
- 문제 메타데이터와 배포 artifact 구조
- 이미지 버전과 상태 표시 방식

Scheduler 및 Resource Broker팀:

- `resource_profile` 필드와 단위
- Runtime에 전달할 workload 구조
- revision 선택과 보존 방식

Monitoring 및 SLA팀:

- image pull 실패 알림
- Registry 장애 알림
- health check 실패와 Pod 장애 알림

## 금지 사항

- Runtime 배포에 mutable `latest` tag를 사용하지 않는다.
- secret을 저장소, image layer, CI 로그에 남기지 않는다.
- 보안 검사 실패를 무시하지 않는다.
- 출처를 알 수 없는 이미지를 Runtime에 전달하지 않는다.
- CI가 Runtime scheduling을 직접 수행하지 않는다.

## MVP 완료 기준

샘플 문제의 메타데이터를 push했을 때 제출 이미지가 자동으로 검증되고, 보안 검사를 통과한 이미지가 GHCR에 등록되며, Runtime과 Scheduler가 digest 기반으로 사용할 수 있는 artifact가 생성되어야 한다.
