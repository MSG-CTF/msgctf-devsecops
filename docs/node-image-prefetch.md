# 노드 이미지 사전 다운로드 연동

## 목표와 현재 범위

관리자가 Backend에서 문제를 수집하면 새 릴리스를 등록하고, 해당 릴리스의
이미지를 실행 가능한 K3s 노드에 미리 받는 흐름을 목표로 합니다. 이미지가
준비된 뒤 관리자가 적용하면 이후 새 인스턴스가 해당 버전을 사용합니다.

이 변경에서 구현한 것은 검사를 통과한 publish bundle에 다운로드 목록을
추가하는 부분입니다. Backend 수집 버튼 연결, 노드 작업 실행, 준비 상태 저장과
활성화 제한은 아직 구현된 기능이 아닙니다. 이 문서의 상태·처리 순서는 담당자와
합의할 연동 제안이며, 현재 Runtime API 계약이 아닙니다.

현재 확인한 Backend Poller는 등록만 수행하고, 활성화 API는 현재 release 포인터를
전환합니다. Runtime의 공개 OpenAPI에는 사전 다운로드 API가 없습니다. Broker
Node Agent는 Kubernetes 관측용이며 containerd socket이나 workload 변경 권한이
없습니다. 기존 수집 버튼이나 Node Agent에 이미 다운로드 기능이 있다고 보지 않습니다.

## 수집과 적용 흐름

```text
문제 main 발행 성공
  -> GHCR digest 이미지 + publish bundle
  -> 관리자 수집 또는 Backend Poller
  -> 출처 검증과 새 release 등록 (기존 active 유지)
  -> 승인된 실행 노드별 사전 다운로드 작업 요청 [추가 연동 필요]
  -> 노드 아키텍처와 전체 컨테이너 digest 확인 [추가 연동 필요]
  -> 노드별 준비 완료 기록 [추가 연동 필요]
  -> 관리자가 적용: 준비된 release만 active 전환 [추가 연동 필요]
  -> 새 인스턴스는 해당 release와 노드 캐시 사용
```

수집 자체를 이미지 실행이나 자동 활성화로 해석하지 않습니다. 자동 다운로드는
위 연동 구현 후 수집에 연결하며, 참가자 문제 인스턴스를 미리 전부 생성하는
기능이 아닙니다. 파일 생성이나 작업 접수만으로 준비 완료를 표시하지 않습니다.

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
이번 PR은 예시만 제공하며 실제 문제 저장소의 caller를 수정하지 않습니다.

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

K3s의 실행 이미지는 노드의 containerd 저장소에 들어가야 합니다. VM에서 별도
Docker daemon으로 `docker pull`한 것만으로 K3s의 이미지 준비를 판정하지 않습니다.
K3s는 `/var/lib/rancher/k3s/agent/images` 아래에 한 줄당 이미지 하나인 텍스트
파일을 놓거나 갱신하면 CRI로 사전 다운로드하는 기능을 제공합니다.
실제 배포 버전의 지원 여부와 GHCR 인증을 먼저 확인해야 합니다.

