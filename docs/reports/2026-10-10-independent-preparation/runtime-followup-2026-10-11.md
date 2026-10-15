# Runtime 답변 반영과 다음 연동 조건

기준일: 2026-10-11 KST. 사용자가 전달한 Runtime 담당 답변을 기록합니다.
이번 기록에서 서버·정책 파일·Secret·K3s 리소스를 직접 재검증하지 않았습니다.
기존 [10월 10일 정적 점검](README.md)과 담당자가 확인한 내용을 구분합니다.

## 배포 시험의 중단 조건

| 항목 | 받은 답변 | 다음 확인 |
|---|---|---|
| 10월 7일 시간 초과 생성 요청 | 이전 GCP K3s에 접속할 수 없어 잔여 리소스 확인 불가 | Runtime·인프라가 operation/workload/Namespace와 클러스터 상태를 확인 |
| CI 인증 | GitHub Secret 등록 및 팀·Target·승인 이미지 제한 토큰 설정 기록 확인 | Tailscale SSH 재인증 후 현재 서버 설정과 Secret의 일치 여부 확인 |
| Grade Tampering 이미지 | 새 bundle은 c409e49c…44e39e, 정책은 이전 9ffbf476…0956d만 허용 | Runtime이 새 digest를 검토·정책 등록·배포 후 배포 SHA와 승인 상태 공유 |

새 Grade 이미지의 전체 발행 참조는
[기존 발행 목록](../2026-10-07-integration-readiness/published-image-references.json)에 있습니다.
확인 대상 digest는
`sha256:c409e49cf70a58be3ca19553b2db09da9d9607fd3462eaf00bdb29b20a44e39e`입니다.
이 목록은 기존 발행 스냅샷이며 이미지 정책 승인이나 실제 pull 증거가 아닙니다.

이 답변은 현재 토큰 일치나 잔여 리소스 없음까지 확인했다는 뜻이 아닙니다.
기존 이미지·무제한 토큰으로 우회하거나 정책을 임의 승인하지 않습니다.
확인 전에 새 생성 시험이나 시간 초과 요청 재실행을 하지 않습니다.
서버 인증과 정책 변경은 Runtime·인프라 담당이 진행합니다.

## 문제별 네트워크 처리

### Afterimage

Runtime 답변으로 STANDARD@v2의 동일 인스턴스 전체 통신 허용이 Compose의 내부망
분리를 재현하지 못한다는 점이 확인됐습니다.
모든 서비스가 같은 문제에 속한다는 이유로 현재 기본 정책 적용을 완료로 기록하지 않습니다.

DevSecOps·출제자가 먼저 정리할 내용:

- 반드시 허용할 출발 서비스·목적 서비스·프로토콜·목적 포트.
- 반드시 차단할 서비스 간 경로와 그 이유.
- 서비스별 공개 포트와 실제 Runtime Service DNS 연결.
- 외부 통신이 필요한 경우 대상·용도·시점.
- 요청된 제한이 유지돼야 하는 정상 동작과 의도된 풀이 경로.

이 내용은 협의 자료이며 아직 합의된 API나 info.yaml 신규 필드가 아닙니다.
Compose 네트워크 이름을 그대로 NetworkPolicy로 변환하거나 연결 관계를 확정하지 않습니다.
출제자 확인 뒤 Runtime이 문제별 허용 관계의 적용 방식을 정하고,
필요한 정책 선택 정보 또는 제한된 입력 계약과 API 예시를 공유해야 합니다.
해당 계약에 맞춰 DevSecOps는 validator와 publish bundle을 수정하고,
Backend·Scheduler는 저장·생성·reset 전달을 보존합니다.
최종 Kubernetes NetworkPolicy 생성과 통신 검증은 Runtime 담당입니다.

이전 internal_connections 제거 합의와 raw Kubernetes YAML 입력 금지는 유지합니다.
제한된 설정을 새로 지원하더라도 기존 필드를 임의 복구하지 않습니다.
DevSecOps #19의 환경변수 전달만으로 이 네트워크 분리가 해결되는 것은 아닙니다.

### Dependency Hell

Runtime 답변으로 운영용 K8s 구성이 기준이며 대회 전체가 공유하는 KOTH 서비스라는 점이
확인됐습니다. 이전 정적 점검의 개발·운영 Compose 목록은 참고 자료로만 유지합니다.

현재 필요한 운영 구성은 별도 Namespace, runner Job, 외부 DB·플랫폼 통신입니다.
일반 참가자 문제 인스턴스용 STANDARD@v2와 egress NONE만으로 운영하지 않습니다.
외부 통신을 전체 허용하거나 일반 팀별 생성·reset smoke에 넣지 않습니다.

책임자·KOTH·Runtime과 확정할 내용:

- 운영용 K8s 구성의 실제 저장소 경로와 기준 commit SHA.
- 공유 서비스의 배포·교체·복구 담당 및 생성/정리 경계.
- runner Job과 외부 DB·플랫폼의 통신 대상·인증·제한 정책.
- KOTH publish bundle과 Backend KothChallenge/release 연결 계약.
- 일반 인스턴스 공급망과 별도 배포 경로 사이에서 DevSecOps가 전달할 값과 형식.

공유 배포라고 확인됐지만 KothChallenge 릴리스 연결이나 자동 배포 계약까지
확정된 것은 아닙니다. 일반 Challenge에 중복 등록하지 않습니다.
Runtime·KOTH의 배포 로직과 원본 운영 manifest를 DevSecOps가 대신 구현하지 않습니다.

## 각 파트에 전달할 확인사항

| 담당 | 요청 | DevSecOps 후속 작업 |
|---|---|---|
| Afterimage 출제자 | 필수 허용/차단 경로와 원래 풀이 의도 확인 | 비밀값 없는 문제별 통신 요구 정리 |
| Runtime | Afterimage 추가 정책 적용 방식과 지원 입력/API 예시 | 승인된 계약만 info.yaml 검증·bundle에 반영 |
| Runtime·인프라 | 이전 리소스, 현재 제한 토큰, 새 Grade digest 승인·배포 확인 | 준비 확인 후 단일 WEB 기능 smoke |
| 책임자·KOTH·Runtime | Dependency Hell 운영 구성 및 별도 배포 담당·계약 확정 | KOTH 이미지/bundle 공급과 배포 연결 범위 정리 |
| Backend·Scheduler | 추가 정책 계약 확정 후 필드 저장·전달·reset 보존 | 실제 bundle 등록과 생성/삭제 연동 검증 |

이 문서는 요청문 준비이며 다른 저장소나 출제자에게 자동으로 메시지를 발송하지 않았습니다.
Runtime 답변과 네트워크 합의는 참가자 ZIP/GCS 저장 계약을 변경하지 않습니다.
GCS는 계속 Backend 저장 방식으로, 실제 서버 인증·bucket 권한·4종 저장/다운로드 검증이 남습니다.

## 이번에 하지 않은 작업

- 새로운 info.yaml 네트워크 필드 추가 및 출제자 파일 수정.
- Runtime 정책 코드·이미지 승인 목록·서버 인증·Tailscale 설정 변경.
- 실제 생성·삭제·reset, GCS 업로드, GHCR 발행·삭제.
- 기본 보안 정책 완화와 다른 팀 PR 병합.

로컬 검사는 문서 링크·JSON 구문·git diff --check입니다.
기존 192개 테스트와 이전 Actions 성공은 이전 커밋의 증거로 유지합니다.
이번 문서 변경의 최신 Actions 결과는 PR 코멘트에 별도로 남깁니다.
