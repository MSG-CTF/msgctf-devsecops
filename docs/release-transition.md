# A/B 버전 전환 사전 준비

이 도구는 **무중단 전환의 사전검수와 HTTP 관측**을 준비합니다. 실제 이미지 pull,
active 변경, 인스턴스 생성·교체·삭제, 트래픽 전환은 실행하지 않습니다. 독립 API나
트래픽 라우터를 새로 만들지 않으며 기존 Backend·Runtime 응답을 사용합니다.

## 서로 다른 두 가지 전환

| 구분 | 의미 | 현재 확인한 코드 |
|---|---|---|
| 새 생성부터 B 사용 | 기존 참가자 A는 유지하고 이후 새 인스턴스만 B로 생성 | Backend current release 전환의 기존 동작 |
| 실행 중 A를 B로 무중단 교체 | B를 먼저 정상 기동하고 같은 접속 경로를 넘긴 뒤 A를 정리 | 소비자 계약·구현과 실제 검증이 별도로 필요 |

Scheduler의 현재 create/replace는 A를 CLEANUP_PENDING으로 먼저 바꿉니다. 같은
사용자의 실행 중복 제약과 기존 정리 후 재예약도 존재합니다. 이 경로를 B 사전
기동에 쓰거나 reset을 B 업그레이드로 사용하지 않습니다. URL이 바뀐 뒤 사람이
다시 접속하는 것과 기존 연결·상태를 유지하는 무중단 전환도 구분합니다.

```text
A 운영 유지
  → 승인된 B 전체 이미지 준비
  → B의 현재 readiness 및 별도 QA 확인
  → [서버 측 계약 필요] B 병렬 기동·정상 판정
  → [서버 측 계약 필요] 접속 경로 전환
  → 전환·기존 연결 처리 확인 후 A 정리

B 실패 / 준비 만료 / 버전 변경
  → 전환 중단, A 유지 (이전 컨테이너·이미지·파일·설정 보존)
```

다운로드와 readiness는 Pod 기동·healthcheck·실제 공개 접속 성공이 아닙니다.
기존 [SSH 사전 다운로드](vm-image-prefetch.md)와 [readiness 대조](node-readiness-audit.md)를
재사용하되, 그 성공만으로 운영 전환을 승인하지 않습니다.

## 1. A/B 사전검수

`scripts.prepare_release_transition`은 다음 **저장된 자료만** 읽습니다.

- A·B의 공식 성공 main `artifact-v2.json` 원본. 원본 출처는 기존 발행 검증 절차로 확인합니다.
- Backend 릴리스 목록 GET 응답의 `data` 객체. challenge_id, current_release_id,
  releases, activation을 보존합니다. 서버 조회 시각은 별도로 기록합니다.
- 후보 B에 대한 Runtime readiness query의 전체 응답과 정확한 target 목록.

Backend 파일은 60초 미만의 관측만 허용합니다. 이는 운영자가 입력한 조회 시각이며
이 도구가 서버를 독립 조회한 증거는 아닙니다. `--as-of`는 과거 재현용입니다.
새 전환·실행 승인으로 쓰지 않고 실제 시험 직전에 최신 자료로 다시 검사합니다.

검사하는 항목:

- 같은 일반 Linux K3s WEB 문제·architecture, 서로 다른 A/B release ID.
- 현재 active=A, A/B 승인·배포 가능 여부, 진행 중인 다른 활성화 의도 부재.
- 전체 공개·비공개 컨테이너의 image digest·포트·공개 여부와 자원·healthcheck 보존.
- schema 2.1 env·secret 이름/등록 상태/버전. 값은 출력하지 않고 설정 fingerprint만 보존.
- B의 정확한 전체 image set, 모든 지정 target의 현재 전체 적합 노드 준비·관측·만료.
- update는 증가하는 revision만 허용합니다. 낮은 revision은 명시적 rollback 방향이 필요합니다.

Backend 파생 릴리스, env_rules, 원본 bundle에 없는 환경값, 지원하지 않는 실행 필드는
자동으로 추측·보완하지 않고 별도 유효 설정 검토가 필요하다고 거절합니다. KOTH·PWN·
Windows·DOCKER·VM은 이번 전환 도구의 범위가 아닙니다. Runtime의 이미지별 UID·쓰기
경로·네트워크 정책, 전체 운영 노드의 누락 여부는 독립 확인하지 않습니다.

