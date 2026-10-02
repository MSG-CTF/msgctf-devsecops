# 문제 실행 설정 점검

기준 source_sha: `efb2fa39f5e935224fc4be1d24bea6db5930c57a`

총 37개: 서버 문제 23개, 정적 문제 14개.

설정 이름과 존재 여부만 점검했습니다. 빌드·취약점 검사·배포 성공을 의미하지 않습니다.
환경변수 참조는 후보이며 필수 여부와 Compose 서비스 대응은 출제자 확인이 필요합니다.

| 문제 | 구분 | info healthcheck | 환경변수 이름(후보) | 확인 필요한 설정 | 점검 |
|---|---|---|---|---|---|
| crypto-nerves | 서버 | 없음 | FLAG | environment | 완료 |
| crypto-reused-seal | 서버 | 없음 | FLAG_PATH | container_mapping, environment | 완료 |
| crypto-tr88 | 정적 | 없음 | 미발견 | 미발견 | 완료 |
| forensic-evidence | 정적 | 없음 | 미발견 | 미발견 | 완료 |
| forensic-is-this-job-legit | 정적 | 없음 | 미발견 | 미발견 | 완료 |
| forensic-leftovers | 정적 | 없음 | 미발견 | 미발견 | 완료 |
| forensic-the-last-record | 정적 | 없음 | 미발견 | 미발견 | 완료 |
| koth-card-battle-arena | 서버 | 있음 | ARENA_ATTACK_RATE_PER_SEC, ARENA_COOLDOWN_SECONDS, ARENA_REGEN_PER_SEC, ARENA_TURN_SECONDS, DATABASE_PATH, DATA_DIR, DEV_MODE, DEV_TEAM_TOKENS 외 9개(JSON 참고) | environment, healthcheck, read_only, tmpfs, volumes | 완료 |
| koth-dependency-hell | 서버 | 있음 | ALLOW_INSECURE_DATABASE, ALLOW_INSECURE_DEV_DATABASE, ALLOW_INSECURE_DEV_RUNNER_HTTP, ALLOW_INSECURE_PLATFORM_HTTP, ALLOW_WEAK_DATABASE_TLS, API_CLIENT_CA_FILE, API_REQUEST_TIMEOUT_SECONDS, ARTIFACT_PRUNE_INTERVAL_SECONDS 외 191개(JSON 참고) | cap_add, command, container_mapping, depends_on, entrypoint, environment, healthcheck, network_mode, network_segmentation, networks, read_only, tmpfs, user, volumes | 완료 |
| koth-grand-tour-duel | 서버 | 있음 | HEALTH_ORIGIN, HEALTH_PORT, INTERNAL_TOKEN, KOTH_CAPACITY_TEAM_COUNT, KOTH_CHALLENGE_ID, KOTH_DATABASE_PATH, KOTH_INTERNAL_TOKEN, KOTH_OFFICIAL_SCHEDULER_ENABLED 외 16개(JSON 참고) | cap_add, container_mapping, depends_on, environment, healthcheck, network_mode, read_only, tmpfs, volumes | 완료 |
| koth-jenga | 서버 | 있음 | ALLOW_DEMO_AUTH, DEV_AUTH_BYPASS, DEV_AUTH_TOKEN, FLAG, INTERNAL_TOKEN, JENGA_DB, JWT_SECRET, KOTH_CHALLENGE_ID 외 11개(JSON 참고) | command, container_mapping, depends_on, environment, volumes, working_dir | 일부 미점검 |
| koth-nonce-upon-a-time | 서버 | 있음 | DATABASE_PATH, DATA_DIR, DEV_MODE, DEV_TEAM_TOKENS, HTTP_THREADS, KOTH_CHALLENGE_ID, KOTH_INTERNAL_TOKEN, PLATFORM_INTERNAL_TOKEN 외 6개(JSON 참고) | environment, healthcheck, read_only, tmpfs, volumes | 완료 |
| koth-swanopoly | 서버 | 있음 | BACKEND_HOST, BACKEND_PORT, BOT_PYTHON, BOT_RUNNER_ALLOW_INPROCESS, BOT_WORKER_PATH, KOTH_CHALLENGE_ID, KOTH_INTERNAL_TOKEN, KOTH_SCORING_SECRET 외 22개(JSON 참고) | depends_on, environment, volumes | 완료 |
| misc-cashout | 서버 | 없음 | PYTHONDONTWRITEBYTECODE | environment | 완료 |
| misc-hidden-order | 정적 | 없음 | 미발견 | 미발견 | 완료 |
| misc-reqr | 서버 | 없음 | AUTO_GENERATE, BASE_URL, FLAG, INSTANCE_DIR, INSTANCE_SEED, PYTHONDONTWRITEBYTECODE | container_mapping, environment | 완료 |
| misc-snack-thief | 정적 | 없음 | 미발견 | 미발견 | 완료 |
| osint-ramen-man | 정적 | 없음 | 미발견 | 미발견 | 완료 |
| osint-the-past-has-an-address | 정적 | 없음 | 미발견 | 미발견 | 완료 |
| osint-trace | 정적 | 없음 | 미발견 | 미발견 | 완료 |
| pwn-ghost-file | 서버 | 없음 | 미발견 | 미발견 | 완료 |
| pwn-msgdriver | 정적 | 없음 | 미발견 | 미발견 | 완료 |
| pwn-note | 서버 | 없음 | 미발견 | 미발견 | 완료 |
| pwn-price-tag | 서버 | 없음 | 미발견 | 미발견 | 완료 |
| pwn-random6 | 서버 | 없음 | FLAG, PORT | environment | 완료 |
| rev-ezpz | 정적 | 없음 | 미발견 | 미발견 | 완료 |
| rev-phantom-lattice | 정적 | 없음 | 미발견 | 미발견 | 완료 |
| rev-rework | 정적 | 없음 | 미발견 | 미발견 | 완료 |
| rev-tinyvm | 서버 | 없음 | FLAG, PYTHONDONTWRITEBYTECODE, TINYVM_CLIENT_TIMEOUT, TINYVM_HOST, TINYVM_PORT | environment | 완료 |
| web-afterimage | 서버 | 없음 | BIND_HOST, BOT_URL, CARTRIDGE_HOST, CARTRIDGE_KEY, CARTRIDGE_PORT, CASE_VAULT_HOST, CASE_VAULT_PORT, CHROME_PATH 외 16개(JSON 참고) | cap_add, depends_on, environment, healthcheck, network_segmentation, networks, read_only, tmpfs | 완료 |
| web-daily-point | 서버 | 없음 | ATTENDANCE_REWARD, DATABASE_PATH, FLAG, FLAG_PRICE, PYTHONDONTWRITEBYTECODE, RACE_DELAY, SECRET_KEY | environment, healthcheck, volumes | 완료 |
| web-grade-tampering | 서버 | 없음 | FLAG, PORT, PYTHONDONTWRITEBYTECODE, SECRET_KEY | environment | 완료 |
| web-logout-please | 서버 | 있음 | DEV_MODE, FLAG | container_mapping, environment, read_only, tmpfs | 완료 |
| web-notebook | 서버 | 없음 | DB_HOST, DB_NAME, DB_PASS, DB_USER, POSTGRES_DB, POSTGRES_PASSWORD, POSTGRES_USER | depends_on, environment | 완료 |
| web-open-house | 서버 | 없음 | 미발견 | 미발견 | 완료 |
| web3-infinite-pack | 서버 | 없음 | FLAG, FLAG_FILE, HOME, INFINITE_PACK_ANVIL_PORT, INFINITE_PACK_CLIENT_TIMEOUT, INFINITE_PACK_HOST, INFINITE_PACK_MAX_RESETS, INFINITE_PACK_MAX_SESSIONS 외 4개(JSON 참고) | environment | 완료 |
| web3-split-brain-oracle | 서버 | 없음 | DEPLOYER_PRIVATE_KEY, DEPLOYMENT_FILE, FLAG, FRONTDOOR_GATEWAY_URL, FRONTDOOR_HOST, FRONTDOOR_PORT, FRONTDOOR_RPC_URL, GATEWAY_HOST 외 13개(JSON 참고) | environment | 완료 |
