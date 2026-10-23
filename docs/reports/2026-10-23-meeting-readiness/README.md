# 10월 23일 회의 전 연동 점검

## 한눈에 보는 결과

2026-10-23 KST 기준 읽기 전용 조회와 로컬 계약 검사를 수행했습니다.
이미지 재빌드·발행, 인증된 Runtime 호출, Backend DB 변경, GCS 쓰기와 GHCR 삭제는 하지 않았습니다.

| 항목 | 확인 결과 | 아직 확인하지 않은 범위 |
| --- | --- | --- |
| 중앙 파이프라인 | main `5cd9ef6e`, 로컬 전체 테스트 237개 통과, 같은 main의 Actions 성공 | 모든 문제의 현재 취약점 DB 재검사 |
| 문제별 발행 | 37개 모두 현재 문제 폴더와 성공·미만료 산출물 일치 | 모든 이미지 pull·실행, Backend 개발 DB |
| 발행 종류 | 동적 24개 publish bundle, 전체 37개 user-files bundle | ZIP 내부 재검사와 참가자 실제 다운로드 |
| 문제 저장소 PR #89 | 현재 head 계약 CI 성공, 리뷰 대기 | main 적용·신규 발행·독립 Runtime 시험 |
| WEB 3개 실물 bundle | 출처·revision·digest·요청 변환 검사 통과 | 실제 서버 정책·토큰 권한·FLAG 주입 |
| 새 Runtime 주소 | 인증서 검증을 켠 무인증 GET에 HTTP 401 | 인증된 생성·접속·삭제, Actions runner 연결 |
| Backend #26·#80 | 이미 병합, 최신 main의 개발 배포 Actions 성공 | 서버 실제 SHA·Poller 실행·37개 DB 대조 |
| GCS | 10월 16일 성공 기록, 10월 20일 main 검증은 WIF 인증 실패 | 현재 main 재검증·개발 서버 인증·실제 ZIP 다운로드 |
| GHCR 정리 | 조회 가능한 46개 package·252개 version, 추가 보존 후 검토 후보 28개 | 사용 중·롤백 보호 목록과 삭제 승인 |

쉽게 말하면, 문제를 검사하고 전달할 산출물은 준비되어 있습니다. 남은 핵심은
새 서버에서 허용된 이미지와 인증으로 실행하고, Backend 개발 서버에서 수집·파일 제공까지 확인하는 것입니다.

## 증거와 기준 버전