```bash
python3 -B -m scripts.prepare_release_transition \
  --current-artifact /private/a/artifact-v2.json \
  --candidate-artifact /private/b/artifact-v2.json \
  --backend-releases /private/releases-data.json \
  --current-release-id CURRENT_RELEASE_UUID \
  --candidate-release-id CANDIDATE_RELEASE_UUID \
  --backend-observed-at ACTUAL_RFC3339_QUERY_TIME \
  --candidate-readiness /private/b-readiness-response.json \
  --target-id APPROVED_TARGET \
  --output-dir /private/new-transition-plan
```

target이 여러 곳이면 `--target-id`를 반복합니다. readiness를 생략해 준비 요청
인계안부터 만들 수 있지만 `IMAGE_READINESS_REQUIRED`와 종료 코드 1이 나옵니다.
readiness가 전부 맞아도 판정은 `READY_FOR_REPRESENTATIVE_QA`까지만입니다.
이 경우 종료 코드 0은 계획 검수 성공이지 배포 실행·활성화·무중단 승인 코드가 아닙니다.
입력 불일치는 종료 코드 2입니다.

`transition-plan.json`에는 A/B 원본 checksum·전체 이미지와 보존 합집합, 설정
fingerprint, target/readiness 대조, 정확한 기존 준비·배포 테스트 API 인계안이 담깁니다.
각 POST는 사람이 승인한 뒤 기존 Backend로 접수하는 예시일 뿐 호출하지 않습니다.
준비 요청에는 고유 Idempotency-Key, 배포 테스트에는 canonical UUID request_id를
운영자가 별도로 선택·기록해야 합니다. 생성된 문구를 그대로 요청 ID로 사용하지 않습니다.
`/activate`, reset, replace, delete 요청은 생성하지 않습니다.

원본·Backend·Runtime 응답을 공개 artifact나 commit에 넣지 않습니다. 새 보고서
디렉터리는0700, JSON은0600이며 기존 출력은 덮어쓰지 않습니다. env·비밀값 원문을
복사하지 않지만 digest·release/target ID와 fingerprint도 운영 자료이므로 비공개로
보관합니다. plan SHA는 변경 탐지용이지 서명·인증·실행 허가가 아닙니다.

## 2. 공개 HTTP 접속 관측

`scripts.observe_rollout_http`는 운영자가 승인한 GET-safe 공개 WEB URL에만 접속합니다.
전환 계획과 관측 결과를 plan SHA로 연결하고 status·헤더 도착까지의 지연·고정 오류
코드만 기록합니다. 토큰·쿠키를 보내거나 응답 본문·헤더·URL 원문을 보고서에 저장하지 않습니다.

```bash
python3 -B -m scripts.observe_rollout_http \
  --plan /private/new-transition-plan/transition-plan.json \
  --url https://approved-public-endpoint.example/health \
  --duration-seconds 120 --interval-seconds 1 --timeout-seconds 2 \
  --output-dir /private/new-http-observation
```

기본 HTTPS는 인증서를 검증합니다. 공개 HTTP 문제는 승인 후 `--allow-http`를 명시할
수 있으나 TLS 검증이 없는 사실이 결과에 남습니다. 기본 예상 상태는200이고 health
endpoint가204라면 `--expected-status 204`를 명시합니다. 로그인 화면의200 응답만으로
문제 기능을 검증한 것으로 계산하지 않습니다.

userinfo·query·fragment·임의 header/인증 입력, 비공개/metadata 주소, redirect와
환경변수 proxy를 허용하지 않습니다. DNS의 모든 주소가 public인지 확인한 뒤 첫
주소를 해당 관측 동안 고정하고 원래 hostname으로 Host/SNI·인증서를 검증합니다.
DNS 주소 교체를 검증하는 도구는 아니며, 다른 A/B URL은 별도 실행으로 관측합니다.
GET-safe 경로인지 운영자가 먼저 확인해야 합니다.

관측은 최대900초·300회이며 느린 요청 뒤 몰아서 따라잡지 않습니다. 요청 timeout은
소켓 작업의 제한이고 응답 헤더 전체의 엄격한 wall-clock 상한은 아닙니다. 실제 지연과
관측 시각을 기록하며, 오류 뒤에도 정한 구간을 관측하고 중간 종료는 INTERRUPTED로
남깁니다. 완료한 샘플과 실패도 비공개 JSON에 원자적으로 보존합니다.

