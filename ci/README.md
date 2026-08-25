# Challenge Supply Chain 운영 기준

## DevSecOps 책임

DevSecOps는 문제 source나 외부 OCI image를 다음 상태로 만들어 Challenge Registry와 Runtime에 전달합니다.

- 재현 가능한 build
- secret과 Critical 취약점 검사를 통과한 image
- OCI digest로 고정된 image
- 컨테이너별 CycloneDX SBOM
- commit과 revision을 추적할 수 있는 workload

DevSecOps는 참가자 instance scheduling, target 선택, Kubernetes manifest 생성, endpoint 발급, instance cleanup을 수행하지 않습니다.
선택형 통합 smoke test는 Runtime이 고른 고정 target에 임시 instance를 생성하고
즉시 삭제하지만, 이 경우에도 Secure Provisioner API만 사용합니다.

## 처리 단계

### 1. 입력 검증

`scripts/validate_info_spec.py`가 다음 항목을 검사합니다.

- 문제 디렉터리 이름
- `name`, `category`, `description`, `flag`
- `deployment`가 없는 정적 문제와 서버 문제 구분
- `runtime_type`: `KUBERNETES | DOCKER | VM`
- `architecture`: `AMD64 | ARM64`
- container name 중복
- `build`와 `image` 상호 배타성
- build context의 문제 디렉터리 이탈
- Dockerfile 존재 여부
- port 범위
- healthcheck container·port·path
- CPU, memory, ephemeral storage 값

검증 결과에는 `flag`가 포함되지 않습니다.

정적 문제는 이 단계에서 검증을 마치며 Docker build, 보안 image scan 및 OCI
발행 job을 실행하지 않습니다.

### 2. 컨테이너 image 처리

`build` 컨테이너는 해당 디렉터리만 Docker build context로 사용합니다. `image` 컨테이너는 외부 Registry에서 명시적 non-latest tag 또는 digest로 image를 가져온 뒤 source digest를 기록합니다.

검사 대상과 push 대상은 동일한 로컬 image입니다. 검사 후 다시 build하지 않습니다.

### 3. 보안 검사

- Gitleaks: 문제 저장소 secret 검사
- Trivy vulnerability scanner: Critical 취약점 차단
- Trivy secret scanner: High·Critical image secret 차단
- Trivy CycloneDX: container별 SBOM 생성

예외가 필요하면 운영 승인자, 사유, 만료일, 대상 digest를 별도 기록해야 합니다. workflow에서 검사 실패를 자동 무시하지 않습니다.

### 4. OCI image 발행

검사 통과 image만 다음 경로로 push합니다.

```text
ghcr.io/<owner>/challenges/<challenge_slug>/<container>:<commit_sha>-<run_id>-<run_attempt>
```

Runtime에 전달하는 값은 다음과 같습니다.

```text
ghcr.io/<owner>/challenges/<challenge_slug>/<container>@sha256:<digest>
```

commit tag는 추적과 발행을 위한 입력이고 Runtime 계약은 digest입니다. `latest`는 만들지 않습니다.

각 컨테이너는 Build 또는 외부 image pull, Trivy Scan, GHCR Push 시간을 초 단위로
측정합니다. 세 구간의 합계와 원본 수치는 publish bundle 및 Actions Summary에
남기며 runner 대기와 job 준비 시간은 제외합니다.

KOTH 문제도 같은 규칙을 사용합니다. `info.yaml`의 `deployment.containers`에
선언된 `service`를 발행하며 로컬 Compose 전용 `checker`는 발행 대상이 아닙니다.

### 5. Atomic Publish 자료

`scripts/generate_publish_bundle.py`가 두 파일을 생성합니다.

- `artifact-v2.json`: Runtime과 Scheduler가 읽을 immutable workload
- `registry-publish.json`: Challenge Registry가 한 transaction으로 revision을 추가하고 active를 전환할 요청

Registry는 기존 active revision을 먼저 해제한 뒤 새 row를 쓰는 방식으로 처리하면 안 됩니다. 새 revision 저장과 active 전환이 하나의 transaction에서 성공해야 합니다. 실패하면 기존 active revision을 유지해야 합니다.

실행 중 instance가 참조하는 revision은 active가 아니더라도 보존합니다.

Backend가 등록 API를 제공하면 reusable workflow의 `publish_registry`를 켜서
`registry-publish.json`을 HTTPS로 전달합니다. API는 `Idempotency-Key`를 기준으로
같은 문제와 revision의 중복 요청을 안전하게 처리해야 합니다. Registry 등록이
실패하면 새 revision을 배포 가능 상태로 간주하지 않습니다.

## 팀 계약

### Challenge Registry

- DevSecOps: 검증된 revision publish
- Scheduler: active revision read-only 조회
- Backend/Registry: slug와 `challenge_id` 매핑 및 transaction 제공
- DevSecOps와 Backend: `registry-publish.json` 요청 및 인증 계약 유지

### Resource Broker

DevSecOps가 검증한 다음 필드를 그대로 사용합니다.

```json
{
  "cpu_millicores": 700,
  "memory_mib": 768,
  "ephemeral_storage_mib": 1024
}
```

### Runtime 및 격리보안

DevSecOps는 `workload.containers[]`, `ports[].public`, `healthcheck`, `resource_profile`을 전달합니다. Runtime은 이를 이용해 Namespace, Pod, Service, Gateway, NetworkPolicy, SecurityContext와 cleanup을 구현합니다.
발행 후 smoke test는 SSM으로 Runtime node 안의 Secure Provisioner API를 호출해
생성과 삭제 Operation이 모두 성공하는지만 확인합니다.

### Monitoring 및 SLA

Monitoring은 Registry pull 실패, Pod 생성 실패, healthcheck 실패, CrashLoopBackOff와 resource saturation을 감시합니다.

## 금지 사항

- `info.yaml` 외의 값을 문제 사양으로 추측하지 않습니다.
- Runtime에 mutable tag를 전달하지 않습니다.
- scan 전 image를 배포 가능 상태로 등록하지 않습니다.
- flag와 secret을 로그 또는 artifact에 기록하지 않습니다.
- CI가 Runtime API를 대신해 Pod를 만들지 않습니다.
- 실행 중 revision의 image와 SBOM을 삭제하지 않습니다.

## MVP Registry 정책

- 2026년 8월 MVP의 원본 Registry는 GHCR입니다.
- Runtime은 instance 생성 시 선택된 node에서 digest 고정 image를 pull합니다.
- 전체 node 사전 pull은 MVP 필수 범위가 아닙니다.
- 사전 pull, mirror 또는 별도 Registry 도입은 MVP 이후 결정합니다.
- 현재 Linux `AMD64`, `ARM64`만 지원합니다.
- Windows container는 Windows runner, node pool, Runtime과 저장 위치가
  확정될 때까지 허용하지 않습니다.
