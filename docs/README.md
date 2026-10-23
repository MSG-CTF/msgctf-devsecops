# 문서

- [노드 이미지 사전 다운로드 연동](node-image-prefetch.md): 문제별·전체 이미지 목록과 변경분 취합, 읽기 전용 Actions와 수집·다운로드·적용의 책임 경계
- [발행본 독립 Runtime 검증](published-runtime-smoke.md): 성공한 main 발행본의 출처 검증과 발행 실행에 영향을 주지 않는 단일 WEB 생성·삭제 시험
- [2026-10-21 Backend 개발 서버 전달 자료](reports/2026-10-21-backend-handoff/README.md): 최신 37개 발행 대조와 문제별 revision·run·artifact, 배포 성공 기록 및 서버 확인 요청
- [2026-10-20 최신 발행 대조](reports/2026-10-20-release-readiness/README.md): 37개 문제 폴더와 성공 산출물 일치, 실패한 Runtime 시험과 수집 계약 구분
- [2026-10-19 병합 후 연동 점검](reports/2026-10-19-release-readiness/README.md): 실제 main 산출물 대조, Notebook revision 529·정책 확인과 남은 배포 검증
- [KOTH·Windows 배포 연동](koth-windows-deployment.md): 공용 KOTH 배치·복구와 Windows 제출 실행의 역할 경계, 미확정 계약과 확인 순서
- [2026-10-19 KOTH 자원·배포 사양 점검](reports/2026-10-19-koth-windows-readiness/README.md): 고정 main의 37개 info.yaml 선언값과 6개 KOTH 자원 비교
- [2026-10-11 Runtime 후속 조건](reports/2026-10-10-independent-preparation/runtime-followup-2026-10-11.md): 새 Grade digest 미승인·이전 리소스 미확인과 Afterimage/KOTH 네트워크 처리 분리
- [2026-10-10 독립 연동 준비](reports/2026-10-10-independent-preparation/README.md): 최신 37개 참가자 파일 검사, 문제별 네트워크 검토 후보와 Backend GCS 준비
- [참가자 파일 GCS 저장](participant-files-gcs.md): Backend 저장 담당과 비활성 CI 업로드 경로
- [2026-10-07 연동 준비 결과](reports/2026-10-07-integration-readiness/README.md): 실제 산출물의 로컬 Backend 소비 시험, 발행 목록과 남은 요청사항

문제 저장소와 DevSecOps 공급망을 연결할 때 필요한 예제와 운영 문서를
관리합니다.

### `gcp-runtime-smoke.md`

GCP Runtime HTTPS 연결 사전 점검, 안전한 인증 전송, 배포팀 답변과 실제 생성
시험 전에 필요한 token·이미지 정책·명세를 설명합니다.

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
