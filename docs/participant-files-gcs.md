# 참가자 파일 GCS 저장

## 현재 범위

참가자 파일은 Docker image가 아니므로 GHCR에 넣지 않습니다. 기존 CI가
`prob/for_user/`를 검사·ZIP 패키징하고 Actions artifact로 전달하는 기능은 유지합니다.
이번 변경은 승인된 main 발행에서 같은 ZIP과 manifest를 GCS에도 저장하는
선택 기능입니다. 기본값은 비활성이며 실제 GCS 저장과 Backend 다운로드 연결은
아직 검증하지 않았습니다. 아래 object key와 영수증은 리뷰용 제안 계약입니다.

## 사용할 인프라

| 항목 | 값 |
|---|---|
| Project | msg-broker |
| Bucket | 2026msg_gcs |
| Workload Identity Provider | projects/309055091666/locations/global/workloadIdentityPools/github-actions/providers/msg-github-actions |
| CI Service Account | gcs-file-upload-devops@msg-broker.iam.gserviceaccount.com |

이 설정은 GitHub Actions에 들어갑니다. 출제자의 info.yaml에는 Google 인증이나
bucket 주소를 추가하지 않습니다. Service Account JSON key도 사용하지 않습니다.
`google-github-actions/auth@v3`의 WIF 방식으로 짧은 수명의 인증을 받습니다.

## 저장 경로 제안

```text
gs://2026msg_gcs/participant-files/<challenge_slug>/revisions/<registry_revision>/<source_sha>/
├── user-files.zip    # present:true인 경우만
└── user-files.json   # ZIP 저장 및 검증이 끝난 후 마지막에 기록
```

문제·revision·커밋을 경로에 넣고 기존 객체를 덮어쓰지 않습니다. 재실행 시 같은
경로에 있는 객체의 크기, SHA-256 metadata, 서버가 계산한 MD5와 generation을
검사해 동일한 객체만 재사용합니다. 다른 내용이면 실패합니다. 새 revision도 기존
파일을 삭제하거나 active release를 자동 변경하지 않습니다.

파일이 없거나 비어 있으면 `present:false` manifest만 저장합니다. 기존 객체를
삭제하지 않으며 화면에서 파일을 숨기는 처리는 Backend의 기존 정책을 따릅니다.
ZIP 저장 실패 또는 metadata 충돌 때는 완료 영수증을 발행하지 않습니다. ZIP만
저장된 부분 실패는 재실행으로 복구하며 삭제 권한이나 덮어쓰기를 사용하지 않습니다.
같은 경로의 JSON 표현이 바뀌면 충돌로 처리하므로 기존 bundle bytes를 재사용합니다.

## 승인된 workflow에서만 업로드

reusable workflow 입력 `enable_user_files_gcs_upload` 기본값은 false입니다.
다음 조건을 모두 만족해야 GCS job이 실행됩니다.

- 문제 저장소가 `MSG-CTF/2026_MSG_CTF`이고 실행 ref가 `refs/heads/main`
- main push 또는 main 수동 발행이며 `publish_images:true`
- info.yaml·Gitleaks 검증과 참가자 파일 패키징 성공
- 동적 문제는 Docker build·image secret·취약점 gate까지 성공
- caller가 id-token:write를 허용하고 `user-files-gcs` Environment에서 승인

저장소 관리자가 **Environment의 required reviewers와 main branch 제한을 먼저
설정**해야 합니다. 이름만 있는 Environment는 승인을 강제하지 않습니다.
WIF의 신뢰 조건도 문제 저장소·main·승인된 workflow로 제한해야 하며 실제
provider 설정은 인프라 담당 확인이 필요합니다. CI Service Account는 이 bucket의
participant-files prefix에 create/get만 허용하는 최소 권한으로 운영하고
delete/overwrite/public ACL 권한은 부여하지 않는 방향으로 검토합니다.

인증 생성 파일은 dist/user-files나 Actions 업로드 대상에 넣지 않습니다.
GCS 객체에는 public ACL과 Signed URL을 생성하지 않으며 `private, no-store`를
설정합니다. 실제 접근 차단은 별도로 bucket IAM과 Public Access Prevention으로
설정해야 합니다. 다운로드 인증·권한·Signed URL은 Backend 담당입니다.

## Backend 전달

기존 `-user-files-bundle`의 user-files.json/zip은 변경하지 않습니다. 신규
`<기존 bundle 이름>-gcs-receipt` artifact에 `gcs-receipt.json`을 발행합니다.
여기에는 challenge_slug, registry_revision, source_ref, source_sha, user_files와
GCS bucket·object_key·generation·checksum·크기가 포함됩니다. 영수증에
서명 URL, 액세스 토큰, Service Account key는 넣지 않습니다.