- 중앙 main: `5cd9ef6eb43f13af5ff3bb323707df2afdfdd266`
- 문제 main: `84742c511bb126a5e94d9d21c85ddf9b0611b923`
- Backend main: `ab849ffbaf026da98ee6971f03e57c8c8e6cdb94`
- Runtime 저장소 정책 확인 ref: `a4c1f47d5a96f44222c87cc3fd458943771a61b7`의 `dev`
- [중앙 main CI](https://github.com/MSG-CTF/msgctf-devsecops/actions/runs/39910995435)
- [문제 저장소 PR #89](https://github.com/MSG-CTF/2026_MSG_CTF/pull/89), head `3e5601755be8708d0b9113a9138790c3cc0e4daa`
- [PR #89의 caller CI](https://github.com/MSG-CTF/2026_MSG_CTF/actions/runs/39911426145): 변경 문제 0개이므로 이미지 발행·Runtime 실행은 하지 않음
- [Backend main CI와 개발 배포 기록](https://github.com/MSG-CTF/msg-backend/actions/runs/39719631467): `deploy-development` 성공, `verify-gcs`는 skipped

중앙 #20·#24와 문제 저장소 #79는 이미 병합됐습니다. #89는 최신 중앙 코드를 문제
저장소에 적용하고 발행과 Runtime 시험을 분리하는 후속 PR이며, 이번 점검에서 병합하지 않았습니다.
Backend #26·#80도 병합됐으므로 이 두 PR의 병합을 다시 기다리는 단계는 아닙니다.
다른 담당자의 중앙 Draft #19는 수정하지 않았습니다.

## 37개 발행 대조

15:45 KST에 현재 문제 main을 기준으로 다시 조회했습니다.

- [문제별 표](publication-table.md): 정적 13개·동적 24개, 37개 모두 문제 폴더 일치
- [정확한 run·artifact·revision 목록](publication-state.json): Backend Poller 대조에 사용
- 동적 문제는 publish bundle과 user-files bundle, 정적 문제는 user-files bundle을 확인
- 성공한 전체 workflow의 산출물만 사용하며 실패한 run의 부분 성공을 대신 인정하지 않음
- 문제 폴더가 바뀌지 않았다면 과거 성공 run의 산출물이 일치할 수 있으므로 재발행 불필요

이 결과는 ZIP 본문·GHCR manifest·현재 취약점 DB·Backend DB·운영 배포를 전부
검증했다는 뜻이 아닙니다. 동일 문제 폴더 비교와 공통 workflow 변경의 실제 반영도 구분합니다.

## Runtime 시험 준비와 추가 확인

Runtime팀이 전달한 주소는 `https://34.9.255.41/internal/v1`, target은
`gcp-msg-runtime-k3s`입니다. [연결 결과](runtime-connection.json)는 이 컴퓨터에서
토큰 없이 수행한 HTTPS GET 결과이며 HTTP 401을 확인했습니다.

로컬 Python의 기본 CA 경로에서는 issuer 확인 오류가 있었습니다. 이번 프로세스에만
설치된 `certifi`의 CA 파일을 지정해 재실행했고 인증서 검증을 유지한 401을 확인했습니다.
시스템 설정이나 서버 인증서를 바꾸지 않았고, 인증서 검증을 끄지 않았습니다.
GitHub Actions runner에서 새 주소를 호출한 결과는 별도로 필요합니다.

문제 저장소의 변수는 아직 이전 주소·target입니다. Secret 원문은 조회하지 않았습니다.

| 항목 | 확인 상태 | 다음 처리 |
| --- | --- | --- |
| `RUNTIME_API_URL` | 이전 Tailscale 주소 | #89 적용과 Runtime 확인 후 새 HTTPS 주소 반영 |
| `RUNTIME_TARGET_ID` | `younhochoi-k3s-test` | 새 target의 사용·토큰 범위 확인 후 갱신 |
| `RUNTIME_CI_TEAM_ID` | 값 설정 여부만 확인 | 새 서버 제한 토큰에 해당 팀이 허용되는지 확인 |
| `RUNTIME_API_TOKEN` | Secret 존재·갱신 시각만 확인 | 기존 Secret과 새 서버 설정의 일치·제한 권한 확인 |

### 실제 발행 bundle 3개의 사전 검사

원본 run은 [39367715071](https://github.com/MSG-CTF/2026_MSG_CTF/actions/runs/39367715071),
revision은 573, attempt는 1입니다. 실제 bundle을 내려받아 현재 중앙의 출처 선택·
bundle 검사·요청 변환 함수를 실행했으며 서버 요청은 보내지 않았습니다.

| 문제 | artifact ID | digest 요약 | 계약 검사 | 저장소 정책 |
| --- | ---: | --- | --- | --- |
| web-grade-tampering | 12239714660 | `3a3de9c6…652fdb` | 통과 | `create_enabled`, `requires_flag: true` |
| web-daily-point | 12239792858 | `fc7c762b…2a4816` | 통과 | `create_enabled`, `requires_flag: true` |
| web-open-house | 12239944783 | `8d8492c1…3b5ea7` | 통과 | `create_enabled`, `requires_flag: true` |

[상세 검사 결과](smoke-bundle-preflight.json)에 전체 image·artifact 이름·자원·포트를 기록했습니다.
`internal_connections`와 `expose`는 요청에 없으며 healthcheck 보존과 `exposed_ports` 변환도 확인했습니다.
형식 검사는 가상 instance·team UUID를 사용했으므로 실제 인증 권한 검증이 아닙니다.

중요하게, 이 3개 최신 digest에는 저장소 정책상 `ci_smoke_enabled: true`가 명시되어 있지
않고 모두 FLAG가 필요합니다. 현 직접 smoke 변환기는 FLAG나 Backend `secret_ref`를
자동 주입하지 않으므로 형식 통과만으로 실행 가능하다고 판단하지 않습니다.
Runtime이 승인한 CI용 digest와 FLAG 준비 방식을 먼저 확인해야 합니다.
저장소 정책과 실제 서버 배포 정책이 같다는 점도 아직 확인하지 않았습니다.

Runtime에 전달할 추가 확인사항:

> 기존 CI 토큰이 새 target과 CI 전용 팀에 계속 유효한지, 현재 배포 commit SHA가
> 무엇인지 확인 부탁드립니다. 최신 WEB bundle 3개는 아래 상세 JSON의 digest이고
> 저장소 정책에서 모두 FLAG가 필요합니다. 직접 smoke에서 사용할 수 있는 정확한
> 승인 digest와 CI 사용 허용 여부, 필요한 FLAG의 안전한 서버 측 주입 방법을 확인
> 부탁드립니다. 기존 CI용 이미지로 기본 기능만 시험한다면 최신 문제 검수와 구분하겠습니다.
> 토큰·FLAG 원문은 댓글이나 채팅으로 전달하지 않으셔도 됩니다.

## Backend와 참가자 파일

Backend #26·#80 병합 및 개발 배포 성공 기록은 확인했지만 이번에 서버 DB를 읽거나
Poller·GCS를 실행하지는 않았습니다. 현재 37개 목록으로 실제 등록을 대조해야 합니다.

파일 저장 담당은 Backend입니다. CI는 ZIP·manifest를 Actions artifact로 발행하고,
Backend Poller가 수집·재검증한 뒤 `default_storage`를 통해 GCS에 저장합니다.
CI 직접 GCS 업로드는 켜지 않았습니다.

확인할 항목:

1. 최신 37개 목록과 DB의 slug·revision·containers·digest 대조, 미매핑 KOTH 처리 결과
2. Poller timer 실행 상태, 최초 수집·중복 다운로드 방지·실패 재시도 결과
3. 실제 ZIP 수집과 GCS 객체 존재·다운로드 권한, 파일 없음·버전 전환·롤백 동작
4. 현재 서버 배포 SHA·migration 상태, 최신 발행본의 일반 env·비밀값 준비 여부

환경변수 자동 보강은 [Backend #129](https://github.com/MSG-CTF/msg-backend/pull/129)에서
별도로 리뷰 중입니다. schema 2.0 bundle 등록 시 같은 소스 커밋의 저장소 env를 읽는
경로이며 중앙 Draft #19의 schema 2.1 발행과 구분합니다. 이번에 다른 담당자의 코드를
수정하거나 환경변수·FLAG를 bundle에 임의로 추가하지 않았습니다.

### GCS의 성공 기록과 최근 실패를 구분

- [10월 16일 verify-gcs 성공](https://github.com/MSG-CTF/msg-backend/actions/runs/38867816237): 당시 테스트 브랜치의 검증
- [10월 20일 main verify-gcs 실패](https://github.com/MSG-CTF/msg-backend/actions/runs/39439736084): `Authenticate with registered GCP identity` 단계
- 오류 분류: `unauthorized_client`, `The given credential is rejected by the attribute condition.`
- 최신 main 일반 CI의 `verify-gcs` skipped는 이 인증 실패가 해결됐다는 증거가 아님

Backend와 GCP IAM 담당자에게 main ref의 WIF Provider 허용 조건 및 서비스 계정
연결을 확인하고 현재 main에서 `verify_gcs=true`로 재검증하도록 요청합니다.
이번 점검에서는 IAM을 변경하거나 기존 배포 계정·Secret을 교체하지 않았습니다.

## GHCR 보존 검토

조회 시각은 15:49 KST이며 이 계정에서 보이는 범위는 package 46개·version 252개입니다.
package 수는 문제 수가 아닙니다. 멀티 컨테이너 문제·자체 시험·과거 플랫폼 이미지도 포함합니다.

기본 정책 계산은 보존 221개·검토 후보 31개였습니다. Runtime 저장소의 WEB·PWN
정책에 남아 있는 32개 digest를 추가 보호하여 보존 224개·후보 28개로 다시 계산했습니다.
blocked 상태를 포함해 정책 파일에 남은 digest는 보수적으로 모두 보호했습니다.

- [삭제 없는 검토표](ghcr/cleanup-plan.md)
- [상세 판정](ghcr/cleanup-plan.json)
- [조회 snapshot](ghcr/inventory.json)
- [추가 보존 목록](ghcr/protected-repository-policy-images.json)
- 정책 기준: Runtime 저장소 위 ref의 `config/web-image-policies.json`, `config/pwn-image-policies.json`
- 실제 삭제 0개, `deletion_enabled: false`

현재 Backend active·rollback과 Scheduler 진행 중·reset·재시도, KOTH의 전체 사용
목록을 합친 결과는 아닙니다. 후보 28개도 삭제 승인이 아니며 현 단계에서는 보존합니다.
이 JSON들은 조회 당시 snapshot이므로 실제 삭제 전에는 최신 목록을 다시 조회해야 합니다.

## 회의에서 정할 것과 다음 순서

1. #89 리뷰 후 병합하고 Runtime 확인이 끝나면 저장소의 새 주소·target을 반영합니다.
2. 제한된 CI 인증·이미지·FLAG 조건을 확인한 뒤 승인된 단일 WEB 하나로 별도 생성·삭제 시험을 합니다.
3. 공개 URL 응답·cold pull·실행 digest·물리 리소스 정리와 정상/실패 healthcheck는 각 증거를 따로 확인합니다.
4. Backend 개발 서버에서 37개 수집 대조 및 실제 참가자 ZIP 다운로드, 최신 main GCS 인증을 확인합니다.
5. Backend → Scheduler → Runtime의 생성·접속·reset·삭제를 대표 문제로 연결 확인합니다.
6. KOTH의 공용 배포·버전 연결·복구 담당과 Windows 실행·초기화 계약은 해당 담당자와 확정합니다.
7. 전체 운영·롤백·OCI 보호 목록을 받은 뒤에만 GHCR 삭제를 별도 승인받습니다.

Actions 비용을 늘리지 않도록 이번 작업은 변경 없는 전체 문제 재빌드나 전체 재발행을
하지 않았습니다. #89 병합만으로 기존 문제를 다시 발행할 필요는 없습니다. 첫 실증도
기존 성공 bundle 하나를 재사용하고, 이후 필요한 문제만 검사·발행하는 순서로 진행합니다.
push와 PR의 중복 빌드 축소는 author branch의 검사 공백이 없도록 별도 검토하며,
보안 검사를 끄거나 스캔 실패를 성공 처리하는 최적화는 하지 않습니다.

## 이번 작업의 범위

실행한 것: 최신 발행 이력 조회, 실제 WEB 3개 bundle 계약 검사, 로컬 전체 테스트,
토큰 없는 Runtime HTTPS 점검, 삭제 없는 GHCR 목록·추가 보존 계산, 협업 요청 정리.

실행하지 않은 것: #89 병합, 설정·Secret·IAM 변경, 이미지 생성·재발행·pull,
인증된 Runtime 생성·삭제, Backend DB·Poller 실행, GCS 쓰기, GHCR 삭제.

테스트용 checkout과 원본 다운로드는 최종 자료를 남긴 뒤 정리합니다.
