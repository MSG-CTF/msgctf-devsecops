# 문제 실행 설정 점검

기준 source_sha: `25e7c6b636ba11b16c77e09274563fe92fbb9003`

총 37개: 서버 문제 24개, 정적 문제 13개.

설정 이름과 존재 여부만 점검했습니다. 빌드·취약점 검사·배포 성공을 의미하지 않습니다.
환경변수 참조는 후보이며 필수 여부와 Compose 서비스 대응은 출제자 확인이 필요합니다.

INFO_ONLY인 항목은 명세만 읽었습니다. 환경변수·Compose·소스는 미점검이며 미발견을 설정 부재로 해석하지 않습니다.

| 문제 | 구분 | info healthcheck | 환경변수 이름(후보) | 확인 필요한 설정 | 점검 |
|---|---|---|---|---|---|
| crypto-nerves | 서버 | 없음 | 미발견 | 미발견 | 명세만 점검 |
| crypto-reused-seal | 서버 | 없음 | 미발견 | 미발견 | 명세만 점검 |
| crypto-tr88 | 정적 | 없음 | 미발견 | 미발견 | 명세만 점검 |
| forensic-evidence | 정적 | 없음 | 미발견 | 미발견 | 명세만 점검 |
| forensic-is-this-job-legit | 정적 | 없음 | 미발견 | 미발견 | 명세만 점검 |
| forensic-leftovers | 정적 | 없음 | 미발견 | 미발견 | 명세만 점검 |
| forensic-the-last-record | 정적 | 없음 | 미발견 | 미발견 | 명세만 점검 |
| koth-card-battle-arena | 서버 | 있음 | 미발견 | 미발견 | 명세만 점검 |
| koth-dependency-hell | 서버 | 있음 | 미발견 | 미발견 | 명세만 점검 |
| koth-grand-tour-duel | 서버 | 있음 | 미발견 | 미발견 | 명세만 점검 |
| koth-jenga | 서버 | 있음 | 미발견 | 미발견 | 명세만 점검 |
| koth-pixel-smuggler | 서버 | 있음 | 미발견 | 미발견 | 명세만 점검 |
| koth-swanopoly | 서버 | 있음 | 미발견 | 미발견 | 명세만 점검 |
| misc-cashout | 서버 | 없음 | 미발견 | 미발견 | 명세만 점검 |
| misc-hidden-order | 정적 | 없음 | 미발견 | 미발견 | 명세만 점검 |
| misc-reqr | 서버 | 없음 | 미발견 | 미발견 | 명세만 점검 |
| misc-snack-thief | 정적 | 없음 | 미발견 | 미발견 | 명세만 점검 |
| osint-ramen-man | 정적 | 없음 | 미발견 | 미발견 | 명세만 점검 |
| osint-the-past-has-an-address | 서버 | 없음 | 미발견 | 미발견 | 명세만 점검 |
| osint-trace | 정적 | 없음 | 미발견 | 미발견 | 명세만 점검 |
| pwn-ghost-file | 서버 | 없음 | 미발견 | 미발견 | 명세만 점검 |
| pwn-msgdriver | 정적 | 없음 | 미발견 | 미발견 | 명세만 점검 |
| pwn-note | 서버 | 없음 | 미발견 | 미발견 | 명세만 점검 |
| pwn-price-tag | 서버 | 없음 | 미발견 | 미발견 | 명세만 점검 |
| pwn-random6 | 서버 | 없음 | 미발견 | 미발견 | 명세만 점검 |
| rev-ezpz | 정적 | 없음 | 미발견 | 미발견 | 명세만 점검 |
| rev-phantom-lattice | 정적 | 없음 | 미발견 | 미발견 | 명세만 점검 |
| rev-rework | 정적 | 없음 | 미발견 | 미발견 | 명세만 점검 |
| rev-tinyvm | 서버 | 없음 | 미발견 | 미발견 | 명세만 점검 |
| web-afterimage | 서버 | 없음 | 미발견 | 미발견 | 명세만 점검 |
| web-daily-point | 서버 | 없음 | 미발견 | 미발견 | 명세만 점검 |
| web-grade-tampering | 서버 | 없음 | 미발견 | 미발견 | 명세만 점검 |
| web-logout-please | 서버 | 있음 | 미발견 | 미발견 | 명세만 점검 |
| web-notebook | 서버 | 없음 | 미발견 | 미발견 | 명세만 점검 |
| web-open-house | 서버 | 없음 | 미발견 | 미발견 | 명세만 점검 |
| web3-infinite-pack | 서버 | 없음 | 미발견 | 미발견 | 명세만 점검 |
| web3-split-brain-oracle | 서버 | 없음 | 미발견 | 미발견 | 명세만 점검 |

