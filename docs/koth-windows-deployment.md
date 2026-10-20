# KOTH·Windows 배포 연동

2026-10-19 회의 전달 내용을 기준으로 실행 방향과 미확정 계약을 구분합니다.
이 문서는 새로운 Backend·Runtime API나 운영 배포 승인을 정의하지 않습니다.

## 방향과 남은 결정

| 항목 | 전달받은 방향 | 아직 확인할 내용 |
|---|---|---|
| KOTH 자원 | Broker와 협의해 여러 서버에 배치 | 문제별 자원·복제 수·동시 운영 또는 대기 여부 |
| KOTH 배포 | GitHub에서 승인한 버전을 K3s에 배포 | 배포 대상 등록·승인 담당과 수동/자동 실행 계약 |
| KOTH 복구 | SLA가 장애를 감지해 복구 경로로 연결 | 복구 실행 주체·중복 방지·데이터 보존·롤백 기준 |
| Windows | Backend 제출 접수 후 약 20개 실행 환경에서 처리 | 실행 환경 형식·작업 API·5~10초의 적용 범위·초기화 기준 |

자원 배치는 KothChallenge와 release 연결 문제를 대체하지 않습니다. 어떤 문제의
어떤 revision·digest를 어느 대상으로 배포했는지 추적할 수 있어야 합니다.
일반 Challenge에 KOTH를 임시 중복 등록하지 않습니다.

## 현재 선언 자원

기준은 문제 main `25e7c6b636ba11b16c77e09274563fe92fbb9003`의 info.yaml입니다.
측정 사용량이나 서버 배치 가능 판정이 아니라 문제 전체의 합산 선언값입니다.

| 문제 | 컨테이너 수 | CPU(m) | 메모리(MiB) | 임시 저장소(MiB) |
|---|---:|---:|---:|---:|
| koth-card-battle-arena | 1 | 500 | 512 | 1024 |
| koth-dependency-hell | 4 | 5500 | 3072 | 4096 |
| koth-grand-tour-duel | 1 | 6000 | 1536 | 2048 |
| koth-jenga | 1 | 300 | 256 | 512 |
| koth-pixel-smuggler | 1 | 1000 | 1024 | 1024 |
| koth-swanopoly | 4 | 6000 | 4096 | 2048 |

6개 세트를 각각 한 번 실행하는 선언 합계는 CPU 19300m, 메모리 10496MiB,
임시 저장소 10752MiB입니다. 복제본·K3s·운영체제·여유 자원은 포함하지 않았습니다.
6코어 선언은 Grand Tour Duel과 Swanopoly 두 개입니다. Dependency Hell도 5.5코어입니다.
CI는 이 값을 임의로 줄이거나 컨테이너별로 나누지 않습니다.

Broker는 가용량과 예약 가능 여부를 확인하고, Runtime은 실제 컨테이너별 배분·실행을
담당합니다. 단일 노드 K3s 여러 개와 하나의 멀티 노드 클러스터는 배치 방식이 다르므로
서버별 target_id와 토폴로지를 먼저 확인해야 합니다.

## DevSecOps 책임

1. 승인된 commit을 기존 파이프라인으로 검사하고 통과한 이미지만 GHCR에 발행합니다.
2. 전체 컨테이너의 digest, registry_revision, 자원과 지원 실행 설정을 bundle에 보존합니다.
3. 배포 계약이 확정되면 실제 담당자의 배포 기능을 호출하고 실행 근거를 남깁니다.
4. 재배포는 승인한 같은 digest, 롤백은 승인한 이전 release를 사용하도록 검증합니다.
5. 배포·복구·롤백 대상 digest가 GHCR 정리 보호 목록에 포함되는지 확인합니다.

KOTH용 API·Scheduler·복구 엔진·Windows 작업 풀을 이 저장소에서 대신 구현하지 않습니다.
NetworkPolicy manifest를 출제자에게 받거나 제거한 internal_connections를 다시 넣지 않습니다.
운영 데이터를 지울 수 있는 자동 재생성도 계약 전에는 켜지 않습니다.

## KOTH 확인 요청

- Backend·KOTH 담당: KothChallenge 식별자와 challenge_slug·revision 연결 및 배포 버전 기록 방식
- Broker: 문제별 후보 target_id, 가용 자원, 6코어 문제 배치, 복제본 수와 대기 방식
- Runtime: 컨테이너별 자원·UID·쓰기 경로·Secret·readiness·공개 포트·네트워크 지원
- SLA·운영 담당: 감지 신호, 실제 복구 호출 대상, 중복 복구 방지, 재시도 상한과 수동 개입
- KOTH 출제자: 보존할 점수·DB·파일, 초기화 허용 범위와 정상 응답 기준

Dependency Hell은 공유 서비스와 외부 의존성이 있는 별도 검토 대상입니다.
일반 문제의 STANDARD@v2·egress NONE을 그대로 적용해 운영 가능하다고 기록하지 않습니다.

## Windows 확인 요청

20개 실행 환경과 5~10초는 전달받은 운영 방향이며 아직 성능 검증된 수치가 아닙니다.
아래 계약 전에는 참가자 제출 코드를 GitHub Actions에서 실행하지 않습니다.

- Backend: 제출 형식·문제 식별자·작업 ID·상태·결과·중복 제출/재시도 계약
- Broker·실행 담당: Windows VM/컨테이너 여부, 운영체제 버전과 동시 실행 환경 수
- Runtime 또는 별도 실행 담당: CPU·메모리·프로세스·네트워크 제한, 시간 초과 시 전체 작업 종료
- 실행 담당: 5~10초가 코드 실행 시간인지 생성·대기·정리를 포함하는지
- 실행 담당: 매 제출 후 환경 초기화 검증, 초기화 실패 환경 격리와 교체
- DevSecOps: 확정된 실행 환경의 빌드·검사·불변 버전 식별·승인 배포 경로

프로세스만 종료하고 다음 제출을 받는 것은 깨끗한 실행 환경 복원을 입증하지 않습니다.
일반 VM과 Windows 컨테이너는 다른 배포물입니다. VM 이미지를 OCI 컨테이너처럼
GHCR에 저장한다고 가정하지 않습니다.

K3s는 현재 Windows를 네이티브 지원하지 않습니다. Linux 서버에 K3s를 설치하는
작업과 Windows 실행 환경 준비를 분리합니다.
[K3s 공식 FAQ](https://docs.k3s.io/faq#does-k3s-support-windows)

## 확인 순서와 완료 기준

1. 위 담당별 계약과 운영 승인자를 확정합니다.
2. KOTH 한 문제로 승인 digest 배포·접속·상태 보존·장애 감지·복구·롤백을 확인합니다.
3. Windows 대표 제출로 정상·실패·시간 초과·초기화·재시도·동시 실행을 확인합니다.
4. 확정한 운영 기록 형식과 실제 담당 API에 맞춰 DevSecOps 배포 호출을 PR로 추가합니다.
5. 실제 run·revision·digest 또는 VM 버전·target·정책 버전·결과를 남긴 뒤 전체 적용합니다.

현재 report의 review_required는 협업 확인 목록일 뿐 새 CI 차단 정책이 아닙니다.
빌드 성공·GHCR 발행·일반 WEB smoke를 KOTH 복구 또는 Windows 실행 완료로 계산하지 않습니다.