Backend가 이 영수증을 이미 지원한다고 가정하지 않습니다. 기존 Poller의
ZIP 직접 수집·Object Storage 복사 방식과 새 CI 저장 방식 중 **하나를 저장
담당으로 확정**해야 하며, 둘 다 같은 파일을 다시 업로드하는 구조로 운영하지 않습니다.
Backend에서는 영수증 수집·검증, Challenge/release 연결, DB metadata 등록,
권한 검사와 다운로드 API를 추가 연결해야 합니다. 기존 Actions 수집 경로는
해당 계약 승인과 적용 전까지 유지됩니다. 실제 GCS 업로드를 먼저 활성화하지 않습니다.

## 리뷰 반영: 저장 담당 결정과 활성화 조건

현재 운영 연결 기준은 **Backend가 기존 Actions ZIP을 받아 저장하는 경로**입니다.
Backend가 새 GCS 영수증을 수집하거나 object key로 파일을 등록하는 기능은
아직 연결되지 않았습니다. PR을 병합해도 이 경로를 자동 전환하지 않으며,
`enable_user_files_gcs_upload:false`를 유지합니다.

책임자·Backend·DevSecOps가 다음 중 하나를 선택해야 합니다.

| 선택 | 저장 담당 | DevSecOps 처리 | Backend 처리 |
|---|---|---|---|
| 기존 방식 유지 | Backend | Actions ZIP·manifest 발행, GCS 옵션 비활성 | ZIP 수집·검증 후 저장소에 저장 |
| CI 저장 방식으로 전환 | DevSecOps CI | 승인 후 GCS 저장 및 영수증 발행 | 영수증 수집·검증, DB 연결·다운로드, 기존 ZIP 재업로드 중지 |

두 경로를 동시에 저장 담당으로 켜지 않습니다. 후자를 선택한 경우에도 아래
확인을 모두 마친 다음 책임자 승인으로 옵션을 활성화합니다.

1. object key·영수증 형식과 저장 담당 전환 계약 확정.
2. Backend 영수증 수집, 문제·revision 연결, DB 등록 및 다운로드 구현 확인.
3. WIF 신뢰 조건, Service Account 최소 권한, bucket IAM·공개 차단 확인.
4. Environment required reviewers와 main 제한 설정 확인.
5. 승인된 테스트 환경에서 실제 GCS 업로드와 참가자 다운로드를 정적·동적,
   파일 있음·없음 4가지로 검증하고 실행·등록 결과를 기록.

업로드 코드의 단위 테스트 통과는 실제 WIF 인증, GCS 저장, Backend 다운로드
성공을 의미하지 않습니다. 현재 리뷰 보완에서도 인증·업로드와 옵션 활성화는
수행하지 않았습니다.

## 전체 문제 수집 계획

```bash
python3 -m scripts.collect_user_files \
  --source-root /absolute/path/to/2026_MSG_CTF \
  --source-sha <현재_origin_main_SHA> \
  --revision <검토용_revision> \
  --output-dir /absolute/path/outside/problem-repository
```

깨끗한 origin/main checkout의 각 info.yaml을 검증하고, 정적·동적 문제를 모두
패키징해 문제별 GCS 저장 계획과 전체 collection-plan.json을 생성합니다.
이 명령은 인증·업로드·Docker build·Trivy·Backend 등록을 실행하지 않습니다.
검토용 revision을 실제 release revision으로 간주하면 안 됩니다. 실제 발행은
caller의 workflow revision과 main 커밋으로 진행해야 합니다. Windows/macOS에서
대소문자 충돌로 checkout이 dirty이면 임의 무시하지 않고 Linux checkout 또는
문제와 무관한 루트 문서를 제외한 clean sparse checkout으로 검사합니다.

```bash
python3 -m scripts.upload_user_files_gcs \
  --bundle-dir /absolute/path/to/checked-user-files-bundle \
  --output /absolute/path/to/gcs-plan.json
```

기본은 저장 계획만 생성합니다. `--apply`는 승인된 WIF job 또는 관리자가
허가한 ADC 환경에서만 사용합니다. CLI 자체가 GitHub Environment 승인을
검사하는 것은 아니므로 인증 권한을 가진 사람의 별도 승인 없이 실행하지 않습니다.

## 남은 확인

- 책임자: object key, 영수증 형식, CI 저장 담당 전환 승인
- 인프라: WIF 신뢰 조건, bucket IAM, 공개 차단과 보존 정책
- Backend: 영수증 수집·DB 연결·다운로드, 중복 저장 담당 제거
- 실제 파일 있음/없음과 정적/동적 4종 업로드·다운로드 테스트
- 저장 도중 실패, 재시도, 같은 revision 충돌, present:false 처리 검증

참고: [GCS generation precondition](https://cloud.google.com/storage/docs/request-preconditions),
[WIF 인증 action](https://github.com/google-github-actions/auth).
