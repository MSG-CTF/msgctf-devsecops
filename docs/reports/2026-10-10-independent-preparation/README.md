# PR #79와 독립적인 연동 준비

기준일: 2026-10-10 KST. 이 보고서는 준비 점검이며 운영 배포 완료 보고서가 아닙니다.

## 기준과 수행 범위

- 문제 저장소 main: `b95a1562491190ccf2bcb54beb34d8e8b76a99f7`.
- DevSecOps main: `40513968fa9e4a8a624dc7c11a6e0a399aada323`을 기존 PR #17에 반영했습니다.
- Backend #80 확인 커밋: `9312f9a91bf1d029b590be9c67dc3bfc46b7c3ac`.
- Runtime 정책 코드 확인 커밋: `701567f410a68518bb628463c8d5480559f31efc`.
- 문제 파일, Backend, Scheduler, Runtime 코드는 수정하지 않았습니다.
- GHCR 발행·삭제, GCS 업로드, 운영 DB 등록, 실제 Runtime 생성·삭제는 실행하지 않았습니다.

저장소 루트에는 양식용 info.yaml과 실제 문제 폴더가 함께 있습니다.
실행 설정 점검 도구가 루트 양식만 1개 문제로 선택하는 경우를 수정했습니다.
실제 문제 폴더가 있으면 우선 점검하며, 단일 문제 경로 입력은 그대로 지원합니다.
이 수정은 점검 대상 탐색에만 적용되며 빌드·취약점 gate나 발행 조건을 완화하지 않습니다.

macOS의 README.md/readme.md 충돌은 임시 문제 checkout에서 해당 루트 문서만
sparse checkout으로 제외했습니다. 문제 폴더는 모두 유지했고 깨끗한 main 상태를 확인했습니다.

## 참가자 파일 점검

| 구분 | 파일 있음 | 파일 없음 | 합계 |
|---|---:|---:|---:|
| 동적 | 16 | 8 | 24 |
| 정적 | 12 | 1 | 13 |
| 전체 | 28 | 9 | 37 |

- info.yaml 검증과 참가자 파일 경로·크기·파일 수 검사를 37개 모두 통과했습니다.
- ZIP 28개와 파일 없음 manifest 9개를 별도 임시 폴더에 생성했습니다.
- 같은 main snapshot을 두 번 패키징한 전체 결과가 바이트 단위로 같았습니다.
- 압축 전 전체 파일 합계는 166,622,309바이트입니다. 한 문제당 100 MiB 제한은 유지했습니다.
- 가장 큰 문제 rev-ezpz는 압축 전 96,848,220바이트로 현재 한도 안입니다.
- 시험용 revision은 1입니다. 실제 release revision이나 Backend 등록 데이터로 사용하지 않습니다.
- GCS 저장 계획 생성도 dry-run이며 인증과 업로드를 실행하지 않았습니다.
- 이 결과는 참가자 공개 내용 승인이나 secret·악성코드 검사 완료를 의미하지 않습니다.

문제별 검사 metadata와 ZIP checksum은 [participant-files-check.json](participant-files-check.json)에
있습니다. ZIP 본문과 원본 참가자 파일은 저장소에 넣지 않습니다.

팀 공유용 전체 문제 목록은 [참가자 파일 표](participant-files-table.md)에 있습니다.

### 최근 실제 Actions 발행 확인

