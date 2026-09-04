# Backend Poller 기반 Challenge Release 등록 설계

## 배경

DevSecOps 공급망은 문제 image를 검사해 GHCR에 digest로 고정하고
`artifact-v2.json`을 포함한 publish bundle을 GitHub Actions artifact로 발행한다.
Backend PR #26은 이 artifact를 주기적으로 수집해 Challenge Release로 등록하는
poller를 제공한다.

기존 PR #7에는 GitHub Actions가 Backend API를 직접 호출하는 push 방식도
포함되어 있었다. 이 방식은 Backend UUID `challenge_id`, API base URL,
관리자 또는 service token과 POST 재전송 규칙을 CI가 알아야 한다. 문제 저장소의
`info.yaml`에는 Backend UUID가 없으므로 현재 계약으로는 안전하게 URL을 만들 수
없다.

MVP에서는 Backend poller를 단일 등록 경로로 사용한다.

## 결정

Challenge Release 등록 흐름은 다음과 같다.

```text
문제 저장소 push
→ GitHub Actions 검증 및 image build
→ Gitleaks와 Trivy 통과
→ GHCR digest image 발행
→ artifact-v2.json과 SBOM을 publish bundle로 업로드
→ Backend poller가 GitHub Actions artifact 수집
→ Backend가 challenge를 매핑하고 release 등록
→ 관리자 또는 Backend가 별도 API로 active release 전환
```

GitHub Actions는 Backend Release API를 직접 호출하지 않는다. 따라서
`CHALLENGE_REGISTRY_URL`, `CHALLENGE_REGISTRY_TOKEN`, `challenge_id`,
`Idempotency-Key`는 DevSecOps publish workflow의 입력이나 secret으로 사용하지
않는다.

## Publish Bundle 계약

Backend poller가 읽는 공식 파일은 `artifact-v2.json`이다. 파일에는 다음 값이
포함된다.

- `schema_version: "2.0"`
- `challenge_slug`
- `revision`과 `registry_revision`
- `runtime_type`과 `architecture`
- `isolation_profile`
- `workload.containers[]`
- 각 컨테이너의 GHCR digest image와 `ports[].public`
- 선택형 `workload.healthcheck`
- 선택형 `workload.internal_connections[]`
- `resource_profile`
- `source_ref`
- `scan_result: "PASS"`
- 컨테이너별 scan, SBOM과 timing evidence

Actions artifact 이름은 Backend poller가 식별할 수 있도록
`<challenge_slug>-<artifact_scope>-publish-bundle` 형식을 유지한다.

`registry-publish.json`은 자동 전송에 사용하지 않고 수동 API 검증 자료로
유지한다. Backend PR #26의 요청 형식인 아래 wrapper만 담는다.

```json
{
  "artifact": {}
}
```

wrapper의 `artifact` 값은 같은 bundle의 `artifact-v2.json`과 정확히 같아야 한다.
`activate`, `operation`, `preconditions`, `retention` 같은 Backend 요청 계약 밖의
필드는 넣지 않는다.

## 책임 경계

DevSecOps는 다음을 담당한다.

- `info.yaml` 검증
- image build 또는 외부 image pull
- Gitleaks와 Trivy 차단 검사
- SBOM 생성
- GHCR digest image 발행
- `artifact-v2.json` 생성과 Actions artifact 업로드

Backend는 다음을 담당한다.

- GitHub Actions artifact 조회 인증 token 관리
- publish bundle 수집
- `challenge_slug`와 Backend `challenge_id` 매핑
- release 등록과 기존 revision 보존
- 같은 `challenge_id`와 `registry_revision`의 중복 수집 처리
- active release 전환과 롤백

Runtime과 Secure Provisioner는 다음을 담당한다.

- active release workload를 실제 K3s 자원으로 변환
- Service endpoint 생성
- NetworkPolicy와 격리 정책 생성
- workload cleanup

## 중복과 실패 처리

Backend poller가 이미 등록한 `registry_revision`을 다시 수집하면 중복으로
기록하고 전체 poll을 실패시키지 않는다. API를 이용한 수동 등록에서
`409 RELEASE_DUPLICATED`가 반환되는 경우에도 이미 등록된 revision으로 본다.
다른 409 code는 성공으로 처리하지 않는다.

CI가 실패하면 publish bundle을 만들지 않는다. Backend poller가 bundle 형식 오류,
challenge 매핑 실패 또는 GitHub API 통신 오류를 만나면 해당 bundle을 등록하지
않고 Backend 로그와 poll 결과에 원인을 남긴다.

Release 등록은 active release를 변경하지 않는다. 활성화와 롤백은 관리자 또는
Backend가 별도 API와 권한으로 수행한다.

## 혼합 포트 경계

Registry artifact는 포트별 `public` 값을 보존한다. 현재 Runtime `dev` 계약은
`ports: [int]`와 컨테이너 단위 `expose`를 사용하므로 한 컨테이너 안에서 public과
private 포트가 섞인 workload를 손실 없이 변환할 수 없다.

이 변경에서는 Runtime DTO를 임의로 확장하거나 포트를 누락하지 않는다. 혼합 포트
지원은 Runtime 팀이 확정한 DTO를 받은 뒤 별도 계약 변경으로 구현한다. 그전까지
DevSecOps smoke runner는 표현할 수 없는 혼합 노출 workload를 명시적으로 거절한다.

## 테스트

PR #7은 다음 자동 테스트를 만족해야 한다.

1. 생성된 `artifact-v2.json`이 Backend PR #26 validator 입력으로 유효하다.
2. `registry-publish.json`의 `artifact` wrapper가
   `artifact-v2.json`과 정확히 일치한다.
3. workflow에 Backend 직접 API 호출, `Idempotency-Key`, 자동 활성화가 없다.
4. publish bundle 이름이 Backend poller suffix 규칙을 만족한다.
5. digest가 아닌 GHCR image와 `scan_result` 실패 상태는 bundle로 발행되지 않는다.
6. 기존 단일·멀티 컨테이너 생성 테스트와 전체 unit test가 통과한다.

실제 통합 검증에서는 Backend poller가 Actions artifact를 내려받아 release를 한 번
등록하고, 같은 bundle을 다시 읽었을 때 duplicate로 처리하며 active release는
변하지 않는지 확인한다.

## 범위 밖

- active release 자동 전환
- Backend API base URL 배포와 service token 발급
- Runtime 혼합 public/private 포트 DTO 변경
- 실제 K3s cold pull, 인증 실패와 ImagePullBackOff 재현

위 항목은 각각 Backend 운영 연결과 PR #6 Runtime/K3s smoke 검증에서 처리한다.
