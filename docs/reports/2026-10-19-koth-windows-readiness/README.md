# KOTH 자원·배포 사양 점검

2026-10-19 KST 기준, 고정 main의 info.yaml 37개만 읽은 점검입니다.
문제 소스·Compose·실행 파일은 이번 점검에서 다운로드하거나 실행하지 않았습니다.
빌드·취약점 검사·GHCR 발행·DB 등록·배포 시험 결과가 아닙니다.

## 결과

- 총 37개: deployment 있음 24개, 없음 13개
- KOTH 6개: 모든 문제에서 KUBERNETES·AMD64 선언
- CPU 6000m: koth-grand-tour-duel, koth-swanopoly
- CPU 5500m: koth-dependency-hell
- runtime_type VM 선언: 0개
- Windows 여부: 판정하지 않음. 운영체제 필드 계약이 없고 참가자 파일은 미점검
- 원본 info.yaml·flag·환경변수 값·명령·접속 비밀값은 보고서에 포함하지 않음

VM 선언 0개는 Windows 문제나 제출형 문제가 없다는 뜻이 아닙니다.
deployment 없음도 참가자 파일 없음이나 실행 환경 불필요를 뜻하지 않습니다.

## 지원 파일

- [실행·자원 사양 표](execution-settings.md)
- [명세 점검 JSON](execution-settings.json)
- [담당별 확인 요청과 완료 기준](../../koth-windows-deployment.md)

실행 예시:

```bash
python3 scripts/audit_execution_settings.py /path/to/2026_MSG_CTF \
  --source-sha 25e7c6b636ba11b16c77e09274563fe92fbb9003 \
  --output-dir deployment-readiness \
  --deployment-only
```

INFO_ONLY는 info.yaml만 읽었다는 표시입니다. 환경변수·Compose 미발견을 실제 설정이
없다는 근거로 사용하면 안 됩니다. 기본 모드에서는 기존처럼 organizer 소스도 점검합니다.
별도 info.yaml 필드나 bundle·API 필드는 추가하지 않았습니다.

## 도구 검증

- 현재 main의 기존 192개와 추가 회귀 검사 10개, 전체 202개 통과
- 관련 점검 테스트 19개 통과
- 추가 항목: 합산 자원 보존, 입력 불변성, 잘못된 타입·비밀값 제외, 명세 전용 CLI,
  기존 소스 점검 유지, .exe·VM으로 Windows 추측 금지, 이전 보고서 표시 호환
- 로컬 HTTP 테스트는 임시 loopback 서버만 사용하며 운영 API·GCS·GHCR을 변경하지 않음
- PR #20은 별도 미병합 변경이므로 해당 PR의 테스트 수와 이 브랜치의 수를 혼동하지 않음

## 확인한 소스와 범위

- 문제 저장소 main: `25e7c6b636ba11b16c77e09274563fe92fbb9003`
- Backend main: `6078dfbcdf01cbb7ca21965e70de92c73cc42d35`
  - KothChallenge 모델에 challenge_slug·release 연결 필드 없음
  - [해당 모델](https://github.com/MSG-CTF/msg-backend/blob/6078dfbcdf01cbb7ca21965e70de92c73cc42d35/apps/koth/models.py)
- Runtime dev: `a3fcaec635728c86fdcfdd69492397053cfcdc9d`
  - 요청 target은 KUBERNETES이며 workload의 containers·healthcheck·exposed_ports 계약 확인
  - [현재 명세](https://github.com/MSG-CTF/secure-provisioner/blob/a3fcaec635728c86fdcfdd69492397053cfcdc9d/docs/api/secure-provisioner.openapi.yaml)
- [Broker PR #4](https://github.com/MSG-CTF/resource-broker/pull/4)
  - VM별 single-node K3s와 Node Agent 가용량 관측 방향 확인. 운영 배치 가능 확인과 구분
- [SLA 이슈 #6](https://github.com/MSG-CTF/sentinel/issues/6)
  - health worker와 Recovery policy 연결 범위 확인. KOTH 복구 완료 증거로 사용하지 않음

이 문서는 DevSecOps PR #20의 발행 대조·Grade smoke와 별개 작업입니다.
PR #19 및 다른 파트의 구현은 수정하지 않았습니다. GHCR 이미지 삭제도 하지 않았습니다.