[Daily Point main 실행 37888914252](https://github.com/MSG-CTF/2026_MSG_CTF/actions/runs/37888914252)은
main snapshot과 같은 SHA로 성공했습니다.

- user artifact: `web-daily-point-37888914252-1-9b0afd9907bc449f84347d30fc67039d-user-files-bundle`.
- artifact ID: `11597860681`.
- 내려받은 manifest: schema 1.0, revision 500, source_ref refs/heads/main,
  source_sha b95a1562491190ccf2bcb54beb34d8e8b76a99f7, present:false.
- 문제 build·scan·aggregate와 publish bundle 발행 job도 성공했습니다.
- K3s smoke는 skipped입니다. GCS 저장·Backend 다운로드 성공 증거는 아닙니다.

이번 작업은 전체 37개 Actions 재발행이 아닙니다.
기존 전체 발행 스냅샷은 [10월 7일 보고서](../2026-10-07-integration-readiness/README.md)에 보존합니다.

## 문제별 네트워크 검토

Runtime의 STANDARD@v2 정책 코드에는 다음 기본 동작이 있습니다.

- 기본 ingress·egress 차단.
- 필요한 클러스터 DNS와 동일 인스턴스 내부 통신 허용.
- public 포트만 외부 공개.
- 다른 인스턴스·팀의 private 통신 차단.

완성된 NetworkPolicy YAML이나 internal_connections를 bundle에 추가하지 않습니다.
현재는 외부 egress 예외나 컨테이너별 내부 통신 제한을 선언하는 출제자 계약이 없습니다.
env·secret_env 지원은 주소·인증값 전달이며 네트워크 정책 예외를 자동 허용하지 않습니다.

| 문제 | Compose에서 발견한 설정 | 확인할 사항 |
|---|---|---|
| web-afterimage | edge, appnet, vaultnet, cartridgenet, exportnet의 5개 네트워크; 4개 internal | Runtime 내부 전체 허용으로 vault·indexer·exporter에 의도하지 않은 직접 접근이 가능해지는지 |
| koth-dependency-hell | 기본 Compose app/database/judge, 운영 overlay app/internal/outbound/public | 어떤 Compose가 운영 기준인지, DB·judge 분리와 outbound 의도가 필수인지, 초기화 서비스 처리 |
| koth-jenga | docker-compose.layers.yml 단독 YAML 해석 실패 | 생성·병합용 파일인지와 실제 사용 방법을 출제자에게 확인; 이 점검만으로 CI 실패나 문제 오류로 판정하지 않음 |

[network-review.json](network-review.json)은 네트워크 이름과 서비스 연결 목록만 포함합니다.
환경변수 값·FLAG·소스 본문은 포함하지 않습니다.
정적 점검은 YAML/Compose에 보이는 설정만 찾으므로, 후보가 아닌 문제가 모두 안전하다는 뜻은 아닙니다.
실제 통신과 차단은 Runtime·출제자와 검증해야 합니다.

Runtime은 컨테이너별 Pod·Service 구조입니다. 다른 컨테이너에는 localhost가 아니라
실제 Runtime Service DNS로 연결해야 합니다. Compose 서비스명과 Runtime DNS가
자동으로 일치한다고 가정하지 않습니다.

### 출제자와 책임자에게 확인할 내용

1. 허용해야 할 컨테이너 간 통신과 반드시 차단해야 할 통신은 무엇인가요?
2. 지금 네트워크 분리가 풀이 경로와 보안 경계에 필수인가요, 단순 배포 편의인가요?
3. 외부 통신이 필수라면 대상·프로토콜·포트와 필요 시점을 알려주세요.
4. Runtime의 내부 전체 허용·외부 차단으로 실행해도 원래 출제 의도가 유지되나요?
5. 임시 저장 경로·초기화 작업·reset 시 보존/재생성할 설정도 확인해주세요.

비밀값 원문은 답변·info.yaml·bundle에 넣지 않습니다.
확인 결과로 기본 정책 적용 가능/별도 Runtime 정책 필요/계약 미지원 문제를 구분합니다.
제한된 정책 의도를 지원하기로 합의한 뒤에만 DevSecOps validator와 bundle 필드를 변경합니다.

## Backend ZIP/GCS 준비

저장 담당은 Backend이며 CI 직접 업로드는 계속 비활성입니다.

현재 Backend #80에는 다음 코드가 있습니다.

- 성공한 Actions artifact 수집과 실행 중 workflow 재시도.
- manifest·ZIP 무결성, 크기·개수 검증과 중복 처리.
- default_storage를 통한 저장과 DB metadata 등록.
- GCS_ENABLED, GCS_PROJECT_ID, GCS_BUCKET_NAME, GCS_OBJECT_PREFIX 설정.
- django-storages[google] 의존성.
- 동적 문제 active revision의 파일 선택, 정적 문제 최신 revision 선택.
- present:false인 선택 버전은 파일 없음으로 처리하며 이전 저장 객체는 보존.

Backend storage backend 내부 object key는 다음과 같습니다.

```text
participant-files/<challenge_slug>/<registry_revision>/<source_sha>/<checksum>.zip
```

GCS_OBJECT_PREFIX는 저장 backend의 location으로 이 경로 앞에 붙습니다.
실제 bucket·prefix·서버 인증·IAM이 적용됐다고 간주하지 않습니다.
CI용 WIF Service Account를 Backend 실행 계정으로 자동 재사용하지 않습니다.

### Backend·인프라 요청사항

- #26의 main 충돌 해결 후 최종 CI와 배포 SHA·migration 상태를 공유해주세요.
- #80에 최신 #26을 반영하고 최신 커밋의 CI 결과를 남겨주세요.
- Backend 실행 인증 신원과 bucket 접근, GCS_ENABLED 설정 상태를 확인해주세요.
- GCS_PROJECT_ID=msg-broker, GCS_BUCKET_NAME=2026msg_gcs 사용 여부와 prefix를 확정해주세요.
- 저장 후 ZIP checksum과 참가자 권한 검사·다운로드를 실제 GCS에서 확인해주세요.
- 등록·다운로드 실패와 실행 중 workflow는 재시도되고, 성공한 같은 artifact는 중복 저장되지 않는지 확인해주세요.

권장 검증 대상은 기존 실제 artifact가 있는 아래 네 종류입니다.
정확한 run·revision은 [기존 재현 입력](../2026-10-07-integration-readiness/input.json)에 있습니다.

| 종류 | 문제 |
|---|---|
| 정적·파일 있음 | misc-hidden-order |
| 정적·파일 없음 | forensic-is-this-job-legit |
| 동적·파일 있음 | pwn-random6 |
| 동적·파일 없음 | misc-cashout |

그다음 파일 변경 버전 활성화, 파일 없음 버전 활성화, 롤백,
권한 없는 다운로드 거절과 재수집 추가 다운로드 0을 확인합니다.
기존 로컬 소비 시험은 SQLite·임시 파일 저장소이며 실제 GCS 검증을 대체하지 않습니다.

## #79와 무관하게 진행할 순서

1. Backend #26 충돌 해결, #80 최신 CI와 GCS 실행 환경 준비.
2. 위 네트워크 후보에 대해 출제자·Runtime·책임자의 필수 통신 조건 확인.
3. DevSecOps #19, Backend #101, Scheduler #60, Runtime #46의 실행 설정 연동 리뷰.
4. Scheduler #59 healthcheck 배포와 활성화 조건, 정상/실패 probe 검증 계획 확인.
5. 승인된 Runtime 서버·토큰·digest가 준비되면 단일 WEB 기능 smoke 후 #17 증거 추가.

문제 저장소 #79는 최신 파이프라인을 main에 적용하는 작업이므로 별도 리뷰를 기다립니다.
#19 등 새 schema 2.1 계약은 다른 소비자 준비 없이 caller에 적용하지 않습니다.
KOTH 모델 연결, 실제 팀 격리, 운영 Secret 관리, PWN/gVisor와 전체 E2E는 별도 완료 조건입니다.
GHCR 보호 digest와 OCI 참조 확인 전 이미지 삭제는 하지 않습니다.

## 로컬 재현

```bash
python3 -B -m scripts.audit_execution_settings /absolute/path/to/problems \
  --source-sha <pinned_main_sha> \
  --output-dir /absolute/path/outside/problems/network-audit

python3 -B -m scripts.collect_user_files \
  --source-root /absolute/path/to/problems \
  --source-sha <pinned_main_sha> --revision 1 \
  --output-dir /absolute/path/outside/problems/user-files

python3 -B -m unittest discover -s tests
```

참가자 파일 명령은 시험용 패키징입니다. 생성물을 Actions나 Backend로 보내지 않습니다.
깨끗한 main checkout에서만 실행하고, 시험이 끝나면 ZIP·문제 checkout·캐시를 제거합니다.
공유할 검사 metadata와 checksum만 이 보고서에 보존합니다.

## 검증 결과

- 단위 테스트 192개 통과: 기존 189개와 문제 탐색 회귀 테스트 3개.
- 파일 패키징·GCS dry-run·점검 도구 관련 42개 테스트 통과.
- 37개 문제 참가자 파일 수집 두 번 성공, 전체 결과 바이트 동일.
- 37개 실행 설정 점검 완료, Jenga overlay 1개는 해석 미완으로 기록.
- git diff --check 통과.

첫 전체 시험은 샌드박스의 로컬 HTTP bind 제한으로 19개 오류가 났습니다.
허용된 로컬 테스트 환경에서 재실행해 192개 모두 통과했습니다. 실제 Runtime API 요청이 아닙니다.

