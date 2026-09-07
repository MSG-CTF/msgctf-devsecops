# Runtime 포트 공개 계약 연동 설계

## 목적

DevSecOps가 발행한 `artifact-v2.json`을 Runtime의 최신 인스턴스 생성 API 계약으로
손실 없이 변환한다. 같은 컨테이너에서 public 포트와 private 포트가 섞여 있어도
private 포트를 외부에 노출하지 않고, Runtime 응답의 공개 endpoint가 요청과 정확히
일치하는지 검증한다.

## 역할 경계

- 출제자 입력인 `info.yaml`의 기존 `ports`와 `expose` 형식은 이 변경에서 수정하지 않는다.
- DevSecOps publish bundle은 Backend PR #62가 소비하는
  `ports: [{"port": 8080, "public": true}]` 형식을 유지한다.
- DevSecOps Runtime smoke runner만 bundle의 포트 정보를 Runtime API의
  `ports: [8080, 9000]`, `exposed_ports: [8080]` 형식으로 변환한다.
- Runtime 요청에는 `expose`를 포함하지 않는다.
- Backend의 DB 모델, Scheduler의 DTO, Runtime 구현은 DevSecOps에서 수정하지 않는다.

## Runtime 요청 변환

각 `workload.containers[]`에 다음 규칙을 적용한다.

1. `ports`에는 bundle에 선언된 전체 포트를 순서대로 넣는다.
2. `exposed_ports`에는 `public: true`인 포트만 넣는다.
3. 모두 private인 컨테이너도 `exposed_ports: []`를 명시한다.
4. `name`, digest 고정 `image`, `ports`, `exposed_ports`, `run_as_user`를 보낸다.
5. workload 전체에 공개 포트가 하나도 없으면 요청 전에 실패한다.
6. `internal_connections`와 `resource_limits`는 기존 검증을 거쳐 보존한다.

예시:

```json
{
  "name": "web",
  "image": "ghcr.io/msg-ctf/challenges/example/web@sha256:...",
  "ports": [8080, 9000],
  "exposed_ports": [8080],
  "run_as_user": 10001
}
```

## 배포 대상과 인증

- 실제 smoke의 `target.target_id`는 workflow 입력을 통해 `aws-k3s-lab`으로 전달한다.
- `target_id`는 release 자체의 속성이 아니므로 `artifact-v2.json`에 저장하지 않는다.
- Runtime API service token은 GitHub Actions에 전달하지 않고 Runtime node의
  `/etc/secure-provisioner/service-token`에서만 읽는다. token은 로그, S3 staging,
  bundle에 남기지 않는다.
- 현재 node에 사용할 service token이 준비되지 않았으므로 코드·단위 테스트까지만
  수행하고 실제 K3s 결과는 미검증으로 기록한다.

## 응답 검증과 정리

- bundle의 모든 `public: true` 포트에서 `(container_name, port)` 예상 집합을 만든다.
- Runtime의 `endpoints[]`는 각 항목의 `container_name`, `port`, `protocol`,
  `service_url`을 검증한다.
- 예상 endpoint와 실제 endpoint가 누락, 추가, 중복 없이 정확히 일치해야 성공한다.
- endpoint가 불일치하면 workload 삭제를 먼저 요청하고 삭제 완료를 확인한 뒤 실패한다.
- create operation 결과에 `runtime_workload_id`가 누락되면
  `GET /internal/v1/instances/{instance_id}/runtime-status`를 cleanup 제한 시간까지
  재시도해 ID를 복구한 뒤 삭제한다.
  status 조회에서도 ID를 복구할 수 없으면 유효한 삭제 요청을 만들 수 없으므로 오류와
  수동 확인 필요 상태를 남긴다.

## Backend 연동

Backend PR #62는 bundle의 `internal_connections`를 검증하고 ChallengeRelease DB와
등록·조회 응답, Poller 수집 과정에 보존한다. DevSecOps는 실제
`web -> db:5432/TCP` 연결을 포함한 publish bundle을 발행한다.

실제 통합 검증은 다음을 확인한다.

1. 최초 bundle 등록과 DB 왕복 후 `internal_connections` 보존
2. 같은 `registry_revision` 재수집 시 중복 등록 방지
3. 새 revision 등록 후 기존 active release 유지
4. Scheduler 계약 확정 후 Runtime 요청까지 `internal_connections`와
   `exposed_ports` 보존

Backend PR #62가 아직 Draft이고 연결이 있는 release 활성화를 차단하므로, 4번과 실제
Runtime 배포는 Backend·Scheduler 계약이 준비된 뒤 수행한다.

## 테스트

- 혼합 포트를 `exposed_ports`로 변환하고 `expose`를 보내지 않는 단위 테스트
- 전체 public과 전체 private 컨테이너 변환 테스트
- 공개 포트가 없는 workload 거절 테스트
- `web -> db:5432/TCP` 보존 테스트
- Runtime endpoint 정확 일치와 누락·추가·중복 거절 테스트
- 전체 Python 단위 테스트, 문법 검사, `git diff --check`, Gitleaks

## 완료 기준

- PR #6의 runner와 테스트가 Runtime PR #39 계약을 따른다.
- PR #7의 publish bundle은 Backend PR #62 입력 계약을 유지한다.
- 실제 배포 전까지 문서와 PR에서 K3s smoke를 완료로 표시하지 않는다.
- Runtime token을 받은 뒤 `aws-k3s-lab`에서 생성·endpoint 확인·삭제 증거를 남긴다.
