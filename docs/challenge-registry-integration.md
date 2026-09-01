# Challenge Registry 통합 검증

## 검증 범위

2026년 8월 31일, 실제 GitHub Actions 성공 실행의 이미지 발행 결과를 입력으로
이번 브랜치의 generator가 publish bundle 후보를 다시 생성했고, 이를 백엔드
PR #26의 Challenge Registry API에 등록했습니다. 운영 서버와 운영 DB는 사용하지
않았으며 PR #26 commit `fdba92d`를 SQLite 데모 설정으로 실행했습니다.

## 입력 증거

- DevSecOps Actions run: `32959545593`
- source commit: `8cf8892588ca43fab2fd57c16d32b8791cac6b8b`
- 원본 artifact: `info-valid-32959545593-1-96109d17d15a4df6b2d1db5a4f4921be-publish-bundle`
- `challenge_slug`: `info-valid`
- 원본 `revision`: `19`
- `scan_result`: `PASS`

원본 Actions artifact는 현재 `main` 코드로 생성돼 `registry_revision`과
`isolation_profile`이 없었습니다. 이번 브랜치의 generator로 원본 metadata,
container results, SBOM과 동일한 image digest를 사용해 후보 bundle을 재생성했고,
그 후보에 `registry_revision: 19`와 `isolation_profile: WEB`이 추가됐습니다.
따라서 아래 등록 결과는 새 계약의 로컬 호환성 증거이며 새 계약이 Actions
`main`에서 이미 발행됐다는 뜻은 아닙니다.

컨테이너는 다음 digest로 고정됐습니다.

```text
ghcr.io/msg-ctf/challenges/info-valid/web@sha256:3f9a465ff4ca0d25db1a415f384576b1b0832ca681fbf03e2b575f24859b3ef0
ghcr.io/msg-ctf/challenges/info-valid/helper@sha256:dcb7908ca45b38f72f3f3a41023a52ef6972be007b793dd2606b97018c017f1e
```

두 이미지는 GHCR push를 성공한 Actions publish 결과입니다. 로컬 GitHub token은
private package read 권한이 없어 별도 manifest 재조회는 HTTP 401로 거절됐으며,
이 검증은 K3s cold pull 성공 증거로 사용하지 않습니다.

## 등록 결과

PR #26의 현재 등록 endpoint는 최종 `registry-publish.json` 계약보다 오래된
`{"artifact": <artifact-v2>, "note": ...}` 요청 형식을 사용합니다. 따라서 로컬
호환성 검증에서는 재생성한 후보의 `artifact-v2`를 이 wrapper에 넣어 등록했습니다.
현재 workflow가 전송하는 `registry-publish.json` 전체 요청은 백엔드 최종 endpoint가
병합·배포된 뒤 별도로 검증해야 합니다.

로컬 Registry API는 다음 결과를 반환했습니다.

```json
{
  "code": "SUCCESS",
  "release_id": "1107b1f1-90e9-4467-9605-b45b86920412",
  "version": 1,
  "registry_revision": 19,
  "challenge_slug": "info-valid",
  "container_count": 2,
  "is_current": false,
  "is_deployable": false
}
```

조회 API와 DB를 다시 확인한 결과 `challenge_releases`에 revision 한 행,
`release_containers`에 `web`과 `helper` 두 행이 저장됐습니다. 각 컨테이너의
digest와 `ports[].public`도 입력 bundle과 일치했습니다.

`is_deployable: false`는 등록 실패가 아닙니다. PR #26의 기존 Scheduler 게이트가
멀티 컨테이너 또는 여러 public 포트를 활성화하지 못하도록 제한하기 때문입니다.

## NetworkPolicy 경계

publish bundle은 raw Kubernetes NetworkPolicy를 포함하지 않습니다. 다음 의도만
전달합니다.

- `isolation_profile`: `WEB | PWN`
- `workload.containers[]`
- `ports[].public`
- 선택형 `workload.internal_connections[]`

Runtime/Secure Provisioner는 이 값으로 default-deny, DNS, public ingress와 선언된
컨테이너 간 TCP 통신 정책을 생성합니다. 출제자와 CI는 임의 egress 또는 Kubernetes
NetworkPolicy를 주입할 수 없습니다.

## 운영 연결 전 남은 조건

- 백엔드 Registry 구현의 `main` 병합과 배포
- DevSecOps service Bearer token 발급
- `registry-publish.json` 전체 요청과 `Idempotency-Key` 계약 반영
- revision 등록과 active 전환의 단일 transaction 처리
- 멀티 컨테이너 Scheduler 계약과 Registry 모델 통합
- 운영 endpoint에서 GitHub Actions 실제 전송 재검증

따라서 이번 결과는 실제 Actions 이미지 발행 결과로 재생성한 publish bundle
후보의 **로컬 Challenge Registry 등록 성공** 증거이며, 운영 Challenge Registry
연결 완료 증거는 아닙니다.
