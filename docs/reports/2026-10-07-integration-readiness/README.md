# 연동 준비와 실제 산출물 소비 시험

기준일: 2026-10-07. 완료한 시험과 외부 준비가 필요한 항목을 구분합니다.
Backend·Scheduler·Runtime의 구현이나 운영 DB는 변경하지 않았습니다.

## 한눈에 보기

| 작업 | 결과 | 확인 범위 |
|---|---|---|
| DevSecOps main 단위 테스트 | 175개 통과 | 로컬 시험 서버를 포함한 테스트 |
| Backend #80 기존 관련 테스트 | 83개 통과 | 릴리스·Poller·참가자 파일 원본 테스트 |
| 실제 산출물 네 종류 소비 | 통과 | 메모리 SQLite, 임시 파일 저장소, 원본 Backend 코드 |
| 최신 GHCR 목록 조회 | 성공 | 46개 패키지, 161개 버전 |
| 기존 전체 발행 이미지 대조 | 37/37 존재 | GHCR 목록의 digest/version 참조, 실제 pull 시험 아님 |
| 승인 WEB Runtime smoke | 실패 | API 연결 시간 초과, 생성·삭제 결과 미확인 |
| GCS 저장 | 미실행 | Backend 저장 방식 유지, CI 업로드 비활성 |
| GHCR 삭제 | 0개 | 보호 목록 확인 전 삭제 금지 |

175개 테스트의 첫 실행에서는 샌드박스의 로컬 HTTP bind 제한으로 19개가
실패했습니다. 로컬 서버를 허용한 재실행에서 전체가 통과했습니다. 이를 운영
Runtime의 정상 동작 증거로 사용하지 않습니다.

## 사용한 실제 산출물