- [K3s 이미지 가져오기 공식 문서](https://docs.k3s.io/add-ons/import-images)
- [K3s private registry 인증](https://docs.k3s.io/installation/private-registry)

이는 사용할 수 있는 노드 내부 구현 방식이지 CI가 직접 해당 경로에 쓰도록
허용한 것이 아닙니다. 노드 담당자가 작업 실행 경로를 정해야 합니다. Pod의
`imagePullSecrets`만으로 노드 사전 다운로드 인증이 된다고 가정하지 않습니다.
CI에 SSH·root 권한, kubeconfig 또는 GHCR pull 토큰을 새로 전달하지 않습니다.

## 업데이트와 기존 인스턴스 유지

1. digest A가 실행 중이어도 새 digest B는 별도 release로 등록합니다.
2. B를 허용된 노드에 먼저 받고 전체 컨테이너를 확인합니다.
3. 관리자가 B를 적용하면 새로 생성하는 인스턴스만 B를 참조합니다.
4. 기존 인스턴스와 reset은 원래 release 계약을 유지합니다. 강제 재시작하지 않습니다.
5. A는 실행 중 인스턴스와 승인된 롤백이 참조하는 동안 삭제하지 않습니다.

이 방식은 기존 참가자 세션을 유지하는 버전 전환입니다. 이미 실행 중인
인스턴스까지 새 이미지로 실시간 교체하는 무중단 배포를 보장하지 않습니다.
그 요구는 상태·스토리지, TCP 세션, readiness와 트래픽 전환 계약을 별도로
정한 뒤 다뤄야 합니다. 사전 다운로드만으로 해결되지 않습니다.

## 담당별 후속 연결

| 담당 | 추가할 작업 |
|---|---|
| DevSecOps | 이번 보조 목록 발행, digest·아키텍처·출처 대조, 승인된 단일 문제 연동 증거 |
| Backend | 수집 후 release별 작업 접수, 상태 조회, 준비되지 않은 release 적용 차단, 기존 active 보존 |
| Runtime·노드 담당 | 노드별 containerd 다운로드와 실제 digest 확인, 인증·디스크·재시도·캐시 상태 처리 |
| Broker | 실행 가능한 target·노드·아키텍처 목록 제공, 새 노드와 준비 실패 노드의 후보 처리 합의 |

아래 항목을 합의한 뒤 호출 코드를 연결합니다. 다른 팀의 API나 privileged
에이전트를 DevSecOps 저장소에서 임의로 만들지 않습니다.

- 사전 다운로드 실행 주체와 요청·조회 인터페이스, 인증 방법
- 대상 target/node 목록의 공급자와 갱신 주기
- 아키텍처별 승인된 실행 노드 전체 준비를 적용 조건으로 사용할지
- 노드가 일부 실패했을 때 적용을 보류할지, 준비 노드에만 한정할지
- 새 노드·재생성 노드의 초기 동기화와 캐시 삭제 후 재확인
- 작업 중복 키: release 식별자 + target/node 식별자 + image digest
- 반환 정보: 작업 식별자, node, 요청 image, 실제 digest/아키텍처,
  관측 시각, 성공·실패, 소요 시간, 재시도 가능 여부
- 동시 다운로드 제한, 디스크 여유 기준과 중단·재시도 기준
- 노드 캐시가 정리됐을 때 준비 상태를 다시 확인하고, Runtime의 실제
  imagePullPolicy와 GHCR 인증 동작을 함께 검증하는 기준

문제 전체 이미지를 미리 받더라도 모든 과거 GHCR 버전을 받지 않습니다.
대상은 일반 동적 문제의 승인된 현재 release, 새로 수집해 사전 다운로드·적용을
준비 중인 승인된 release와 별도로 승인한 롤백 버전입니다.
최신판이라는 tag를 노드에서 해석하지 않고 정확한 digest 목록을 사용합니다.
다운로드 작업 중이거나 다운로드 후 적용 대기 중인 digest도 GHCR 정리 보호
목록에 포함해야 합니다. 노드 캐시가 있다는 이유로 GHCR 원본을 지우지 않습니다.

## 검증 순서

1. 승인된 단일 WEB의 노드 이미지 미보유 상태를 먼저 확인합니다.
2. 수집으로 사전 다운로드를 요청하고 요청 전후 캐시·pull 증거·시간을 기록합니다.
3. 모든 컨테이너의 digest와 아키텍처를 확인한 뒤 적용합니다.
4. 생성·실제 HTTP 접속·실행 imageID·삭제를 확인합니다.
5. 캐시가 있는 상태의 생성 시간과 비교합니다. 전체 생성 시간을 pull 시간으로 기록하지 않습니다.
6. 새 revision을 수집할 때 기존 active와 실행 인스턴스가 유지되는지 확인합니다.
7. 인증 실패·디스크 부족·부분 실패·새 노드에서도 거짓 준비 완료가 나오지 않는지 확인합니다.

현재는 위 노드 다운로드·자동 적용 연동을 수행한 상태가 아닙니다. 기존
Open House 생성·삭제 성공 기록은 cold pull이나 이번 자동화 검증으로 재사용하지 않습니다.

## 이번 변경의 확인 결과

- 전체 로컬 단위 테스트 286개 통과
- 기존 Open House main 발행 run `37349840954`, revision `461`의 실제
  `artifact-v2.json`으로 이미지 목록 생성 확인
- 출력의 이미지가 원본 bundle의 정확한 digest와 일치하고 원본 파일 hash가 보존됨
- 실제 workflow의 목록 생성 셸 실행과 기존 Poller의 파일 선택 방식 호환 확인
- 실제 일반 동적 문제 18개 중 K3s 지원 15개·컨테이너 이미지 22개 취합
- `misc-reqr`, `pwn-ghost-file`, `pwn-random6`는 현재 `DOCKER` 선언이므로
  K3s 목록에서 별도 분류하며 실행 방식을 임의로 바꾸지 않음
- 전체 일반 문제 30개와 정적 12개, KOTH·Windows 제외를 구분해 보고

새 취합 workflow는 reusable 코드와 caller 예시만 준비한 상태입니다. 실제 문제
저장소의 수동 caller 적용과 해당 경로의 Actions 실행은 리뷰·병합 후 진행합니다.
PR 자체 CI와 로컬 실제 bundle 취합 성공을 새 caller의 운영 실행 성공으로 기록하지 않습니다.

이 결과는 목록 생성 검증입니다. 실제 Backend 수집, 노드 다운로드, 캐시 hit,
Runtime HTTP 접속이나 무중단 교체 성공을 의미하지 않습니다.
PR 병합 후 문제 저장소가 참조하는 reusable workflow와 `devsecops_ref`를 같은
병합 SHA로 갱신해야 새 발행에 이 목록이 포함됩니다. 기존 bundle은 자동 변경되지 않습니다.
