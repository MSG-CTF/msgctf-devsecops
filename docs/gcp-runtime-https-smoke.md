# GCP Runtime HTTPS smoke

## 목적

문제 이미지 발행 후 GitHub 호스팅 runner가 GCP Secure Provisioner의 공개 HTTPS API로 승인된 WEB 이미지를 생성·조회·삭제한다. Runtime이 K3s 리소스와 보안 정책의 소유자이며 Actions에는 K3s kubeconfig나 GHCR pull 토큰을 주지 않는다.

## 호출 계약

재사용 공급망 workflow에 `enable_runtime_https_smoke`(기본 `false`), `runtime_api_url`, `runtime_ci_team_id`, 기존 `runtime_target_id`를 전달한다. 호출 저장소는 `RUNTIME_API_TOKEN`을 Actions Secret으로 제공한다. 이 토큰은 Provisioner가 전용 팀·Target·승인된 digest 및 자원 상한으로 제한하며 기존 전체 권한 서비스 토큰과 다르다. URL·팀·Target은 Actions 변수로 둔다.

발행 bundle의 `artifact-v2.json`을 기존 `runtime_api_smoke_runner.py`에 입력한다. runner는 기본 인증서 검증을 켠 HTTPS로 create → Operation 조회 → delete → Operation 조회를 수행한다. 토큰은 runner 임시 파일에만 쓰고 작업 종료 시 지운다. 결과에는 토큰이나 FLAG 원문을 넣지 않는다. 발행된 digest가 아직 Provisioner 정책에 없으면 생성이 실패하며, 이미지 정책 검토·배포 후 재실행한다. 자동 승인이나 임의 digest 허용은 하지 않는다.

## 단계적 적용과 복구

기존 AWS SSM smoke job 및 `enable_k3s_smoke_deploy` 입력은 그대로 둔다. 새 HTTPS job은 별도 플래그로만 실행한다. 먼저 승인된 Grade digest를 이용한 수동 GitHub runner 시험으로 공개 TLS·토큰·생성·삭제를 검증한다. 그다음 호출 저장소가 새 재사용 workflow 커밋을 고정하고 `ENABLE_RUNTIME_HTTPS_SMOKE=true`를 설정한다. 오류가 발생하면 이 변수만 `false`로 바꿔 자동 실행을 중단한다. 기존 공급망 검증·이미지 발행·AWS job은 영향을 받지 않는다.

## 검증 범위

단위 검증은 workflow 입력·secret·조건부 실행, 최소 runner 권한, HTTPS 호출, 토큰 파일 정리, AWS job 불변을 확인한다. 실제 runner 시험은 승인 digest의 create `SUCCEEDED`, HTTP 준비와 공개 응답, delete `SUCCEEDED`, K3s Namespace 제거를 확인한다. 새 digest 자동 승인, Scheduler reset, PWN/gVisor, 팀 인증 게이트웨이는 이 변경에 포함하지 않는다.

2026-10-06 사전 실측에서는 기존 `runtime_api_smoke_runner.py`에 승인된 Grade Tampering digest `9ffbf476…0956d`의 artifact를 전달하고 공개 `https://34.67.93.98:443`에서 CI 토큰으로 실행했다. 생성·삭제 모두 `SUCCEEDED`였으며 K3s Namespace 조회 결과가 비어 있었다. 이는 Provisioner VM에서 공개 HTTPS 경로를 사용한 시험이다. GitHub 호스팅 runner 출발지 시험은 별도로 기록해야 한다.
