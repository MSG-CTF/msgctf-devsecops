# GCP Runtime 연결과 배포 검증 준비

## 이번 구현 범위

- 기존 smoke HTTP client에 인증서·hostname 검증을 유지하는 HTTPS 전송 추가.
- `https://<host>/internal/v1`를 전달해도 API 경로가 중복되지 않도록 origin 정규화.
- URL 안의 사용자 정보·query·fragment·임의 경로·외부 HTTP 거절.
- Runtime 응답 redirect를 따라가지 않음. Bearer token이 다른 서버로 전달되는 것을 방지.
- AWS SSM 노드 내부에서 사용하는 loopback HTTP 경로 유지.
- Actions 수동 실행에서 토큰 없는 TLS·비인증 차단 사전 점검 추가.

실제 생성·삭제 job을 AWS에서 GCP로 자동 전환한 것은 아닙니다.
기존 `challenge-supply-chain.yml`의 SSM job은 그대로입니다. token·승인 이미지·
배포 정책 확인 후 별도 검증을 진행합니다. TLS 검증을 끄는 옵션은 제공하지 않습니다.

## Runtime팀 전달 내용: 2026년 10월 5일

| 항목 | 전달받은 값·상태 |
|---|---|
| GCP VM | `provisioner-test-1` |
| 배포 브랜치 | `fix/psa-restricted-namespaces` |
| 배포 SHA | `1e3f8ac901eaf7caf082042fbfe7e8238d2d7176` |
| API | `https://34.67.93.98:443/internal/v1` |
| broker-test2 target | `b794d71b-51ef-45fd-87c1-9721e2999e79` |
| broker-test-3 target | `b56f00f9-bb83-45ef-a6bc-d905c6a1126a` |
| service token | VM에서 인증 확인. CI 전용 발급·Secret 등록은 미확인 |
| GHCR pull | 두 노드 설정 완료, 10월 2일 Grade Tampering digest pull 확인했다는 전달 |
| 정책 | STANDARD@v2, 기본 격리, egress NONE, exposed_ports |
| 이미지별 정책 | 정확한 digest에 UID·쓰기 경로·공개 포트를 연결하는 서버 정책 |
| FLAG | Kubernetes Secret 주입 시험. 실제 운영 FLAG는 미입력 |
| 미지원 | 임의 환경변수, 문제별 healthcheck/readiness, 실행 권한 완화 |
| 제한 | 노드 PID 제한 미적용, gVisor 없음. 현재 PWN 시험 금지 |

배포 SHA와 브랜치를 `MSG-CTF/secure-provisioner` GitHub API에서 조회했으나
확인되지 않았습니다. 배포 안 됐다는 단정이 아니라 원격에 push되지 않았거나
다른 소스일 수 있어, 실제 API 명세와 해당 소스의 원격 ref 확인이 필요합니다.
현재 공개된 dev 명세가 위 배포 SHA와 동일하다고 가정하지 않습니다.

Runtime팀이 언급한 API 명세·WEB 이미지별 정책·배포 기록의 실제 문서 링크 또는
내보낸 파일을 받아야 합니다. 승인된 WEB 이미지 3개의 정확한 digest, 컨테이너
이름, UID, writable path, 공개 포트가 확인되기 전에는 임의 이미지로 생성하지 않습니다.

## 토큰 없는 사전 점검

```bash
python3 -m scripts.runtime_connection_probe \
  --api-url https://34.67.93.98:443/internal/v1 \
  --output dist/gcp-runtime-connection.json
```

인증이 필요한 임의 instance의 상태 GET을 token 없이 요청하고 HTTP 401을
기대합니다. TLS가 실패하거나 redirect, 200, 403 등 예상 외 응답이면 실패합니다.
응답 본문은 보고서에 저장하지 않으며 create/reset/delete는 요청하지 않습니다.

Actions 자체 검증의 수동 입력 `check_gcp_runtime_connection=true`를 사용하면
GitHub-hosted runner에서 같은 점검을 수행합니다. 기본값은 false이며 PR CI가
자동으로 테스트 서버에 요청을 보내지 않습니다. 이 job은 secret을 사용하지 않습니다.

```bash
gh workflow run pipeline-self-test.yml \
  --repo MSG-CTF/msgctf-devsecops \
  --ref fix/gcp-runtime-https-preflight \
  -f check_gcp_runtime_connection=true
```

401은 주소·TLS·비인증 접근 차단의 증거이지 Runtime 배포 SHA·서비스 token의
유효성·workload 실행 성공·운영 격리 완료의 증거가 아닙니다.

2026년 10월 5일 로컬 curl과 Python 점검에서 인증서를 검증한 HTTPS 연결과
HTTP 401을 확인했습니다. Python의 기본 CA 경로가 비어 있어 첫 점검은 실패했고,
macOS에 이미 설치된 `/etc/ssl/cert.pem`을 명시한 재실행은 성공했습니다.
검증을 끄거나 서버 인증서를 임의로 신뢰하지 않았습니다.

```bash
env SSL_CERT_FILE=/etc/ssl/cert.pem python3 -m scripts.runtime_connection_probe \
  --api-url https://34.67.93.98:443/internal/v1 \
  --output dist/gcp-runtime-connection.json
```

이는 해당 Mac의 CA 설정에 대한 재실행 예시입니다. Linux runner에서는 기본
신뢰 저장소로 검사합니다. 결과는
`docs/reports/2026-10-05-gcp-runtime-connection/local-connection.json`에 있습니다.

## 실제 생성 시험 전 필요한 항목

1. Runtime API 명세와 배포 SHA의 원격 위치 확인.
2. 승인된 WEB 이미지 3개의 digest별 실행 정책.
3. CI 전용 `RUNTIME_API_TOKEN`을 실제 시험 caller 저장소의 Actions Secret에 등록.
4. Runtime token 권한 범위·만료·회전·동시 시험·인증 요구사항 확인.
5. target별 공개 endpoint와 방화벽/접속 경로 확인.
6. 승인 이미지가 있는 실제 publish bundle과 테스트 team/instance 식별자.

token 원문은 카톡, PR, artifact에 넣지 않습니다. secret을 명령줄 argument로
전달하지 않고 runner에서 권한을 제한한 임시 token 파일로 저장해 기존 runner에
전달한 뒤 cleanup해야 합니다. token은 GHCR pull credential과 다른 값입니다.

Backend Poller에 직접 등록 API를 호출하는 설계와 연결하지 않습니다. 실제 배포
시험도 Runtime팀 API를 사용하며 Kubernetes 리소스를 CI가 직접 생성하지 않습니다.

## 후속 검증 순서

1. 토큰 없는 Actions HTTPS 점검.
2. 인증과 승인된 WEB 1개 생성·HTTP 응답·삭제. 실패 cleanup 확인.
3. 두 target의 승인 WEB 3개와 새 digest cold pull, 실제 실행 digest 확인.
4. mixed ports, 내부 통신, 팀·인스턴스 간 격리, reset.
5. Backend/Scheduler/Broker를 포함하는 실제 release E2E.
6. PID·gVisor 등 Runtime 준비 후 별도 PWN 검증.

현재 임의 환경변수와 문제 healthcheck는 지원하지 않는다고 전달받았습니다.
FLAG Secret 시험이 있다는 이유로 모든 문제의 실행 설정이 해결됐다고 말하지
않습니다. 각 필드의 공통 계약과 실제 지원 여부를 확인해야 합니다.
