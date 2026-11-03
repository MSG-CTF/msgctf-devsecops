# 최신 문제 발행 대조

2026-10-20 KST에 GitHub API를 읽기 전용으로 조회했습니다.
기준 문제 main은 `27b60a032cf2e378de0ad1c4eff8a20c951d4fee`입니다.
문제 빌드·재발행·이미지 pull·Backend 등록·Runtime 생성은 새로 실행하지 않았습니다.

## 결과

- 전체 37개: 동적 24개, 정적 13개
- 37개 모두 해당 문제 폴더와 필요한 성공·미만료 산출물이 일치
- 동적 문제는 publish bundle과 참가자 파일 bundle, 정적 문제는 참가자 파일 bundle 대조
- pwn-random6의 최신 폴더와 성공 run `39367715071`의 산출물이 일치
- web-afterimage의 성공 run `39367715071`도 현재 폴더와 일치
- 과거의 '36개 일치, random6 미발행'은 10월 19일 기록이며 현재 판정에 사용하지 않음

[문제별 대조표](publication-table.md)와 [출처·제외 근거 JSON](publication-state.json)에
문제별 source SHA·run·revision·artifact ID를 기록했습니다. raw info.yaml·flag·환경변수 값은 저장하지 않습니다.

폴더 일치는 현재 취약점 DB 재검사, 모든 GHCR digest의 실재·pull, Backend DB 등록,
실행 digest 대조·접속·reset·격리·전체 배포 성공을 의미하지 않습니다.
문제 폴더 밖 공통 설정 변경도 별도 검수가 필요합니다.

## Afterimage 실패 실행의 처리

run `39370165254`에서는 7개 이미지 build·scan·push와 aggregate가 성공한 뒤
Runtime HTTPS smoke가 실패했습니다. 생성된 publish bundle이 있어도 전체 run이 failure이므로
이번 대조 도구는 해당 artifact를 성공 근거에서 제외했습니다.

- [성공 발행 run](https://github.com/MSG-CTF/2026_MSG_CTF/actions/runs/39367715071)
- [후속 smoke 실패 run](https://github.com/MSG-CTF/2026_MSG_CTF/actions/runs/39370165254)

Backend의 현재 Poller도 completed/success인 workflow만 수집합니다.
발행 검사와 후속 Runtime 시험을 분리할 때도 이 성공 실행·출처 검증을 완화하지 않습니다.
Runtime 시험 실패는 별도 실패 결과로 남겨야 하며 '배포 검수 성공'으로 처리하면 안 됩니다.

## PR #20 최신 main 통합

- 통합 main: `9ebca724dce53a9f24533a96dd5b0d40317f7f82`
- 충돌은 docs/README.md와 tests/README.md의 목차였으며 양쪽 항목 보존
- #21 KOTH 점검, #22 TCP/PWN 프로필, #23 Afterimage 승인 취약점 31개 처리 유지
- 통합한 전체 로컬 단위 테스트 221개 통과
- 원격 HTTPS 연결 점검은 기본 비활성이며 Runtime 생성·삭제는 이번에 실행하지 않음

PR #19나 다른 파트 구현을 대신 수정하지 않았고 main 병합도 하지 않았습니다.
임시 작업 파일은 원격 반영과 검증을 마친 뒤 제거합니다.
