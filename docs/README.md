# 문서

문제 저장소와 DevSecOps 공급망을 연결할 때 필요한 예제와 운영 문서를
관리합니다.

## 파일

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

실제 GitHub Actions publish bundle을 백엔드 Challenge Registry 기능 브랜치에
등록한 통합 검증 증거와 운영 연결 전 남은 조건을 기록합니다.
