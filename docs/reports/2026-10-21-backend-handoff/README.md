# Backend 개발 서버 검증 전달 자료

## 발행 대조 기준

- 확인 시각: 2026-10-21 12:27 KST
- 문제 main: `84742c511bb126a5e94d9d21c85ddf9b0611b923`
- 전체 37개: 동적 24개, 정적 13개
- 37개 모두 해당 문제 폴더와 일치하는 성공·미만료 Actions 산출물 확인
- 이미지 재빌드·재발행·pull, ZIP 본문 검사, Backend 등록 및 Runtime 생성은 이번에 수행하지 않음

[문제별 대조표](publication-table.md)는 slug·정적/동적·발행 run 개요입니다.
[전체 수집 목록 JSON](publication-state.json)에는 문제별 revision과 정확한 artifact ID·이름·출처가 있습니다.
10월 20일 보고서 이후 변경된 문제까지 이번 main 기준으로 다시 대조했습니다.

## Backend에 전달하는 필드

| 위치 | 의미 |
| --- | --- |
| `problems[].challenge_slug` | Backend 문제 매핑 키 |
| `problems[].runtime_required` | `true`는 deployment 있는 동적 문제, `false`는 정적 문제 |
| `problems[].status` | 현재 문제 폴더와 성공 산출물의 대조 결과 |
| `problems[].artifacts.publish` | 동적 문제의 release 등록용 publish bundle |
| `problems[].artifacts.user-files` | 정적·동적 문제의 참가자 파일 bundle |
| 각 artifact의 `registry_revision` | 해당 산출물을 발행한 revision |
| 각 artifact의 `run_id` | GitHub Actions 실행 ID |
| 각 artifact의 `id`, `name` | 다운로드할 artifact ID와 정확한 이름 |
| 각 artifact의 `source_sha` | 해당 성공 실행의 문제 출처 SHA |
| 각 artifact의 `run_status`, `run_conclusion`, `expired` | 완료·성공·미만료 여부 |
| 각 artifact의 `problem_tree_matches` | 보고서 기준 main의 해당 문제 폴더와 일치 여부 |

모든 문제에 같은 revision을 쓰지 않습니다. 변경이 없던 문제는 과거 성공 run의
산출물이 현재 문제 폴더와 일치할 수 있습니다. 각 문제·artifact에 기록된 값을 사용합니다.
정적 문제에는 publish bundle이 필요하지 않으며 참가자 파일 bundle을 수집합니다.
KOTH 6개의 별도 모델 연결은 합의된 계약을 따라야 하며 일반 Challenge에 임의로 중복 등록하지 않습니다.

이 목록은 Backend에 전달할 후보 목록이지 실제 DB 등록 결과가 아닙니다.
GHCR 이미지 내부 digest는 실제 `artifact-v2.json`의 컨테이너별 값을 확인해야 합니다.
실패한 전체 workflow에서 일부 생성된 bundle은 성공 근거에서 제외합니다.
보고서 생성 뒤 저장소가 변경되면 `source_sha`를 기준으로 후속 대조가 필요합니다.

## 개발 서버 배포 기록

GitHub에서 확인한 가장 최근 Backend 개발 배포 성공 기록은 다음과 같습니다.

- 대상 commit: `1271c466ec81ac5b3e146d7579d728ca4089dc78`
- [Backend CI 실행 39536795109](https://github.com/MSG-CTF/msg-backend/actions/runs/39536795109)
- 해당 실행의 `deploy-development` job과 실제 배포 단계가 성공
- 완료 시각: 2026-10-21 12:12 KST

이는 Actions의 배포 성공 기록입니다. 이번 작업에서 서버에 SSH로 접속하거나
현재 실행 컨테이너 SHA·migration·Poller 가동 상태를 직접 확인하지는 않았습니다.
서버에서 실행 중인 버전은 담당자의 실측 확인이 필요합니다.

## 코드에 정의된 Backend·Poller 실행 위치

기준은 위 Backend commit이며 실제 설치·가동 여부는 서버 담당자가 확인해야 합니다.

- Compose 작업 디렉터리: `/opt/msg-dev`
- Compose 프로젝트: `msg-dev`
- Compose 파일: `/opt/msg-dev/compose.yml`
- 환경변수 파일: `/opt/msg-dev/.env` — 원문은 공유하지 않음
- Backend 서비스: Compose의 `backend`
- Poller 명령: `backend` 컨테이너 안의 `python manage.py poll_releases`
- systemd 정의: `msg-release-poll.service`, `msg-release-poll.timer`
- timer 정의: 부팅 90초 뒤 시작, 이전 실행 종료 후 5분 간격

근거:

- [Poller service](https://github.com/MSG-CTF/msg-backend/blob/1271c466ec81ac5b3e146d7579d728ca4089dc78/deploy/msg-release-poll.service)
- [Poller timer](https://github.com/MSG-CTF/msg-backend/blob/1271c466ec81ac5b3e146d7579d728ca4089dc78/deploy/msg-release-poll.timer)
- [제한된 SSH 배포 계약](https://github.com/MSG-CTF/msg-backend/blob/1271c466ec81ac5b3e146d7579d728ca4089dc78/docs/backend-deploy-ssh.md)

## 서버 관리 담당자에게 받아야 할 항목

1. 현재 Backend API 주소와 개발 VM 식별자
2. 검증 담당자의 관리용 SSH 접속 방법과 허용 계정·접근 경로
3. 현재 실행 컨테이너의 실제 배포 SHA와 migration 적용 상태
4. `msg-release-poll.timer` 설치·활성 상태 및 최근 실행 성공 여부
5. 서버의 Actions 읽기 인증과 GCS 저장 인증 준비 여부 — 값이 아니라 준비 상태만 공유

CI 전용 `msg-backend-deploy` 계정은 forced command가 적용된 배포 전용 계정입니다.
일반 점검용 셸 계정으로 간주하지 않습니다. SSH host·key·known_hosts·토큰 원문은
GitHub Secret 또는 기존 승인된 보안 전달 경로로만 관리합니다.

## 이번 작업에서 한 것과 남은 것

- 완료: 최신 37개 발행 이력 대조, 문제별 수집 정보 정리, 기존 개발 배포 성공 기록과 코드상 실행 위치 확인
- 미실행: 개발 서버 SSH 접속, 실제 Poller 수집·DB 대조·GCS 다운로드·인스턴스 생성 시험
- 다음: 서버 관리 담당자가 접속과 실행 상태를 확인한 뒤 Backend팀이 이 목록으로 실제 수집 결과를 대조

관련 조회 도구 단위 테스트 14개가 통과했습니다. 실제 서버 배포 검증 성공으로 확대 해석하지 않습니다.
