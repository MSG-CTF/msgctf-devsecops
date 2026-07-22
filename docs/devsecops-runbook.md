# MSGCTF DevSecOps 운영 절차

## 파이프라인 1: 문제 이미지 배포

담당: DevSecOps

1. 제출 저장소에 `challenge.toml`이 있는지 확인한다.
2. `challenge.id`, `deployment.resource_profile`, `image.ref`, `image.port`, `monitoring.health_path`를 검증한다.
3. 출제자가 제출한 Docker 이미지를 pull한다.
4. 메타데이터 저장소에 Gitleaks를 실행하고 secret이 발견되면 중단한다.
5. 제출 이미지에 Trivy를 실행하고 Critical 취약점이 발견되면 중단한다.
6. 제한된 권한으로 이미지를 실행하고 선언된 health endpoint를 확인한다.
7. 통과한 이미지를 MSGCTF GHCR로 승격한다.
8. 승격된 이미지의 digest를 추출한다.
9. `artifact.json`과 Kubernetes manifest를 생성한다.
10. Runtime이 사용할 배포 artifact를 GitHub Actions에 업로드한다.

Runtime은 mutable tag가 아닌 digest 기반 `image_ref`로 배포해야 한다.

## 파이프라인 2: 플랫폼 CI/CD

담당: Platform팀 및 DevSecOps

1. frontend, backend, runtime, scheduler 테스트를 실행한다.
2. 각 컴포넌트의 Docker 이미지를 빌드한다.
3. 저장소에 Gitleaks를 실행한다.
4. 이미지에 Trivy를 실행한다.
5. 통과한 컴포넌트 이미지를 GHCR에 push한다.
6. Workload Identity Federation으로 GCP에 인증한다.
7. Kubernetes manifest를 GKE에 적용한다.
8. 각 Deployment의 rollout 완료 여부를 확인한다.

GKE 배포는 Repository Variable `ENABLE_GKE_DEPLOY`가 `true`일 때만 실행한다.

## Runtime 계약

Backend가 관리하는 문제 메타데이터 예시:

```json
{
  "challenge_id": "web100",
  "tile_id": 12,
  "resource_profile": "small"
}
```

Runtime이 사용하는 `artifact.json` 예시:

```json
{
  "challenge_id": "web100",
  "image_ref": "ghcr.io/msgctf/web100@sha256:abcd...",
  "digest": "sha256:abcd...",
  "resource_profile": "small",
  "container_port": 5000,
  "health_path": "/health",
  "scan_result": "PASS"
}
```

Scheduler가 사용하는 resource profile 예시:

```json
{
  "small": {
    "requests": {"cpu": "250m", "memory": "256Mi"},
    "limits": {"cpu": "500m", "memory": "512Mi"}
  }
}
```

Kubernetes는 최종 문제 Pod를 `challenge` namespace에 실행한다.

## 실패 대응

### 보안 검사 실패

- Actions 로그에서 Gitleaks 또는 Trivy 결과를 확인한다.
- secret이 발견되면 credential을 즉시 폐기하고 새 값으로 교체한다.
- 취약점을 수정하거나 승인된 예외 절차를 거친 뒤 다시 실행한다.

### Health Check 실패

- 제출 이미지의 실행 포트와 `image.port`가 일치하는지 확인한다.
- `monitoring.health_path`가 HTTP 200을 반환하는지 확인한다.
- non-root, read-only filesystem, capability 제한 환경에서 실행되는지 확인한다.

### GHCR Push 실패

- workflow의 `packages: write` 권한을 확인한다.
- Repository의 Actions workflow permission을 확인한다.
- 같은 이름의 package에 조직 정책이 적용되어 있는지 확인한다.

### GKE 배포 실패

- GCP Workload Identity Provider와 Service Account 설정을 확인한다.
- `GKE_CLUSTER`, `GKE_LOCATION` secret을 확인한다.
- `kubectl rollout status`와 Pod event를 확인한다.

## 대회 운영

대회 시작 전 모든 문제 이미지의 보안 검사와 health check를 완료하고 digest와 artifact를 확정한다. 대회 중 긴급 수정이 필요하면 운영 승인, 재검사, 새 digest 생성, 새 artifact 등록 순서로 처리한다. 이전 digest는 실행 중인 인스턴스와 롤백을 위해 보존한다.
