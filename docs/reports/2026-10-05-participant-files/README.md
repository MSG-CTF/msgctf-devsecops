# 전체 문제 참가자 파일 수집 결과

## 기준

- 문제 저장소: MSG-CTF/2026_MSG_CTF
- main 커밋: acb8c0a4511d03c0aba22efe0c8e2a4870d0fb98
- 실행: info.yaml 검증 → for_user 구조 검사 → ZIP 생성 → ZIP 재검사 → GCS 저장 계획
- 문제 37개: 동적 24개 / 정적 13개
- 파일 있음 28개 / 없음 9개
- 압축 전 총 크기: 164,402,128 bytes (문제별 100 MiB 제한 적용)
- 검토용 revision: 1. 실제 release 또는 등록 이력이 아닙니다.
- GCS 업로드 0건, Backend 등록 0건. Docker·취약점 전체 CI 재실행 결과도 아닙니다.

수집 JSON은 collection-plan.json에 있습니다. 실제 ZIP과 참가자 파일 내용은
DevSecOps 저장소에 커밋하지 않습니다. 로컬에서만 검증했으며 Actions 발행 결과로
기록하지 않습니다. root README.md/readme.md 대소문자 충돌을 피해 문제와 관계없는
두 루트 문서만 제외한 clean sparse checkout을 사용했습니다.

## 문제별 결과

| 문제 | 구분 | 참가자 파일 |
|---|---|---|
| crypto-nerves | 동적 | 있음 |
| crypto-reused-seal | 동적 | 없음 |
| crypto-tr88 | 정적 | 있음 |
| forensic-evidence | 정적 | 있음 |
| forensic-is-this-job-legit | 정적 | 없음 |
| forensic-leftovers | 정적 | 있음 |
| forensic-the-last-record | 정적 | 있음 |
| koth-card-battle-arena | 동적 | 없음 |
| koth-dependency-hell | 동적 | 있음 |
| koth-grand-tour-duel | 동적 | 있음 |
| koth-jenga | 동적 | 있음 |
| koth-pixel-smuggler | 동적 | 있음 |
| koth-swanopoly | 동적 | 있음 |
| misc-cashout | 동적 | 없음 |
| misc-hidden-order | 정적 | 있음 |
| misc-reqr | 동적 | 있음 |
| misc-snack-thief | 정적 | 있음 |
| osint-ramen-man | 정적 | 있음 |
| osint-the-past-has-an-address | 동적 | 있음 |
| osint-trace | 정적 | 있음 |
| pwn-ghost-file | 동적 | 있음 |
| pwn-msgdriver | 정적 | 있음 |
| pwn-note | 동적 | 있음 |
| pwn-price-tag | 동적 | 있음 |
| pwn-random6 | 동적 | 있음 |
| rev-ezpz | 정적 | 있음 |
| rev-phantom-lattice | 정적 | 있음 |
| rev-rework | 정적 | 있음 |
| rev-tinyvm | 동적 | 있음 |
| web-afterimage | 동적 | 있음 |
| web-daily-point | 동적 | 없음 |
| web-grade-tampering | 동적 | 없음 |
| web-logout-please | 동적 | 있음 |
| web-notebook | 동적 | 없음 |
| web-open-house | 동적 | 없음 |
| web3-infinite-pack | 동적 | 없음 |
| web3-split-brain-oracle | 동적 | 있음 |

구분은 분야가 아니라 deployment 유무입니다. 파일이 있다는 것은 구조·용량·ZIP
검증 통과이지 참가자 공개 승인, 악성코드 검사, 실제 다운로드 성공을 뜻하지 않습니다.
