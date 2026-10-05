# 문서

문제 저장소와 DevSecOps 공급망을 연결할 때 필요한 예제와 운영 문서를
관리합니다.

### `ghcr-cleanup.md`

GHCR 이미지 버전의 보존 정책, 삭제 없는 후보 조회 방법, 실제 조회 보고서와
삭제 전에 받아야 할 보호 digest 목록을 설명합니다.

## 파일

### `challenge-execution-settings.md`

현재 info.yaml과 publish bundle의 지원 필드, 문제별 실행 설정 점검표,
환경변수·healthcheck·스토리지·네트워크 계약의 미확정 부분과 담당별 요청을 정리합니다.

### `challenge-caller-example.yml`

문제 저장소가 `challenge-supply-chain.yml` reusable workflow를 호출하는
GitHub Actions 예제입니다.

### `devsecops-runbook.md`

문제 검증 실패, Docker build 실패, Gitleaks·Trivy 차단, GHCR 발행 실패에
대응하기 위한 운영 절차입니다. Challenge Registry, Runtime, Broker,
Monitoring 팀과 맞춰야 할 계약도 포함합니다.

현재 GitHub 기준의 문제 저장소, Broker, Scheduler, Runtime, Monitoring 연동
상태와 미확정 항목도 기록합니다.

### `challenge-registry-integration.md`

Backend poller의 Actions artifact 수집 기반 release 등록 운영 계약과, 과거 로컬
Registry 등록의 호환성 증거를 기록합니다.

### `participant-files-contract.md`

`prob/for_user/` 참가자 제공 파일의 ZIP 생성, 무결성 manifest, Actions artifact
전달 방식과 Backend·Object Storage 역할 경계를 정의합니다.
