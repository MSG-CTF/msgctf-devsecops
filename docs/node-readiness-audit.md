# 노드 이미지 준비 응답 대조

`scripts/audit_node_image_readiness.py`는 기존 publish bundle과 **저장된 Runtime
readiness 원본 JSON**을 오프라인에서 대조합니다. 준비 API·노드·GHCR·Backend를
호출하거나 이미지를 다운로드하지 않습니다. 정보 조회·준비 worker·Scheduler·릴리스
활성화 구현을 대체하지 않으며, 기존 생성 fallback이나 준비 선호 정책을 변경하지 않습니다.

## 입력과 범위

- 공식 성공 발행에서 가져온 `artifact-v2.json`: schema2.0/2.1의 일반 Linux K3s 문제.
- Runtime `POST /v1/image-readiness/query`가 실제 반환한 JSON. operation의 SUCCEEDED
  이력이나 카톡 요약문으로 대신하지 않습니다.
- 운영 담당자가 확인한 **예상 target ID 전체 목록**. 노드명으로 추측하지 않습니다.
- 판정 기준 시각. 생략하면 실행 PC의 현재 UTC이며, 과거 증거 재현에는 `--as-of`를 씁니다.

기존 `generate_node_image_plan.py`를 재사용해 main 출처 형식·revision·검사 증거·
전체 컨테이너의 고정 GHCR 참조를 검사합니다. KOTH·VM·DOCKER는 제외합니다.
이는 **입력 자료의 계약 검사**입니다. GitHub run/artifact의 진위·출처나 Backend의
현재 active release를 독립 조회한 것이 아니므로 기존 출처 검증을 먼저 거쳐야 합니다.
schema2.1의 env·비밀값 참조도 보고서에 복사하지 않습니다.

## 검사 내용

1. 공개 컨테이너뿐 아니라 DB 등 보조 컨테이너를 포함한 전체 이미지 집합을 사용합니다.
2. architecture와 전체 참조 집합으로 Runtime canonical `image_set_id`를 재계산해
   응답과 비교합니다. JSON 파일 hash·줄 단위 이미지 목록 checksum과는 다릅니다.
3. 예상 target 누락은 UNKNOWN입니다. 중복·예상 밖 target이나 모순된 개수/타입은
   잘못된 응답으로 거절합니다.
4. `observed_at <= 판정 시각 < valid_until`을 확인하고 RFC3339Nano를 나노초까지
   비교합니다. 미래 관측·만료·시각 누락/오류를 준비 완료로 표시하지 않습니다.
5. 최대 관측 나이는 기본60초이며 현재 Scheduler 기본값과 같습니다. 운영 설정이
   다르면 승인된 값으로 `--max-observation-age-seconds`를 지정합니다. 이 옵션은
   실제 Runtime·Scheduler 설정이나 증거의 시각을 바꾸지 않습니다.
6. 만료·미관측 target의 개수를 현재 준비된 노드 합계에 포함하지 않습니다.

`ready=true`는 적합한 같은 노드 **한 대 이상**에 전체 이미지가 있다는 힌트입니다.
`ready_node_count=1, eligible_node_count=2`는 준비 선호에 사용할 수 있어도
전체 노드 준비 완료가 아닙니다. 이 경우 `PARTIAL`로 기록합니다.

명세·identity 기준:
[Runtime B안 계약](https://github.com/MSG-CTF/secure-provisioner/blob/619423a35876d3e823df17b812cb0b1539001c13/docs/api/image-preparation-b-contract.md),
[canonical 구현](https://github.com/MSG-CTF/secure-provisioner/blob/619423a35876d3e823df17b812cb0b1539001c13/internal/imageprep/model.go#L265-L275),
[Scheduler 조회 시각 기준](https://github.com/MSG-CTF/instance-scheduler/blob/692be04aabab0addfbce251c81c1da16b8c2c1e8/docs/image-readiness.md#L91-L111).
공식 query/response 예제는 `tests/fixtures/runtime-readiness/`에 원문으로 보관합니다.

## 실행

```bash
python3 -B -m scripts.audit_node_image_readiness \
  --artifact /absolute/path/to/artifact-v2.json \
  --readiness-response /absolute/path/to/runtime-readiness.json \
  --target-id target-a \
  --target-id target-b \
  --output-dir /absolute/path/to/new-private-audit
```

과거 증거를 재현할 때만 `--as-of 2026-10-24T00:00:30Z`처럼 실제 기준 시각을 지정합니다.
보고서는 생성 시각과 판정 기준 시각을 따로 기록합니다. 과거 기준의 성공 결과를 현재
준비 상태로 재사용하지 않습니다. 입력 시각을 수정하거나 만료를 연장하지 않습니다.

새 출력 디렉터리에 `readiness-audit.json` 하나만 만듭니다. 디렉터리는0700,
보고서는0600이며 기존 출력은 덮어쓰지 않습니다. target ID 등 운영 정보가 있으므로
공개 저장소·공개 Actions artifact에 원본 보고서를 업로드하지 않습니다.
표준 출력에는 상태·집계만 쓰고 입력 원문·env·token·오류 응답 본문은 출력하지 않습니다.
파일 크기는 각1MiB, 이미지32개·target50개까지입니다.

## 판정과 종료 코드

| 상태 | 의미 | 종료 코드 |
|---|---|---:|
| ALL_ELIGIBLE_READY | 모든 요청 target에서 ready_node_count=eligible_node_count>0이며 관측이 fresh | 0 |
| PARTIAL | 일부 target/적합 노드만 fresh READY | 1 |
| NOT_READY | 모든 요청 target이 fresh 관측됐으나 준비된 노드 없음 | 1 |
| UNKNOWN | 누락·미관측·만료·시각 오류 등으로 전체 준비를 판단할 수 없음 | 1 |
| 잘못된 입력/응답·I/O 오류 | 이미지 집합·architecture·target·개수·파일 등이 계약과 다름 | 2 |

종료1은 **대조 증거가 전체 완료를 보장하지 못한다는 뜻**입니다. 생성 API를 차단하거나
준비 요청·재시도를 실행하지 않습니다. 기존 발행 workflow의 필수 gate로 연결하지 않았으며
검사 실패로 정상 bundle을 Backend Poller가 수집하지 못하게 만들지도 않습니다.

## 증명하지 않는 것

- API의 실제 호출·응답 인증, Backend 현재 active, 노드 UID/boot generation의 독립 검증
- Backend 준비 operation 성공, 실제 Pod 생성·HTTP 접속·imageID, cold pull 소요 시간
- 새 노드 자동 준비, 운영 버전 전환·기존 인스턴스 hotfix 교체·롤백 성공
- 요청 목록 밖의 모든 운영 노드 준비와 물리 노드 UID별 중복 없는 총수

보고서의 개수는 fresh target 응답에 있는 수의 합입니다. 유일한 물리 노드 수로
취급하지 않습니다. `image_set_id`도 서명이나 실행 승인 증명이 아닙니다.
`readinessCache=miss`는 Scheduler 조회 응답 캐시의 상태이므로 이 도구의 이미지
준비 판정이나 cold pull 증거로 사용하지 않습니다.