| 구분 | 문제 | revision | 성공한 main 실행 |
|---|---|---|---|
| 동적·파일 없음 | misc-cashout | 449 | [37341655773](https://github.com/MSG-CTF/2026_MSG_CTF/actions/runs/37341655773) |
| 동적·파일 있음 | pwn-random6 | 455 | [37345781390](https://github.com/MSG-CTF/2026_MSG_CTF/actions/runs/37345781390) |
| 정적·파일 없음 | forensic-is-this-job-legit | 466 | [37353062378](https://github.com/MSG-CTF/2026_MSG_CTF/actions/runs/37353062378) |
| 정적·파일 있음 | misc-hidden-order | 469 | [37354078451](https://github.com/MSG-CTF/2026_MSG_CTF/actions/runs/37354078451) |

새 revision 시험에는 이전 [pwn-random6 revision 330](https://github.com/MSG-CTF/2026_MSG_CTF/actions/runs/36388354543)의
실제 bundle도 사용했습니다. 정확한 artifact 이름·ID와 workflow 메타데이터는
[input.json](input.json)에 있습니다.

## Backend 소비 시험

실행 코드: [Backend #80](https://github.com/MSG-CTF/msg-backend/pull/80)의
`8ed90393220154cd0983a49dd52abf87534d0c9b`입니다.
Backend 소스는 수정하지 않고 원본 migrations, Poller, validator, DB 모델,
관리자 활성화 API, 참가자 상세·다운로드 API를 호출했습니다.

GitHub CLI로 실제 ZIP·JSON을 다운로드하고 workflow 성공·main·SHA 메타데이터를
조회했습니다. 로컬 소비 시험에서는 **GitHub HTTP 계층만 이 다운로드 파일로
대체**했습니다. 따라서 실제 GitHub API 인증·리다이렉트·증분 페이지 조회를
시험한 것은 아닙니다. 운영 DB나 GCS에도 접속하지 않았습니다.

확인 결과:

- 이전 revision 330 등록·활성화 후 새 revision 455 등록에도 active 330 유지.
- 관리자 활성화 API 호출 후에만 active 455로 전환.
- 새 릴리스 2건, 참가자 파일 기록 4건 등록.
- 컨테이너 image digest·포트와 합산 resource_profile의 DB 재조회 값 일치.
- 같은 산출물 재수집 시 등록 0건, 추가 ZIP·bundle 다운로드 호출 0건.
- 파일 있음 2종의 다운로드 200, 발행 ZIP과 바이트·SHA-256 일치.
- 문제 접근 권한 제거 후 파일 다운로드 403.
- 파일 없음 2종은 files 응답이 비어 있고 저장 object key 없음.

상세 결과: [backend-consumer-result.json](backend-consumer-result.json).

**현재 파일 표시 정책도 확인이 필요합니다.** 이 Backend 커밋은 동적 문제의
파일을 active release revision 기준으로, 정적 문제는 최신 revision 기준으로
선택합니다. 새 present:false만 등록했다고 이전 active의 파일을 곧바로 숨기지
않습니다. 이전 안내의 '최신 present:false 우선'과 달라 Backend에 현재 정책
확인을 요청합니다. 이번 시험은 새 present:false로 기존 파일을 숨기는 시나리오나
새 파일 변경 발행까지 검증한 것이 아닙니다.

## 전체 발행 목록과 GHCR 보존

[publication-handoff.json](publication-handoff.json)은 기존 전체 발행 검증
스냅샷입니다. 기준 source SHA는 `1dea73b652f9eeb98204c1fda7f66b9afb89505d`,
pipeline SHA는 `2d275ae083324eb83b776ace81daa3a669d2c11c`입니다.
전체 문제 37개, 동적 24개·정적 13개, publish bundle 24개, 참가자 bundle 37개
(ZIP 있음 28개·없음 9개)입니다. 이번 작업에서 전체 문제 CI를 재발행한 것은 아닙니다.
공유용 문제별 구분·revision·실행 링크는 [전체 발행 표](publication-table.md)에 있습니다.

[최신 삭제 없는 조회 실행](https://github.com/MSG-CTF/msgctf-devsecops/actions/runs/37563390461)은
성공했습니다. 2026-10-07 11:44 KST 기준 161개 버전 중 보존 분류 145개,
검토 후보 16개입니다. 날짜 기준이 지나면서 전날 후보 15개에서 1개가 늘었으며
삭제 권한이 생겼다는 뜻은 아닙니다.

[ghcr-check-result.json](ghcr-check-result.json)에 최신 조회 결과와 기존 발행
이미지 37개의 대조 결과를 기록했습니다. 37개 모두 해당 GHCR 목록에서 확인했습니다.
패키지 46개는 플랫폼·시험 패키지도 포함하므로 문제 수와 같지 않습니다.
이 목록의 존재 확인은 private pull, cold pull 속도, 실행 digest 확인이 아닙니다.

실제 삭제는 Backend active·rollback, Scheduler 대기·reset·재시도, Runtime 실행,
KOTH 복구·rollback의 최신 전체 목록과 OCI 참조 관계·관리자 승인 후에만 검토합니다.
모든 검토 후보의 `deletion_authorized`는 false입니다.

## Runtime 시험과 중단 지점

[승인 WEB smoke 실행 37562649497](https://github.com/MSG-CTF/2026_MSG_CTF/actions/runs/37562649497)은
11:34~11:45 KST에 `POST /internal/v1/instances` 연결 시간 초과로 실패했습니다.
복구용 같은 요청 재시도도 시간 초과였습니다. `SUCCEEDED` 생성·삭제 결과는 없습니다.
별도 로컬 무인증 HTTPS 점검도 TCP 443 연결 시간 초과였습니다.

정책상 승인된 기존 Grade Tampering digest와 기존 수동 workflow만 사용했습니다.
PR #16의 실제 publish bundle 자동 smoke를 시험한 것이 아닙니다.
target은 `b794d71b-51ef-45fd-87c1-9721e2999e79`, 시험 team은
`c0a720f9-4301-4a1f-804f-222769cf90b2`이고 제한은 300m/256MiB/512MiB였습니다.
Secret 원문을 열람하거나 다른 인증으로 바꾸지 않았습니다.

TCP 연결 시간 초과가 관찰됐지만 VM 중지·주소 변경·방화벽·서비스 리스너 중
어느 것이 원인인지는 아직 확인하지 못했습니다. Runtime 담당의 서버 확인이
필요합니다. 요청 수신 여부와 잔여 operation/workload/Namespace 확인도 부탁드립니다.
삭제 성공이나 '리소스가 전혀 생성되지 않음'을 단정하지 않습니다. 확인 전 재생성
시험을 반복하지 않으며 PWN·reset·전체 격리 시험도 실행하지 않습니다.

## 현재 발행 digest 정책 등록 요청

기존 승인 digest와 최신 발행 digest는 다릅니다. Runtime의 자동 승인을 가정하지 않습니다.
전체 이미지 주소는 [published-image-references.json](published-image-references.json)에 있습니다.

| 문제 | 발행 revision | 현재 발행 digest |
|---|---|---|
| web-grade-tampering | 458 | c409e49cf70a58be3ca19553b2db09da9d9607fd3462eaf00bdb29b20a44e39e |
| web-daily-point | 457 | 3b8129fe265d72dd8cc989a73dabf15c822ecc2a6e5cde95ec45119fb1397a11 |
| web-open-house | 461 | ad459de4ec1b5687be9b17cf445973344cf8aaee150bc759a5f02e79435d236d |

Runtime 담당이 UID·쓰기 경로·공개 포트를 검토해 정확한 digest 정책에 등록한
뒤에만 PR #16의 실제 bundle smoke 대상으로 사용합니다.

## GCS 준비 체크리스트

저장 담당은 Backend입니다. CI의 GCS 직접 업로드는 false로 유지합니다.
`msg-broker`/`2026msg_gcs`는 전달받은 설정이며 실제 IAM·bucket 접근은 검증하지 않았습니다.

- Backend·인프라: Backend 실행 Service Account와 ADC 인증 방식 확정.
- Backend: GCS용 Django storage backend·의존성·STORAGES 설정 준비.
- 인프라: bucket 위치, 비공개 접근, IAM 최소 권한과 보존 정책 확인.
- Backend: object key, 참가자 권한 검사, 다운로드 방식과 만료시간 결정.
- 담당 합의 후 실제 GCS 4종 저장·다운로드·재수집 시험.

CI용 Service Account를 Backend 계정으로 간주하거나 서비스 계정 key를
info.yaml·bundle·채팅에 넣지 않습니다. 운영 구성은 해당 담당자가 적용합니다.

## 다음 요청과 진행 순서

| 담당 | 요청 | 이후 작업 |
|---|---|---|
| DevSecOps 리뷰 담당 | PR #16 검증 범위와 새 결과 검토 | 승인 후 병합 및 caller 참조 동시 갱신 |
| Backend #26·#80 | 실제 HTTP Poller·개발 DB에서 4종 재확인, present:false 정책 확인 | 등록·다운로드 증거 및 병합·배포 SHA 공유 |
| Backend·KOTH | 별도 KothChallenge와 release 연결 확정 | KOTH 6개 실제 수집 시험 |
| Runtime #45 | API 접속 복구, 잔여 리소스 확인, 최신 digest 정책 승인 | 생성·접속·삭제 기능 smoke 재실행 |
| Backend·Runtime·Scheduler·KOTH | 기준 시각과 미확인 범위를 포함한 보호 digest 목록 | 삭제 후보 재계산 후 별도 삭제 PR·승인 |
| Backend·인프라 | GCS 인증·storage 설정 | 실제 GCS 저장·참가자 다운로드 시험 |

그다음 Backend → Scheduler → Runtime 생성·조회·reset·삭제 E2E와 네트워크 격리,
healthcheck·필수 실행 설정을 확인합니다. 다른 파트의 미지원 기능을 DevSecOps에서
임의로 완성하거나 시험 성공으로 표시하지 않습니다.

## 로컬 소비 시험 재현

[probe_backend.py](probe_backend.py)는 수동 증거 재현 도구입니다. 운영 pipeline에
추가하지 않으며 Backend 코드를 대체하지 않습니다. `.env` 없는 별도 Backend
checkout과 해당 커밋의 requirements 환경이 필요합니다. DB는 메모리 SQLite로,
저장은 자동 정리되는 임시 폴더로 강제합니다. 임시 계정은 시험 DB에만 생성합니다.

1. Backend #80의 위 SHA를 별도 checkout하고 pinned requirements로 venv를 구성합니다.
2. input.json을 `<evidence>/input.json`으로 두고 네 문제의 publish/user bundle을
   GitHub CLI로 내려받습니다. 디렉터리는 `<evidence>/artifacts/<slug>/publish/`와
   `<evidence>/artifacts/<slug>/user/`입니다. publish 폴더는 동적 두 문제만 필요합니다.
3. revision 330 bundle을 `<evidence>/artifacts/pwn-random6/revision-330/<artifact-name>/`
   아래에 둡니다. 정확한 run ID와 artifact-name은 input.json에 있습니다.
4. 아래 명령을 Backend venv의 Python으로 실행합니다.

```bash
/absolute/path/to/backend/.venv/bin/python probe_backend.py \
  --backend /absolute/path/to/backend \
  --evidence /absolute/path/to/evidence \
  --output /absolute/path/to/backend-consumer-result.json
```

기준 SHA가 다르거나 `.env`가 존재하면 실행을 거절합니다. 실행이 끝나면 DB와
저장 파일은 남지 않습니다. 결과 JSON에는 metadata만 기록하며 ZIP·토큰·플래그는
공유 저장소에 넣지 않습니다. 실행 중 403 로그 2개는 의도한 권한 거절 시험입니다.