**NO_HTTP_FAILURE_OBSERVED는 표본에서 HTTP 실패를 못 봤다는 뜻입니다.** B 버전
실행 imageID, 실제 healthcheck, 지속 TCP/WebSocket 연결, 표본 사이의 접속 보장,
DB·업로드·세션 보존이나 롤백 성공을 증명하지 않습니다. 모든 요청이200이어도
`zero_downtime_proven=false`입니다. HTTP 관측은 기존 Pod·release·트래픽을 변경하지 않습니다.

## 3. 실제 시험 순서와 파트 경계

1. 진웅/DevSecOps: 승인된 대표 WEB의 A/B 원본·현재 운영 선택을 대조하고 계획을 만듭니다.
2. 이미지 준비: 기존 경로로 B를 준비하고 현재 readiness를 재조회합니다. 과거 operation
   성공이나 캐시 존재만으로 대신하지 않습니다. A 이미지를 삭제하지 않습니다.
3. Backend/Runtime: 승인된 별도 관리자 배포 테스트로 B의 실제 imageID·healthcheck·공개
   접속을 확인합니다. 이는 참가자 A의 접속 경로 전환이 아닙니다. QA 자원·팀·설정과
   정리 담당을 먼저 확정하며 우리 도구는 자동 생성·삭제하지 않습니다.
4. 진웅/DevSecOps: A URL 관측을 전환 전에 시작하고 B 기동·전환·안정화 동안 유지합니다.
5. Backend·Scheduler·Runtime/접속 경로 담당: 아래 계약을 반영한 별도 전환기로 B를
   선택합니다. 기존 replace/reset을 무중단 교체기로 대신하지 않습니다.
6. 공동: 이전 A 유지, B 실제 사용, 실패 시 A 유지, rollback, 연결·상태 보존을 확인합니다.
   성공 이후에만 합의된 시점에 A를 정리합니다. 관측 보고서 하나로 전체 통과 처리하지 않습니다.

실제 소비자 계약에서 추가로 정할 사항:

| 항목 | 필요한 결정 | 담당 구현 |
|---|---|---|
| 병렬 A/B | 동일 사용자·문제의 B 준비용 별도 실행과 임시 이중 자원 예약 | Backend·Scheduler·Broker |
| 접속 전환 | 안정된 URL/포트의 소유 주체, 원자적 switch·drain·확인 방법 | Backend·Runtime·접속 경로 담당 |
| 상태·연결 | DB/파일/세션 이관·호환, 기존 TCP/WebSocket 처리, TTL 보존 | 출제자·Backend·Runtime |
| 실패·rollback | B 실패 시 A를 유지하고 중복 전환·이전 generation을 막는 기준 | Backend·Scheduler·Runtime |
| 자동화 연결 | 발행·가져오기·준비·승인·전환의 식별자와 결과 연결 | 각 소비자·DevSecOps |

완성되지 않은 switch API 이름이나 인증 범위를 임의로 만들지 않습니다. 기존 설정의
자동 활성화 여부도 이 도구에서 바꾸지 않습니다. 자동화 연결 전까지 사전검수와
관측 도구로 준비하고 실제 배포 권한·승인은 각 담당 시스템에서 유지합니다.

## 확인한 기존 계약

- [Backend release 응답·실행 설정](https://github.com/MSG-CTF/msg-backend/blob/6ffed88cbdc743716bf8486b999d12cc9ecc6f12/apps/instances/releases.py#L470)
- [Backend current release 전환과 기존 인스턴스 유지](https://github.com/MSG-CTF/msg-backend/blob/6ffed88cbdc743716bf8486b999d12cc9ecc6f12/apps/instances/admin_views.py)
- [기존 준비 API](https://github.com/MSG-CTF/msg-backend/blob/6ffed88cbdc743716bf8486b999d12cc9ecc6f12/apps/instances/image_preparation_views.py)
- [기존 관리자 배포 테스트 API](https://github.com/MSG-CTF/msg-backend/blob/6ffed88cbdc743716bf8486b999d12cc9ecc6f12/apps/instances/deployment_test_views.py#L40)
- [Scheduler의 선행 정리·reset 버전 보존](https://github.com/MSG-CTF/instance-scheduler/blob/e94eaf17a1a3408524de90946b90f3f6cb6b9a69/src/main/kotlin/kr/msgctf/scheduler/instance/service/InstanceSchedulerService.kt)
- [Scheduler 교체 대기](https://github.com/MSG-CTF/instance-scheduler/blob/e94eaf17a1a3408524de90946b90f3f6cb6b9a69/docs/replacement-wait.md)

이 고정 소스 대조는 해당 버전의 실제 서버 배포 확인이 아닙니다.
