# 노드 이미지 사전 다운로드 연동

## 목표와 현재 범위

이 저장소가 공급하는 것은 검사를 통과한 publish bundle의 **이미지 목록·출처 대조 보조 도구**입니다.
Backend 수집 버튼 연결, 준비 API 호출, 노드 작업, 준비 상태 저장은 구현하지 않습니다.
기존 수집·활성화 기능에 사전 다운로드 기능이 이미 있다고 가정하지 않습니다.

2026-10-27부터 최초 준비 범위는 **현재 운영 버전의 전체 컨테이너**, 업데이트 시에는
**승인된 새 버전의 전체 컨테이너 추가 준비**로 정리합니다.
[운영 버전 기준 정책](active-release-prefetch-policy.md)에 active 선택·기존 버전 보존과
K3s 선언 전환 기준을 기록했습니다. 이 취합 도구는 Backend active release를 조회하지
않으므로 최신 발행 목록을 현재 운영 목록으로 간주하지 않습니다.

Runtime [B안 계약 초안 PR #70](https://github.com/MSG-CTF/secure-provisioner/pull/70)을
기준으로 목록 계약을 만들었으며, 실제 준비 구현은
[Runtime PR #80](https://github.com/MSG-CTF/secure-provisioner/pull/80)에서 진행합니다.
단일 WEB의 실제 다운로드·실행 자료와 전체 운영 배포는 구분합니다. 준비 API의
운영 배포 SHA·전용 인증·허용 target·용량이 확인된 범위에서만 연결합니다.

B안에서 Backend는 승인된 release의 준비 요청·진행 추적을, Runtime은 실제
다운로드·관측·재시도를, Scheduler는 Broker 후보를 받은 뒤 준비 상태 일괄 조회와
준비된 target 우선순위를 담당합니다. Broker 후보·예약 API는 변경하지 않습니다.
DevSecOps는 기존 bundle과 보조 목록을 공급하며 노드 agent나 준비 API를 만들지 않습니다.

기존 생성 경로의 준비 상태는 성능 선호 조건입니다. 준비 실패·미관측·만료·조회
장애 시 기존 생성·pull 경로를 유지하되 실제 인증·digest 승인·격리·플랫폼·자원
검사는 필수입니다. 이와 별도로 Backend의 선택적 **준비 후 자동 활성화**는 현재
준비 확인 전까지 이전 active를 유지하는 계약이며, 기존 생성 fallback과 혼동하지 않습니다.

## 수집과 적용 흐름

```text
문제 main 발행 성공
  -> GHCR digest 이미지 + publish bundle
  -> 관리자 수집 또는 Backend Poller
  -> 출처 검증과 새 release 등록 (기존 active 유지)
  -> Backend가 Runtime에 승인된 release의 준비 작업 요청 [운영 설정·연동 검증 필요]
  -> Runtime이 노드별 다운로드·전체 이미지 검증·관측 [전체 운영 대상 검증 필요]

관리자 active 전환 또는 별도 승인한 준비 후 전환 (등록만으로 전환하지 않음)
  -> Backend가 선택된 release의 실행 정보를 Scheduler에 전달
  -> Broker 후보 조회와 기존 예약 경로 유지
  -> Scheduler가 Runtime 준비 상태를 조회해 같은 위험도 안에서 준비 target 선호
  -> Runtime이 필수 실행 조건을 검사한 뒤 준비 노드 선호·IfNotPresent로 생성
  -> 미준비·관측 만료·조회 실패는 기존 생성·필요 시 pull 경로로 진행
```

수집 자체를 이미지 실행이나 자동 활성화로 해석하지 않습니다. 자동 다운로드는
실제 배포된 연동과 승인 범위로 수집에 연결하며, 참가자 문제 인스턴스를 미리 전부 생성하는
기능이 아닙니다. 파일 생성이나 작업 접수만으로 준비 완료를 표시하지 않습니다.

## B안 요청과 보조 목록의 구분

| 정보 | 원본과 담당 |
|---|---|
| 전체 컨테이너의 name·digest·ports | DevSecOps의 원본 `artifact-v2.json`을 Backend가 검증해 사용 |
| architecture·isolation_profile | 원본 bundle에서 보존. 보조 목록이 실행 사양을 대체하지 않음 |
| release_id | Backend에서 등록된 release의 식별자. CI가 UUID를 추측·발급하지 않음 |
| request_id·target_ids | Backend가 영속 요청·운영 승인 범위에서 공급. 노드명으로 추측하지 않음 |
| operation_id·image_set_id | Runtime 준비 API의 접수 응답. CI 파일 hash와 구분 |
| 노드별 현재 준비 상태·관측 시각·만료 | 실제 실행 CRI와 승인 정책을 관측하는 Runtime의 정보 |

`plan.json`은 준비 API에 그대로 POST할 요청이 아닙니다. 의도적으로 name·image만
담으며 ports·isolation_profile·release_id·target_ids·인증·실행 설정은 담지 않습니다.
Backend는 이미 갖고 있는 **원본 bundle의 전체 실행 사양**과 자기 release·운영
범위로 요청을 구성합니다. 이 보조 파일을 기다려야만 Backend 준비 구현을 시작할
수 있는 것은 아닙니다.

전체 취합의 `images-amd64.txt` 등은 여러 문제를 합친 관리·대조 목록입니다.
한 release의 전체 이미지 집합과 같지 않으며 이를 하나의 release 준비 요청이나
readiness 조회로 무조건 보내지 않습니다. 실제 요청은 release·architecture별로
구분하고 보조 컨테이너도 빠짐없이 포함합니다.

`artifact_sha256`은 원본 JSON 파일 hash이고 `image_list.sha256`은 줄 단위 목록의
checksum입니다. #70의 `image_set_id`는 architecture와 정렬·중복 제거한 전체
이미지 참조 집합에서 Runtime이 계산하는 별도 식별자입니다. 서로 대체하지 않습니다.
이번 PR은 제안 단계의 API 요청 생성·hash 계산·HTTP 호출을 추가하지 않습니다.

### 현재 준비 상태는 파일 목록이 아님

B안의 `ready=true`는 적합한 **같은 노드 한 대 이상**에 요청 플랫폼의 전체 이미지가
실제 실행 CRI에서 사용 가능하고, 현재 Runtime 승인 정책과 유효한 관측을 만족함을
뜻합니다. 서로 다른 노드의 이미지 보유를 합산하지 않으며 별도 Docker daemon의
cache도 대신 세지 않습니다. 모든 Pod를 한 노드에 강제 배치하라는 뜻도 아닙니다.

작업 이력의 SUCCEEDED와 현재 readiness는 다릅니다. `observed_at`·`valid_until`은
Runtime의 실제 관측 근거이며 CI 목록 생성 시각이나 조회 시각으로 만들거나 연장하지
않습니다. 관측 만료·캐시 삭제·노드 교체 후에는 과거 성공만으로 준비됐다고 표시하지
않습니다. `plan_only: true` 목록에는 이 준비 상태를 발급하는 필드가 없습니다.

실제 준비 요청은 Backend [#139](https://github.com/MSG-CTF/msg-backend/issues/139),
Runtime 구현은 [#69](https://github.com/MSG-CTF/secure-provisioner/issues/69),
Scheduler 연동은 [#75](https://github.com/MSG-CTF/instance-scheduler/issues/75),
Broker 매핑 확인은 [#8](https://github.com/MSG-CTF/resource-broker/issues/8)에서 추적합니다.
Backend의 관리자 GitHub 발행 요청·실행 추적 PR #171은 이 준비 작업과 별개입니다.

## DevSecOps 발행 자료

`artifact-v2.json`의 기존 JSON과 `info.yaml` 형식은 바꾸지 않습니다. main의 성공한
일반 `KUBERNETES` 문제 발행에 다음 보조 파일을 함께 업로드합니다.

```text
<challenge_slug>-<artifact_scope>-publish-bundle/
├── artifact-v2.json
├── registry-publish.json
└── node-prefetch/
    ├── plan.json
    └── images.txt
```

`plan.json`에는 `plan_only: true`, 문제 slug, revision, source ref/SHA,
아키텍처, 컨테이너별 digest reference와 원본 artifact 및 목록의 SHA-256이
들어갑니다. 다운로드 성공이나 Runtime 이미지 승인 상태를 뜻하지 않습니다.
환경변수, FLAG, 인증 토큰이나 실행 명령은 담지 않습니다.

`images.txt`에는 공개 여부와 관계없이 해당 문제의 **모든 컨테이너** 이미지를
한 줄에 하나씩 기록합니다. 다른 문제·다른 컨테이너 경로, tag-only reference,
`latest`, 검사 실패 또는 컨테이너별 증거 불일치는 거절합니다.

KOTH와 VM은 이번 실행 범위에서 제외하며 보조 목록을 만들지 않습니다. 정적
문제는 기존대로 이미지 발행 자체가 없습니다. PWN 목록 생성은 실행 승인이
아니며 Runtime의 격리 조건을 별도로 만족해야 합니다.

기존 성공 bundle에서도 목록을 만들 수 있습니다.

```bash
python3 scripts/generate_node_image_plan.py \
  --artifact /absolute/path/to/artifact-v2.json \
  --output-dir /absolute/path/to/new-node-prefetch
```

기존 출력 디렉터리는 덮어쓰지 않습니다. 이 도구는 네트워크 호출이나 이미지
다운로드를 하지 않습니다. 원본 파일 hash는 파일 연결 확인용이지 신뢰를
발급하는 서명이 아닙니다. 소비자는 기존 Backend 출처 검사대로 성공 workflow,
공식 main, 저장소, run/artifact와 commit을 검증하고, 검증한 원본에서 목록을
다시 계산·대조해야 합니다. `plan_only`를 지우거나 보조 JSON을 수정해도 실행
승인으로 인정하지 않습니다.

## 전체 목록과 업데이트 변경분

`scripts/collect_node_image_plans.py`는 현재 main 문제 전체와 성공 발행본을 새로
대조한 뒤 일반 동적 문제의 원본 `artifact-v2.json`을 가져옵니다. 저장소·공식
workflow·main·성공 여부·run·revision·commit과 문제 폴더 일치, 전체 컨테이너
검사 증거를 확인하고 기존 문제별 생성기를 재사용합니다.

출력 예:

```text
node-prefetch/
├── prefetch-inventory.json
├── changes.json
├── images-amd64.txt
├── images-arm64.txt  # 해당 아키텍처가 있을 때만 생성
└── summary.md
```

아키텍처별 목록은 서로 섞지 않습니다. 전체 대상 중 하나라도 조회·출처·검사에
실패하면 이미지 목록과 완료 inventory는 발행하지 않습니다. 대신 실패 문제와
고정된 오류 분류를 담은 `failure-report.json`, `summary.md`만 남기고 종료 코드
2로 실패합니다. API 응답 본문이나 인증 원문을 오류 보고서에 복사하지 않습니다.
파일 저장도 임시 디렉터리에 완료한 뒤 이동하므로 중간 저장 실패를 완료로
취급하지 않습니다. 취합 도중 main이 바뀌어도 실패합니다.

이는 **목록의 완전성·출처 검증**에서 실패한 것이지 Runtime이 관측한 미준비나
다운로드 실패 상태가 아닙니다. 불완전한 목록을 완료로 표시하지 않는 검사와,
준비 정보 장애 시 기존 생성으로 진행하는 B안의 성능 fallback을 혼동하지 않습니다.

```bash
python3 -B -m scripts.collect_node_image_plans \
  --output-dir /absolute/path/to/new-node-prefetch

python3 -B -m scripts.collect_node_image_plans \
  --previous-plan /absolute/path/to/previous/prefetch-inventory.json \
  --output-dir /absolute/path/to/next-node-prefetch
```

`changes.json`은 문제·컨테이너 단위의 신규, digest/아키텍처 변경, 유지와
현재 목록에서 제외된 항목을 구분합니다. 최초 취합은 비교 기준 없음으로
표시합니다. 지정한 이전 파일이 없거나 손상됐으면 최초 취합으로 대체하지
않고 실패합니다. 이전 목록의 문제·컨테이너 경로와 checksum도 검증합니다.
**현재 목록 제외는 삭제 승인이 아닙니다.** 이전 이미지의 실행·롤백·적용 대기
여부는 별도로 보호해야 하며 `deletion_authorized`는 항상 `false`입니다.

### Actions 연결

새 reusable workflow는 `.github/workflows/node-image-prefetch-plan.yml`입니다.
문제 저장소에서 `.github/workflows/node-image-prefetch.yml`이라는 수동 caller로
호출하는 예시는 [caller 예시](node-image-prefetch-caller-example.yml)에 있습니다.
두 SHA placeholder는 리뷰·병합된 동일한 실제 commit으로 교체해야 합니다.
실제 문제 저장소의 caller는 [PR #101](https://github.com/MSG-CTF/2026_MSG_CTF/pull/101)로
적용됐습니다. 목록 caller 성공은 노드 다운로드 완료나 Backend active 조회 성공이 아닙니다.

공식 문제 저장소의 수동 main 호출만 허용하고, source 저장소 자신의
`GITHUB_TOKEN`에 `contents: read`, `actions: read`만 사용합니다. 별도 PAT,
Backend 서비스 토큰, Runtime 토큰이나 SSH 권한을 추가하지 않습니다.
실행 commit과 조회한 main이 다르면 실패합니다. Summary와 90일 보관 artifact를
남기며, 실패한 실행에는 실패 보고서만 보관합니다.

다음 호출에서 `previous_artifact_id`로 이전 성공 취합 artifact를 지정할 수 있습니다.
이전 artifact도 동일 저장소·공식 caller·main 성공 실행인지 확인합니다. 로컬
이전 JSON 파일은 구조·checksum 검사만 수행하므로 승인된 원본을 직접 선택해야
하며, 파일 자체를 서명된 신뢰 근거로 사용하지 않습니다.

## 실제 노드 저장 방식

실제 실행용 K3s CRI에서 pull·inspect하고 캐시를 관측하는 경로는 Runtime 담당입니다.
VM의 별도 Docker daemon이나 다른 containerd namespace에 받은 것만으로 실행
준비를 판정하지 않습니다. 실제 노드·K3s 버전·GHCR 인증과 Runtime 정책은 구현
담당자가 확인합니다. 이 저장소에서 CRI client·privileged worker를 추가하지 않습니다.

- [K3s 이미지 가져오기 공식 문서](https://docs.k3s.io/add-ons/import-images)
- [K3s private registry 인증](https://docs.k3s.io/installation/private-registry)

공식 문서는 구현 참고 자료이지 CI에 노드 경로 쓰기 권한을 부여하는 계약이 아닙니다. Pod의
`imagePullSecrets`만으로 노드 사전 다운로드 인증이 된다고 가정하지 않습니다.
CI에 SSH·root 권한, kubeconfig 또는 GHCR pull 토큰을 새로 전달하지 않습니다.

## 업데이트와 기존 인스턴스 유지

1. digest A가 실행 중이어도 새 digest B는 별도 release로 등록합니다.
2. B의 사전 준비를 비동기로 요청할 수 있으며 결과를 별도 표시합니다.
3. 관리자가 B를 적용하면 새로 생성하는 인스턴스만 B를 참조합니다.
4. 기존 인스턴스와 reset은 원래 release 계약을 유지합니다. 강제 재시작하지 않습니다.
5. A는 실행 중 인스턴스와 승인된 롤백이 참조하는 동안 삭제하지 않습니다.

준비 후 자동 전환을 사용하는 경우에는 준비 실패 시 이전 active를 유지합니다.
이 전환 기능은 Backend PR #178의 별도 리뷰·배포·활성화가 필요합니다.
기존 생성의 pull fallback을 변경하지 않으며 캐시 여부와 무관하게 실행 보안 조건을 검사합니다.

이 방식은 기존 참가자 세션을 유지하는 버전 전환입니다. 이미 실행 중인
인스턴스까지 새 이미지로 실시간 교체하는 무중단 배포를 보장하지 않습니다.
그 요구는 상태·스토리지, TCP 세션, readiness와 트래픽 전환 계약을 별도로
정한 뒤 다뤄야 합니다. 사전 다운로드만으로 해결되지 않습니다.

## 담당별 후속 연결

| 담당 | 추가할 작업 |
|---|---|
| DevSecOps | 기존 전체 bundle와 보조 대조 목록 공급, digest·아키텍처·출처 대조, 단일 문제 연동 증거 |
| Backend | 승인 release별 준비 요청·진행 추적·명시적 재시도, 승인 target 범위 공급, 기존 active·인스턴스 보존 |
| Runtime·노드 담당 | 실제 CRI 다운로드·검증·관측과 준비 API, 권한·정책·디스크·재시도·캐시 상태 처리 |
| Scheduler | Broker 후보 조회 후 Runtime 준비 상태 일괄 조회, 준비 target 선호, 장애 시 기존 예약·생성 흐름 유지 |
| Broker | 기존 후보·예약 API 유지, 후보 target과 Runtime Registry 매핑 확인 |

다음은 각 담당 구현의 실제 배포·설정·통합 검증을 확인할 항목입니다. 다른 팀의 API나 privileged
에이전트를 DevSecOps 저장소에서 임의로 만들지 않습니다.

- 제안된 준비·조회·retry API와 Backend 전용 인증 권한. CI smoke 토큰을 준비 권한으로 재사용하지 않음
- Backend의 승인 target 공급 경로와 Broker target·Runtime Registry 매핑
- Runtime의 같은 노드 전체 이미지 확인, 실제 관측·만료, 노드 UID·캐시 교체 처리
- 안정적인 request_id·정규화 본문으로 동일 준비 요청 복구, 실패 작업은 새 요청 ID의 child retry로 추적
- node UID·boot/cache generation·실행 CRI·플랫폼·resolved digest와 현재 승인 정책을 구분
- 부분 실패·디스크 부족·인증/정책 오류와 일시 registry 오류의 재시도 분류
- 새 노드 초기 관측, 동시 다운로드 한도·디스크 기준과 실제 pull 성능 검증
- 제안 API·feature flag가 실제로 지원되는 배포 SHA 확인 후 시범 대상에서만 활성화

문제 전체 이미지를 미리 받더라도 모든 과거 GHCR 버전을 받지 않습니다.
대상은 일반 동적 문제의 승인된 현재 release, 새로 수집해 사전 다운로드·적용을
준비 중인 승인된 release와 별도로 승인한 롤백 버전입니다.
최신판이라는 tag를 노드에서 해석하지 않고 정확한 digest 목록을 사용합니다.
다운로드 작업 중이거나 다운로드 후 적용 대기 중인 digest도 GHCR 정리 보호
목록에 포함해야 합니다. 노드 캐시가 있다는 이유로 GHCR 원본을 지우지 않습니다.

## 검증 순서

1. #70 계약 합의와 Runtime 실제 구현·배포를 확인하고 기본 비활성 상태를 유지합니다.
2. 승인된 단일 WEB의 캐시 미보유 상태를 확인한 뒤 Backend 준비 요청·노드 pull·관측·시간을 기록합니다.
3. 같은 노드의 전체 이미지·플랫폼·현재 정책과 유효 관측을 대조합니다. 관리자 적용은 별도 동작입니다.
4. 생성·실제 HTTP 접속·실행 imageID·삭제를 확인합니다.
5. 캐시가 있는 상태의 생성 시간과 비교합니다. 전체 생성 시간을 pull 시간으로 기록하지 않습니다.
6. 새 revision을 수집할 때 기존 active와 실행 인스턴스가 유지되는지 확인합니다.
7. 인증 실패·디스크 부족·부분 실패·새 노드에서도 거짓 준비 완료가 나오지 않는지 확인합니다.
8. 미준비·만료·준비 조회 장애 시 기존 생성·pull 경로를 유지하고, 실제 보안 거절은 유지되는지 확인합니다.

2026-10-27 수령한 Runtime 시범 자료에서는 단일 WEB의 실제 pull 3.786초,
Pod Ready·imageID 일치·캐시 재사용·시험 리소스 정리를 확인했습니다.
전체 현재 운영 버전의 일괄 준비, Backend·Scheduler 운영 설정 설치와 자동 전환은
이 시범으로 검증됐다고 계산하지 않습니다. 기존 Open House 생성·삭제 기록도
cold pull이나 새 자동화 검증으로 재사용하지 않습니다.

## 기존 목록 검증 기록

- 전체 로컬 단위 테스트 286개 통과
- 기존 Open House main 발행 run `37349840954`, revision `461`의 실제
  `artifact-v2.json`으로 이미지 목록 생성 확인
- 출력의 이미지가 원본 bundle의 정확한 digest와 일치하고 원본 파일 hash가 보존됨
- 실제 workflow의 목록 생성 셸 실행과 기존 Poller의 파일 선택 방식 호환 확인
- 실제 일반 동적 문제 18개 중 K3s 지원 15개·컨테이너 이미지 22개 취합
- 당시 `misc-reqr`, `pwn-ghost-file`, `pwn-random6`는 `DOCKER` 선언이어서 별도 분류함.
  2026-10-27 K3s 전환 결정 이후에도 문제 저장소 변경과 새 bundle 발행 전까지 과거 목록은 그대로 보존
- 전체 일반 문제 30개와 정적 12개, KOTH·Windows 제외를 구분해 보고

위 결과는 기존 PR 검증 당시의 기록입니다. 현재 전체 문제·노드 상태를 다시
조회하거나 실제 다운로드한 결과로 재표기하지 않습니다. 최신 main 병합 후의
회귀 테스트와 CI는 PR 본문에 별도 기록합니다.

이후 중앙 PR #26과 문제 저장소 PR #101이 병합됐고, 실제 수동 main 취합 run
`40333744581` 및 이전 artifact를 사용한 재취합 run `40334270971`이 성공했습니다.
당시 일반 K3s 문제 15개·이미지 22개를 대조했으며 추가·변경·제외는 0개였습니다.
이는 발행 목록 검증이며 Backend active 선택이나 현재 전체 노드 준비 완료는 아닙니다.

이 결과는 목록 생성 검증입니다. 실제 Backend 수집, 노드 다운로드, 캐시 hit,
Runtime HTTP 접속이나 무중단 교체 성공을 의미하지 않습니다.
PR 병합 후 문제 저장소가 참조하는 reusable workflow와 `devsecops_ref`를 같은
병합 SHA로 갱신해야 새 발행에 이 목록이 포함됩니다. 기존 bundle은 자동 변경되지 않습니다.
