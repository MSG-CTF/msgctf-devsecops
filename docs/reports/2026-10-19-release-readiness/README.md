# 병합 후 문제 공급망 연동 점검

기준일: 2026-10-19 KST. 이 문서는 실제로 조회·검사한 범위와 담당자 기록을 구분합니다.
문제 전체 운영 배포 완료 보고서는 아닙니다.

## 이번에 직접 확인한 내용

| 항목 | 결과 | 증거·한계 |
|---|---|---|
| 현재 문제 목록 | 동적 24개·정적 13개, 총 37개 | main `25e7c6b636ba11b16c77e09274563fe92fbb9003`의 문제 폴더별 info.yaml 기준 |
| 성공 발행과 문제 폴더 대조 | 36개 일치, pwn-random6 1개 변경 | [전체 표](publication-table.md), [원본 메타데이터](publication-state.json) |
| Notebook 새 발행 | revision 529, 웹·DB 검사·GHCR 발행·bundle 성공 | [main 실행](https://github.com/MSG-CTF/2026_MSG_CTF/actions/runs/39143988846) |
| Notebook GHCR 실체 | 웹·DB의 정확한 digest 버전이 GHCR 목록에 존재 | package version ID `1405440967`, `1405443160`; 새 이미지 pull은 이번에 실행하지 않음 |
| Notebook Runtime 정책 | 새 웹·DB digest와 포트가 승인 정책에 일치 | Runtime dev `8f95ef9e4bbf2aaeb8f4e3fe22807c7e76a523f0`; 서버 정책 파일 직접 조회는 아님 |
| Notebook 참가자 파일 | revision 529, present:false | user-files artifact ID `12142143306`; ZIP은 생성하지 않는 정상 유형 |
| 현재 연결 | 인증서를 검증한 HTTPS GET의 401 응답 | 토큰 미사용, 생성·삭제 미실행; 서버 배포 SHA나 토큰 유효성 확인 아님 |
| 공급망 코드 | 단위 테스트 207개 통과 | 기존 192개와 발행 대조·연결 주소 회귀 검사 15개; Docker 빌드는 이번 로컬 시험 범위 아님 |

폴더 대조는 전체 저장소 SHA가 아니라 문제별 Git tree로 비교합니다. 다른 문제나
workflow만 바뀐 경우 해당 문제의 과거 성공 발행을 무조건 누락으로 처리하지 않습니다.
반대로 폴더가 바뀌면 과거 성공 이미지를 최신 문제의 결과로 표시하지 않습니다.
공통 루트 설정 변경, 현재 취약점 DB, bundle 내용과 모든 이미지 digest 실체는
별도 검증 대상입니다. 이 대조만으로 36개 모두 배포 가능하다고 판단하지 않습니다.

## pwn-random6에서 남은 것

- 현재 main의 문제 폴더는 마지막 성공 발행 revision 455와 다릅니다.
- [후속 main 실행 38238229618](https://github.com/MSG-CTF/2026_MSG_CTF/actions/runs/38238229618)은
  `Trivy 취약점 차단 검사`에서 실패했습니다.
- 해당 실패 실행에서 먼저 올라온 참가자 파일 artifact는 Backend 수집 대상인
  성공 실행의 자료가 아니므로 이번 대조에서 제외했습니다.
- [문제 저장소 #81](https://github.com/MSG-CTF/2026_MSG_CTF/pull/81)의 수정본은
  branch CI에서 pwn-random6을 포함해 통과했지만 아직 Draft·미병합입니다.
- 수정본의 승인·main 반영 후 해당 문제를 다시 검사·발행하고 새 revision과
  digest를 Backend에 전달해야 합니다. revision 455를 최신으로 간주하지 않습니다.

## Notebook 실제 전달 자료

```text
challenge_slug: web-notebook
registry_revision: 529
source_sha: 25e7c6b636ba11b16c77e09274563fe92fbb9003
run_id: 39143988846
publish_artifact_id: 12142484368
publish_artifact_name: web-notebook-39143988846-1-b730c37ae26045e7acab290a5328dfb3-publish-bundle
user_files_artifact_id: 12142143306
user_files_artifact_name: web-notebook-39143988846-1-b730c37ae26045e7acab290a5328dfb3-user-files-bundle
web: ghcr.io/msg-ctf/challenges/web-notebook/web@sha256:61cebc237880b45ec1157b60d892429bfa6b237fbee83f339cd4e73d659b4a8b
db: ghcr.io/msg-ctf/challenges/web-notebook/db@sha256:2bcb74bbea090364d812459b3039d6a79ce0521a24a4d3fee7ff8a4f6d32bf3d
```

내려받은 artifact-v2.json과 registry-publish.json의 artifact가 일치하고,
컨테이너 결과의 image·PASS·CycloneDX SBOM 파일이 bundle과 연결되는지 확인합니다.
FLAG 원문과 원본 ZIP·문제 소스는 이 보고서에 넣지 않습니다.
새 DB 정책은 FLAG를 필수로 요구하며 웹 8080만 공개하고 DB 5432는 비공개입니다.
두 이미지는 `ci_smoke_enabled:false`이므로 기존 단일 WEB 직접 smoke 대상으로
임의 사용하지 않습니다. FLAG가 필요한 실제 경로는 Backend를 통해 시험합니다.

## 병합·배포 상황

- Backend #80·#101이 #26에 포함됐고 [#26](https://github.com/MSG-CTF/msg-backend/pull/26)은
  main에 병합됐습니다. 더 이상 #26·#80 병합을 기다리는 상태가 아닙니다.
- Backend 최신 main `5c227f538a3e25c78b54193e8e468a94a73172f9`의
  [개발 서버 배포](https://github.com/MSG-CTF/msg-backend/actions/runs/39145334521)가 성공했습니다.
- Scheduler #60이 dev에 반영됐고 최신 dev `18c63edb7e363eabfd03ed4cc7b2d7b7380736ec`의
  [배포](https://github.com/MSG-CTF/instance-scheduler/actions/runs/39141454855)가 성공했습니다.
- Runtime #45·#46과 후속 수정이 dev에 반영됐고 최신 dev
  `8f95ef9e4bbf2aaeb8f4e3fe22807c7e76a523f0`의
  [배포](https://github.com/MSG-CTF/secure-provisioner/actions/runs/39144969399)가 성공했습니다.

성공한 배포 job과 main/dev의 코드 반영을 확인한 것입니다. 모든 K3s target과 서버별
정책·운영 DB·GCS 실행 계정이 자동으로 동일해졌다고 추정하지 않습니다.

## 이전 기록에서 진전된 것

- [Backend GCS 실행](https://github.com/MSG-CTF/msg-backend/actions/runs/38867816237)은
  지정된 `gcs-file-upload-devops@msg-broker.iam.gserviceaccount.com`을 명시해 실제
  GitHub 4종 산출물과 GCS 저장·다운로드·중복 방지 등 130개 검사를 통과했습니다.
  runner의 임시 PostgreSQL·HTTP 기준이며 운영 DB·서버 실행 계정의 저장 성공과 구분합니다.
- [이전 실패 인스턴스 조회](https://github.com/MSG-CTF/2026_MSG_CTF/actions/runs/38935581594)는
  Runtime 상태가 TERMINATED임을 확인했습니다. 원래 DELETE operation의 FAILED 기록은
  남아 있고 직접 물리 K3s 검사는 수행하지 않았으므로 이를 과거 operation 성공으로 바꾸지 않습니다.
- [Runtime #54](https://github.com/MSG-CTF/secure-provisioner/pull/54)에는 담당자가 실제
  Backend 경로에서 새 Notebook 이미지·FLAG 변경·누락 차단·예약 반납·리소스 정리를
  검증한 기록이 있습니다. 이번 작업에서 직접 다시 생성한 결과는 아닙니다.

## 다음 작업과 담당

### 이번에 직접 실행한 Grade 기능 smoke

[문제 저장소 수동 Actions 39151393362](https://github.com/MSG-CTF/2026_MSG_CTF/actions/runs/39151393362)가
성공했습니다. 기존 main의 승인된 WEB 시험 workflow를 변경 없이 한 번 실행했습니다.

- 대상: CI 전용 `younhochoi-k3s-test`, 승인 Grade digest `c409e49c…44e39e`.
- 생성 Operation: SUCCEEDED, 60.680초. 삭제 Operation: SUCCEEDED, 45.699초.
- 공개 endpoint의 컨테이너 이름·포트·protocol·주소 형식이 요청과 일치합니다.
- 결과·추적 식별자와 미검증 범위는 [실행 영수증](runtime-smoke-result.json)에 보존했습니다.
- workflow가 승인 digest로 시험용 artifact를 만드는 경로입니다. revision 1은
  시험 입력이며 실제 Backend release revision 등록·전환을 뜻하지 않습니다.
- 반환된 접속 주소를 runner에서 HTTP GET으로 검사하지는 않았습니다.
  실제 노드 imageID, 캐시 없는 pull, 물리 Namespace·Pod·Service 제거 확인도
  이번 시험에 포함되지 않습니다. 생성·삭제 시간은 GHCR pull 시간으로 사용하지 않습니다.
- Backend Poller·Challenge Registry·Scheduler·Broker를 거치는 전체 E2E는 아닙니다.

[PR #20 코드 CI](https://github.com/MSG-CTF/msgctf-devsecops/actions/runs/39151297362)와
[수동 HTTPS 연결 점검](https://github.com/MSG-CTF/msgctf-devsecops/actions/runs/39151306208)도
코드 커밋 `9ab898f484694e8d18644c56018547296a477536`에서 성공했습니다.
두 실행의 main 전용 샘플·KOTH 발행 생략은 PR 브랜치의 의도된 조건입니다.
수동 점검은 Python 기본 신뢰 저장소에서 TLS 검증과 무인증 401을 확인했습니다.
이후 추가한 실행 영수증과 문서는 코드 변경이 아닙니다.

### GHCR 읽기 전용 정리 후보 갱신

[수동 Actions 39150931566](https://github.com/MSG-CTF/msgctf-devsecops/actions/runs/39150931566)이
성공했습니다. 패키지 46개·이미지 버전 170개 중 보존 146개·추가 검토 24개입니다.
패키지는 컨테이너·테스트 자료도 포함하므로 문제 수 37개와 같지 않습니다.
결과는 `BLOCKED_PENDING_USAGE_CONFIRMATION`, `deletion_enabled:false`입니다.
24개는 삭제 승인 목록이 아니며 실행·대기·reset·active·rollback·KOTH 참조와
OCI index 관계를 확인하기 전에는 삭제하지 않습니다. 원본 보고서는 해당 실행의
`ghcr-cleanup-39150931566-1` artifact에서 확인합니다.

### 남은 작업 순서

| 순서 | 작업 | 담당·완료 기준 |
|---|---|---|
| 1 | 새 연결 점검 주소 입력 방식 리뷰 | DevSecOps: 예전 GCP IP 고정 제거, 토큰 없는 Actions 점검 결과 보관 |
| 2 | pwn-random6 수정본 승인·main 재발행 | 출제자·리뷰 담당 + DevSecOps: 최신 소스의 검사·GHCR·두 bundle 성공 |
| 3 | 개발 서버의 전체 산출물 수집 집계 | Backend: 37개 slug와 정적/동적 파일, 동적 release, 중복·active 유지·실제 저장소 확인 |
| 4 | 일반 문제 대표 실행과 실패 경로 QA | Backend·Scheduler·Broker·Runtime + DevSecOps: release_id·환경변수·healthcheck·접속·reset·삭제 대조 |
| 5 | Afterimage·공유 KOTH 네트워크 확정 | 출제자·책임자·Runtime: #49 통신 경로 승인, 실제 허용·차단 시험, KOTH 별도 운영·release 연결 결정 |
| 6 | 나머지 문제별 실행 정책 승인·전체 QA | Runtime·출제자 + DevSecOps: 정확한 digest의 UID·쓰기 경로·FLAG·공개 포트·필수 통신 확인 |
| 7 | GHCR 보존 대상 확정 뒤 정리 승인 | Backend·Scheduler·Runtime·KOTH: active·실행·대기·reset·롤백 digest 합집합; 합의 전 삭제 금지 |

DevSecOps #19와 문제 #81은 다른 작성자의 Draft 작업으로 이번에 수정·병합하지 않습니다.
기존 schema 2.0 발행에 실행 설정을 추가하는 관리자 경로와 새 schema 2.1 발행 경로를
구분해 검토하며, 준비되지 않은 계약을 caller에 먼저 적용하지 않습니다.
CI가 GCS를 직접 저장하는 기능은 계속 비활성입니다. 저장 담당은 Backend입니다.

## 재현

```bash
python3 -B -m scripts.audit_publication_state --output-dir /absolute/path/to/report
python3 -B -m unittest discover -s tests
```

발행 대조는 GitHub CLI 읽기 인증만 사용하며 토큰을 출력·복사하지 않습니다.
macOS 기본 Python CA 경로가 비어 처음 연결 점검이 실패해, 기존 시스템 CA를
`SSL_CERT_FILE=/etc/ssl/cert.pem`으로 명시한 재실행과 curl에서 TLS 검증·401을 확인했습니다.
인증서를 임의 신뢰하거나 검증을 끄지 않았습니다. 운영 인스턴스를 생성·삭제하지 않았습니다.