## 배포 사양과 협업 확인 항목

자원은 info.yaml의 문제 전체 합산 선언값입니다. 컨테이너별 배분·복제 수·서버 가용량은 확인하지 않았습니다.
INFO_ONLY는 info.yaml만 읽은 점검입니다. 환경변수·Compose·소스 미발견을 설정이 없다는 증거로 사용하지 않습니다.
운영체제를 선언하는 계약은 아직 없어 .exe 파일이나 VM 값만으로 Windows 문제를 판정하지 않습니다.
확인 항목은 배포 승인이나 새로운 CI 차단 조건이 아닙니다. Registry 등록·실제 실행·복구 성공도 의미하지 않습니다.

| 문제 | category | runtime_type | architecture | 컨테이너 수 | CPU(m) | 메모리(MiB) | 임시 저장소(MiB) | 범위 | 협업 확인 항목 |
|---|---|---|---|---:|---:|---:|---:|---|---|
| crypto-nerves | crypto | KUBERNETES | AMD64 | 1 | 1000 | 512 | 256 | INFO_ONLY | 추가 판정 없음 |
| crypto-reused-seal | crypto | KUBERNETES | AMD64 | 1 | 500 | 512 | 1024 | INFO_ONLY | 추가 판정 없음 |
| crypto-tr88 | crypto | 미선언 | 미선언 | 0 | 미선언 | 미선언 | 미선언 | INFO_ONLY | 추가 판정 없음 |
| forensic-evidence | forensics | 미선언 | 미선언 | 0 | 미선언 | 미선언 | 미선언 | INFO_ONLY | 추가 판정 없음 |
| forensic-is-this-job-legit | forensic | 미선언 | 미선언 | 0 | 미선언 | 미선언 | 미선언 | INFO_ONLY | 추가 판정 없음 |
| forensic-leftovers | forensic | 미선언 | 미선언 | 0 | 미선언 | 미선언 | 미선언 | INFO_ONLY | 추가 판정 없음 |
| forensic-the-last-record | forensic | 미선언 | 미선언 | 0 | 미선언 | 미선언 | 미선언 | INFO_ONLY | 추가 판정 없음 |
| koth-card-battle-arena | koth | KUBERNETES | AMD64 | 1 | 500 | 512 | 1024 | INFO_ONLY | koth_release_mapping, koth_deployment_and_recovery_owner, koth_capacity_and_replica_plan |
| koth-dependency-hell | koth | KUBERNETES | AMD64 | 4 | 5500 | 3072 | 4096 | INFO_ONLY | koth_release_mapping, koth_deployment_and_recovery_owner, koth_capacity_and_replica_plan |
| koth-grand-tour-duel | koth | KUBERNETES | AMD64 | 1 | 6000 | 1536 | 2048 | INFO_ONLY | koth_release_mapping, koth_deployment_and_recovery_owner, koth_capacity_and_replica_plan |
| koth-jenga | koth | KUBERNETES | AMD64 | 1 | 300 | 256 | 512 | INFO_ONLY | koth_release_mapping, koth_deployment_and_recovery_owner, koth_capacity_and_replica_plan |
| koth-pixel-smuggler | koth | KUBERNETES | AMD64 | 1 | 1000 | 1024 | 1024 | INFO_ONLY | koth_release_mapping, koth_deployment_and_recovery_owner, koth_capacity_and_replica_plan |
| koth-swanopoly | koth | KUBERNETES | AMD64 | 4 | 6000 | 4096 | 2048 | INFO_ONLY | koth_release_mapping, koth_deployment_and_recovery_owner, koth_capacity_and_replica_plan |
| misc-cashout | misc | KUBERNETES | AMD64 | 1 | 250 | 128 | 128 | INFO_ONLY | 추가 판정 없음 |
| misc-hidden-order | misc | 미선언 | 미선언 | 0 | 미선언 | 미선언 | 미선언 | INFO_ONLY | 추가 판정 없음 |
| misc-reqr | misc | DOCKER | AMD64 | 1 | 500 | 256 | 256 | INFO_ONLY | 추가 판정 없음 |
| misc-snack-thief | misc | 미선언 | 미선언 | 0 | 미선언 | 미선언 | 미선언 | INFO_ONLY | 추가 판정 없음 |
| osint-ramen-man | osint | 미선언 | 미선언 | 0 | 미선언 | 미선언 | 미선언 | INFO_ONLY | 추가 판정 없음 |
| osint-the-past-has-an-address | osint | KUBERNETES | AMD64 | 1 | 500 | 512 | 1024 | INFO_ONLY | 추가 판정 없음 |
| osint-trace | osint | 미선언 | 미선언 | 0 | 미선언 | 미선언 | 미선언 | INFO_ONLY | 추가 판정 없음 |
| pwn-ghost-file | pwn | DOCKER | AMD64 | 1 | 250 | 128 | 256 | INFO_ONLY | 추가 판정 없음 |
| pwn-msgdriver | pwn | 미선언 | 미선언 | 0 | 미선언 | 미선언 | 미선언 | INFO_ONLY | 추가 판정 없음 |
| pwn-note | pwn | KUBERNETES | AMD64 | 1 | 250 | 256 | 256 | INFO_ONLY | 추가 판정 없음 |
| pwn-price-tag | pwn | KUBERNETES | AMD64 | 1 | 250 | 128 | 256 | INFO_ONLY | 추가 판정 없음 |
| pwn-random6 | pwn | DOCKER | AMD64 | 1 | 500 | 256 | 512 | INFO_ONLY | 추가 판정 없음 |
| rev-ezpz | rev | 미선언 | 미선언 | 0 | 미선언 | 미선언 | 미선언 | INFO_ONLY | 추가 판정 없음 |
| rev-phantom-lattice | rev | 미선언 | 미선언 | 0 | 미선언 | 미선언 | 미선언 | INFO_ONLY | 추가 판정 없음 |
| rev-rework | rev | 미선언 | 미선언 | 0 | 미선언 | 미선언 | 미선언 | INFO_ONLY | 추가 판정 없음 |
| rev-tinyvm | rev | KUBERNETES | AMD64 | 1 | 500 | 512 | 1024 | INFO_ONLY | 추가 판정 없음 |
| web-afterimage | web | KUBERNETES | AMD64 | 7 | 2000 | 4000 | 2048 | INFO_ONLY | 추가 판정 없음 |
| web-daily-point | web | KUBERNETES | AMD64 | 1 | 500 | 512 | 1024 | INFO_ONLY | 추가 판정 없음 |
| web-grade-tampering | web | KUBERNETES | AMD64 | 1 | 300 | 256 | 512 | INFO_ONLY | 추가 판정 없음 |
| web-logout-please | web | KUBERNETES | AMD64 | 1 | 300 | 256 | 128 | INFO_ONLY | 추가 판정 없음 |
| web-notebook | web | KUBERNETES | AMD64 | 2 | 700 | 768 | 1024 | INFO_ONLY | 추가 판정 없음 |
| web-open-house | web | KUBERNETES | AMD64 | 1 | 500 | 512 | 1024 | INFO_ONLY | 추가 판정 없음 |
| web3-infinite-pack | web3 | KUBERNETES | AMD64 | 1 | 2000 | 512 | 128 | INFO_ONLY | 추가 판정 없음 |
| web3-split-brain-oracle | web3 | KUBERNETES | AMD64 | 1 | 1000 | 1024 | 2048 | INFO_ONLY | 추가 판정 없음 |
