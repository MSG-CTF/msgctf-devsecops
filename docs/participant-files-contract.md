# 참가자 제공 파일 전달 계약

## 목적

문제의 `prob/for_user/`를 DevSecOps 공급망에서 안전하게 패키징하고 Backend
poller가 수집할 수 있는 GitHub Actions artifact로 전달합니다. Docker image가 아니므로
GHCR에 저장하지 않으며, ZIP 자체를 Backend DB에 넣는 방식도 사용하지 않습니다.

## DevSecOps 산출물

승인된 `main` 발행에서는 문제마다 다음 Actions artifact를 생성합니다.

```text
<challenge_slug>-<artifact_scope>-user-files-bundle/
├ user-files.json
└ user-files.zip       # 제공 파일이 있을 때만 존재
```

`prob/for_user/`가 없거나 비어 있으면 `user-files.json`만 생성하며
`user_files.present`는 `false`입니다.

```json
{
  "schema_version": "1.0",
  "challenge_slug": "pwn-random6",
  "source_ref": "refs/heads/main",
  "source_sha": "0123456789abcdef0123456789abcdef01234567",
  "registry_revision": 42,
  "user_files": {
    "present": true,
    "archive": "user-files.zip",
    "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    "size_bytes": 12345,
    "file_count": 3,
    "uncompressed_size_bytes": 25000
  }
}
```

`challenge_slug`, `source_sha`, `registry_revision`으로 문제 릴리스와 참가자 파일을
연결합니다. `sha256`은 Backend가 내려받은 ZIP의 무결성을 다시 확인하는 값입니다.

## 검증 기준

- 기본 최대 파일 수: 1,000개
- 기본 최대 압축 전 합계: 100 MiB
- 심볼릭 링크 금지
- 일반 파일이 아닌 FIFO, socket, device 파일 금지
- ZIP 내부 경로는 `prob/for_user/` 기준 상대 경로만 허용
- 파일 순서와 ZIP metadata를 고정해 같은 입력은 같은 ZIP을 생성

문제 파일은 의도적으로 실행 파일이나 취약한 binary를 포함할 수 있으므로 image용
Trivy 취약점 기준을 그대로 적용하지 않습니다. 저장 용량, 허용 확장자, 악성코드 검사,
참가자 공개 승인 정책은 Backend·운영·보안 담당과 별도 확정해야 합니다.

## 역할 분담

- DevSecOps: 파일 구조 검사, ZIP 생성, SHA-256 계산, Actions artifact 발행
- Backend poller: Actions artifact 수집, manifest 검증, 문제 릴리스 연결
- Object Storage 담당: ZIP 영구 보관과 접근 정책 관리
- Backend API: 참가자 권한 확인 후 다운로드 URL 제공
- Frontend: Backend API가 제공한 다운로드 기능 표시

Actions artifact의 90일 보관은 전달과 통합 테스트를 위한 임시 보관입니다. 대회
운영에서는 Backend poller가 ZIP을 GCS/S3 등의 Object Storage로 복사하고 DB에는
object key, checksum, 크기와 릴리스 연결 정보만 저장하는 방식을 권장합니다.
