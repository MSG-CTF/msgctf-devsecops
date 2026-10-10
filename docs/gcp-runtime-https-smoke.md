# GCP Runtime HTTPS smoke

## 목적

문제 이미지 발행 후 GitHub 호스팅 runner가 GCP Secure Provisioner의 공개 HTTPS API로 승인된 WEB 이미지를 생성·조회·삭제한다. Runtime이 K3s 리소스와 보안 정책의 소유자이며 Actions에는 K3s kubeconfig나 GHCR pull 토큰을 주지 않는다.

## 호출 계약

재사용 공급망 workflow에 `enable_runtime_https_smoke`(기본 `false`), `runtime_api_url`, `runtime_ci_team_id`, 기존 `runtime_target_id`를 전달한다. 호출 저장소는 `RUNTIME_API_TOKEN`을 Actions Secret으로 제공한다. 이 토큰은 Provisioner가 전용 팀·Target·승인된 digest 및 자원 상한으로 제한하며 기존 전체 권한 서비스 토큰과 다르다. URL·팀·Target은 Actions 변수로 둔다.

발행 bundle의 `artifact-v2.json`을 기존 `runtime_api_smoke_runner.py`에 입력한다. runner는 기본 인증서 검증을 켠 HTTPS로 create → Operation 조회 → delete → Operation 조회를 수행한다. 토큰은 runner 임시 파일에만 쓰고 작업 종료 시 지운다. 결과에는 토큰이나 FLAG 원문을 넣지 않는다. 발행된 digest가 아직 Provisioner 정책에 없으면 생성이 실패하며, 이미지 정책 검토·배포 후 재실행한다. 자동 승인이나 임의 digest 허용은 하지 않는다.

bundle에 `workload.healthcheck`가 있으면 `container`, `port`, `path`를 검증한 뒤
같은 위치의 Runtime 요청 필드로 전달한다. 생략/null이면 요청에서 생략한다.
컨테이너·포트 일치, 공백·제어 문자 금지, UTF-16 길이 1024 제한은 CI와 같은
검증 함수를 사용한다. 비공개 검사 포트를 exposed_ports에 추가하지 않는다.
기존 expose와 internal_connections 미전송 원칙도 유지한다.

## 단계적 적용과 복구

기존 AWS SSM smoke job 및 `enable_k3s_smoke_deploy` 입력은 그대로 둔다. 새 HTTPS job은 별도 플래그로만 실행한다. 먼저 승인된 Grade digest를 이용한 수동 GitHub runner 시험으로 공개 TLS·토큰·생성·삭제 Operation을 검증한다. 그다음 호출 저장소가 새 재사용 workflow 커밋을 고정하고, 발행할 digest의 정책 승인을 확인한 뒤 `ENABLE_RUNTIME_HTTPS_SMOKE=true`를 설정한다. 오류가 발생하면 이 변수만 `false`로 바꿔 자동 실행을 중단한다.

기존 검사·발행과 AWS job의 활성화 조건을 유지한다. 공유 healthcheck 검증 모듈은
AWS staging에서도 runner와 함께 전달한다. HTTPS smoke가 실패하면 전체 workflow도
실패하므로, 성공한 workflow만 수집하는 Backend Poller는 해당 실행의 bundle을
등록할 수 없다. 정책 미승인 digest로 자동 job을 먼저 활성화하지 않는다.

## 검증 범위

단위 검증은 workflow 입력·secret·조건부 실행, 최소 runner 권한, HTTPS 호출, 토큰 파일 정리, AWS job 불변을 확인한다. 단위 테스트 통과는 실제 문제 접속이나 운영 격리 검증을 의미하지 않는다.

현재 runner와 자동 job이 확인하는 항목은 다음과 같다.

- Runtime API의 HTTPS 인증서 검증과 인증된 요청.
- bundle의 HTTP healthcheck 검증·전달. 실제 probe 수행과 준비 상태 판정은 Runtime 소유다.
- 생성 Operation의 `SUCCEEDED`와 결과의 workload 식별자 확인.
- 반환된 endpoint의 형식과 공개 포트 계약 확인. endpoint 주소로 실제 접속하는 검사는 아니다.
- 삭제 Operation의 `SUCCEEDED` 확인. K3s 리소스를 직접 조회한 삭제 확인은 아니다.

공개 문제 URL의 실제 HTTP 응답, 전달된 healthcheck의 정상·실패 동작, 실행 이미지 digest 대조, K3s Namespace·Pod·Service 잔존 여부, 팀·인스턴스 격리는 별도 검증이 필요하다. 새 digest 자동 승인, Scheduler reset, PWN/gVisor, 팀 인증 게이트웨이도 이 변경에 포함하지 않는다. 이번 보완은 실제 서버를 호출하거나 HTTPS smoke를 활성화하지 않는다.

## 확인된 실행 기록

2026-10-06 사전 실측은 PR 작성자의 기록이다. 기존 `runtime_api_smoke_runner.py`에 승인된 Grade Tampering digest `9ffbf476…0956d`의 시험용 artifact를 전달하고 Provisioner VM에서 공개 `https://34.67.93.98:443` 경로를 호출해 생성·삭제 Operation 성공을 확인했다. 작성자가 별도로 수행한 K3s Namespace 조회에서는 제거를 확인했다고 보고했다. 이 Namespace 확인은 runner의 자동 검사 항목이 아니다.

[GitHub 호스팅 runner 수동 시험](https://github.com/MSG-CTF/2026_MSG_CTF/actions/runs/37443357952)은 성공했다. 승인된 기존 Grade digest와 workflow에서 생성한 시험용 `artifact-v2.json`을 사용했으며, 생성·삭제 Operation 성공을 확인했다. 시험용 bundle의 `scan_result: PASS`와 revision은 테스트 입력이며, 해당 실행이 이미지를 다시 빌드·검사·발행하거나 실제 릴리스를 Backend에 등록한 것은 아니다. 이 Actions에는 문제 URL의 HTTP 접속 검사나 K3s Namespace 직접 조회 단계가 없다.

## 남은 연동 검증

- 새 자동 `k3s-smoke-https` job에 실제 발행 bundle을 입력하고 승인된 최신 digest로 실행한다.
- Runtime 담당자와 공개 URL의 응답, 실행 digest, K3s 리소스 정리를 별도 확인해 실행 기록을 남긴다.
- Backend Poller 수집·릴리스 등록과 Scheduler를 통한 인스턴스 생성은 별도 경로로 검증한다. 이 smoke는 Backend와 Scheduler를 거치지 않는다.
