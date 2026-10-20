# 발행본 독립 Runtime 검증

## 목적과 책임

문제 발행과 실제 서버 시험을 서로 다른 GitHub Actions 실행으로 나눕니다.
이미지 검사·GHCR 발행·bundle 생성이 성공했다면 Backend Poller는 해당 성공 실행의
산출물을 수집할 수 있습니다. 이후 별도 Runtime 시험이 실패하더라도 원래 발행
실행의 성공 여부는 바뀌지 않습니다. Runtime 시험 자체의 실패는 그대로 실패로
기록하며 `continue-on-error`로 감추지 않습니다.

Backend의 `completed`·`success` 실행만 수집하는 기준은 유지합니다. 기존 실패 실행에
이미 bundle이 있더라도 수집 대상으로 억지로 인정하지 않습니다.

## 지원 범위

- 이미 완료·성공한 문제 저장소 `main` 발행 실행을 수동으로 선택합니다.
- Runtime 운영자가 정확한 GHCR digest를 승인한 일반 WEB 문제만 시험합니다.
- 첫 경로는 단일 컨테이너, `KUBERNETES`, `AMD64`, `WEB`으로 제한합니다.
- 기존 Runtime API 요청 변환기와 HTTPS·인증서 검사, 응답 검사, 삭제 확인을 재사용합니다.
- 새 이미지 빌드·push, Backend API 호출, release 활성화는 하지 않습니다.
- KOTH, PWN, 멀티 컨테이너, 전용 VM 및 Windows 배포를 자동 지원하지 않습니다.

Afterimage의 전용 VM 배포는 Runtime·Scheduler·Broker가 연결한 별도 경로입니다.
이 단일 WEB smoke의 성공을 해당 경로 또는 전체 격리 검증의 성공으로 기록하지 않습니다.

## 실행 계약

문제 저장소의 별도 수동 caller가 다음 reusable workflow를 호출합니다.

`.github/workflows/published-runtime-smoke.yml`

| 입력 | 설명 |
| --- | --- |
| `source_run_id` | 성공한 `challenge-validation.yml` 실행 ID |
| `challenge_slug` | 해당 실행에서 발행한 승인 WEB 문제 |
| `confirm_deploy` | 임시 생성·삭제를 명시적으로 승인, 기본 `false` |
| `devsecops_ref` | 검토한 DevSecOps 도구의 전체 commit SHA |
| `runtime_api_url` | 인증서가 유효한 Runtime HTTPS API 주소 |
| `runtime_ci_team_id` | 서버 측 제한 토큰에 허용된 CI 전용 팀 UUID |
| `runtime_target_id` | 서버 측 제한 토큰에 허용된 현재 target |

Secret은 `RUNTIME_API_TOKEN`만 사용합니다. GHCR pull 인증은 Runtime 노드가 관리하며
API 토큰과 혼용하지 않습니다. 토큰은 로그·산출물에 저장하지 않고, 임시 파일은
접근 권한을 제한해 사용 후 삭제합니다.

실제 시험 전 Runtime팀과 현재 배포 SHA, 정확한 이미지 digest·UID·쓰기 경로·포트
승인, 제한된 CI 토큰, target 사용 가능 여부 및 이전 잔여 리소스를 확인해야 합니다.
선택한 bundle의 자원 요구량도 해당 target에 승인된 범위인지 확인합니다.

## 출처 검증과 흐름

1. 수동 실행이며 caller의 실행 ref가 `refs/heads/main`인지 확인합니다.
2. 선택한 원본 실행이 같은 저장소의 공식 `challenge-validation.yml`, `main`,
   `push` 또는 `workflow_dispatch`, 완료·성공 상태인지 확인합니다.
3. artifact 전체 페이지를 조회하고 현재 run attempt의 문제별 publish bundle이
   정확히 하나인지 확인합니다. 만료되거나 16 MiB를 초과하는 압축본은 거절합니다.
4. 검증한 artifact ID만 다운로드합니다. 다른 문제·이전 시도의 산출물을 섞지 않습니다.
5. `artifact-v2.json`의 source SHA, main ref, slug, revision과 원본 실행의 출처가
   일치하는지 확인합니다. `PASS`, GHCR digest, 자원·포트·healthcheck 계약도 검사합니다.
6. CI 실행·재시도별 instance UUID를 만들어 기존 Runtime runner로 생성·조회·삭제합니다.
   생성 실패나 응답 오류가 나도 기존 runner의 삭제 확인 절차를 유지합니다.
7. 별도 실행에 출처 목록과 정제된 생성·삭제 결과를 보관합니다.

caller는 같은 CI target을 쓰는 smoke를 직렬 실행하고 `cancel-in-progress: false`로
설정해야 합니다. 자동 취소로 삭제 절차를 끊지 않도록 합니다. 수동 강제 취소나
러너 종료까지 정리를 보장하는 것은 아니므로 이 경우 Runtime 리소스를 별도 확인합니다.

## 결과 해석

발행 run ID, artifact ID·이름, SHA, slug, revision을 `selection.json`에 남기고
정제된 Runtime 결과와 함께 14일 보관합니다. 원본 bundle과 token 파일은 재업로드하지 않습니다.

성공은 기존 runner가 확인한 Runtime 생성 성공, endpoint 응답 계약과 삭제 완료를 뜻합니다.
실제 공개 URL의 HTTP 응답, 노드의 cold pull 시간·실행 digest, 다른 인스턴스와의 격리,
reset, 정상·실패 probe 및 운영 부하는 별도 연동 시험으로 확인해야 합니다.

이 workflow의 단위 테스트 통과만으로 실제 배포 성공을 선언하지 않습니다.
중앙 reusable workflow를 병합한 뒤 caller의 workflow SHA와 `devsecops_ref`를 같은
병합 SHA로 갱신하고, 승인한 단일 WEB 발행본으로 최초 실제 실행을 진행합니다.
