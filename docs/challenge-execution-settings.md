# 문제 실행 설정 계약과 협업 확인

## 현재 결론

이미지 빌드·보안 검사 성공은 문제 실행 성공과 다릅니다. info.yaml에 없는
Compose 실행 설정은 publish bundle에 자동으로 포함되지 않습니다.
이번 변경은 필요한 설정을 점검하고 미지원 입력이 조용히 삭제되는 것을 막습니다.
환경변수나 네트워크 필드를 임의로 새 API에 전송하지 않습니다.

DevSecOps는 문제 사양 검증과 bundle 발행, Backend는 저장과 등록,
Scheduler는 생성·reset 전달, Runtime은 설정 적용·격리·준비 상태 판정을 담당합니다.
실제 출제자 확인과 팀 간 계약 승인은 아직 필요합니다.

## 지원 필드

| info.yaml | CI 배포 정보 | 지원 상태 / 남은 일 |
|---|---|---|
| deployment.runtime_type | runtime_type | 검증·발행 지원 |
| deployment.architecture | architecture | 검증·발행 지원 |
| deployment.containers[].name | workload.containers[].name | 검증·발행 지원 |
| build / image | workload.containers[].image | GHCR digest 고정 이미지로 발행 |
| ports / expose | workload.containers[].ports[].port/public | Runtime smoke에서는 ports/exposed_ports로 변환, expose 미전송 |
| deployment.resource_profile | resource_profile | CPU·메모리·임시 저장 용량 합산 지원 |
| deployment.healthcheck.container/port/path | workload.healthcheck | CI가 이미 보존함. Backend 릴리스 PR은 저장함. Scheduler 생성 요청과 Runtime 적용은 추가 연결 필요 |
| flag | 없음 | CI output·bundle에 값 미포함. 런타임 FLAG 주입으로 자동 변환하지 않음 |
| registry_revision | registry_revision | workflow 입력으로 지정, release 식별 및 이력 관리 |

Runtime smoke의 run_as_user 기본값은 10001입니다. 문제별 UID 지정은 현재
info.yaml 계약이 아닙니다. Runtime에 writable_paths가 있더라도 CI와 Backend를
거치는 전체 경로가 합의됐다는 뜻은 아닙니다.

현재 info.yaml의 expose는 컨테이너 단위이므로 true이면 선언된 모든 포트가
public으로 정규화됩니다. Runtime의 exposed_ports 지원과는 별개로, 같은 컨테이너의
공개/비공개 포트를 info.yaml에서 따로 지정하는 계약은 추가 합의가 필요합니다.
healthcheck나 관리자 포트를 참가자 포트와 함께 선언했다고 자동으로 비공개가 되지 않습니다.

미지원 컨테이너·healthcheck·resource_profile 필드는 이제 validator가 오류로
처리합니다. environment, env, command, volumes, networks 등을 지금 info.yaml에
추가하면 실행에 적용되지 않고 명세 검증에서 거절됩니다.
YAML 문법 오류도 원문이나 traceback 대신 고정된 안내로 출력해 비밀값 노출을 막습니다.

## 실제 문제 점검

2026-10-02 문제 저장소 main `efb2fa39f5e935224fc4be1d24bea6db5930c57a` 기준:

- 총 37개: deployment 있음 23개, 없음 14개.
- 서버 문제 중 info.yaml healthcheck 선언 7개.
- 서버 문제 중 환경변수 이름 발견 19개. 기본값·테스트 참조도 포함한 후보이며 필수 설정 수는 아님.
- 별도 네트워크 분리 검토 후보: web-afterimage, koth-dependency-hell.
- koth-jenga/docker-compose.layers.yml은 일반 YAML parser로 해석되지 않아 일부 미점검.
  Compose 오류라고 단정하지 않으며 전용 태그·파일 문법을 출제자와 확인해야 함.

전체 표는 [문제별 점검표](reports/2026-10-02-execution-settings/execution-settings.md),
컨테이너별 설정 이름은 [점검 JSON](reports/2026-10-02-execution-settings/execution-settings.json)에 있습니다.
이번 점검은 빌드·Trivy·GHCR 발행·K3s 배포를 재실행한 결과가 아닙니다.

| 우선 확인 문제 | 필요한 확인 |
|---|---|
| pwn-random6 / crypto-nerves / web-grade-tampering | FLAG 필수 여부, 환경변수 기본값, 주입 책임자 |
| web-notebook | DB_HOST와 실제 내부 주소 대응, DB 계정·비밀번호 참조, 초기화 순서 |
| web-afterimage | 여러 네트워크·서비스 연결·인증키·봇 통신이 출제 의도에 필요한지 |
| koth-dependency-hell | 서비스 역할, 네트워크 분리, 저장소·인증키·외부 플랫폼 통신; 일반 문제와 같은 배포인지 별도 확인 |
| web-daily-point / KOTH 문제 | 쓰기 경로, 크기, 임시/영구 구분, reset 데이터 삭제 범위 |

Compose 서비스명과 info.yaml 컨테이너명이 다르면 container_mapping으로 표시합니다.
checker 등 운영 보조 서비스이거나 이름 차이일 수 있으므로 자동 추가하지 않습니다.

## 출제자 확인 양식

각 운영용 컨테이너별로 다음을 확인합니다. 비밀 값은 댓글이나 보고서로 받지 않습니다.

| 항목 | 받을 내용 |
|---|---|
| 환경변수 | 이름, 필수/선택, 기본값 여부, 비밀 여부, 주입 담당자 |
| FLAG | 고정/동적 구분, 환경변수/파일 주입 중 무엇인지, 누락 시 동작 |
| 시작 명령 | 이미지 CMD/ENTRYPOINT로 충분한지, 추가 command/args가 필요한지 |
| 내부 주소 | 접속할 컨테이너·Service명·포트, Runtime이 발급하는 실제 내부 DNS와의 대응 |
| 저장소 | 컨테이너 경로, 용량, 공유 여부, 영속성, reset 초기화 기준 |
| healthcheck | 준비 완료를 확인하는 HTTP 경로·포트 또는 TCP/exec 필요 여부 |
| 네트워크 | 꼭 허용할 통신과 꼭 차단할 통신, 외부 접속 필요 여부 |

정적 문제의 참가자 파일 전달은 별도 user-files-bundle 계약을 유지합니다.
실행 환경변수나 운영 인증키는 참가자 ZIP에 넣지 않습니다.

## 합의할 실행 설정

아래는 제안이며 아직 지원되는 info.yaml 키나 Runtime API가 아닙니다.
합의 후에만 validator → publish bundle → Backend DB → Scheduler → Runtime 순서로
추가하고 버전·하위 호환성 규칙을 함께 확정합니다.

1. 일반 환경변수와 비밀 참조를 구분합니다. 이름·길이·개수·허용 변수 규칙을
   검증하며 쉘 보간이나 명령 실행은 하지 않습니다.
2. FLAG·DB 비밀번호·인증키는 원문 대신 승인된 비밀 참조를 bundle에 기록하는
   방향으로 협의합니다. 참조 발급·접근 범위·동적 값 생성·reset 처리 소유자는
   Backend/Runtime/보안팀이 정합니다. CI가 info.yaml.flag를 그대로 복사하지 않습니다.
3. healthcheck의 기존 HTTP 구조는 끝까지 보존합니다. TCP/exec, 시간 제한,
   startup/readiness 판정이 필요하면 공통 계약을 추가합니다. Runtime에 없는 키를 먼저 보내지 않습니다.
4. 쓰기 경로·용량은 제한된 storage 계약으로 정의합니다. hostPath나 임의 호스트
   마운트는 입력받지 않습니다. Compose volume을 그대로 복사하지 않습니다.
5. command/args는 필요한 문제 확인 후 지원 여부를 정합니다. 가능하면 이미지의
   CMD/ENTRYPOINT에 담고, 지원 시 쉘 문자열이 아닌 명시적 인자 배열을 사용합니다.
6. 새 bundle 등록, DB 왕복, 생성·reset 때 값/참조 보존을 검증합니다.
7. 같은 컨테이너의 포트별 공개 여부를 지정하는 입력 형식을 정합니다. Runtime의
   exposed_ports와 대응하되 기존 expose 입력의 변환·하위 호환성도 함께 확인합니다.

## 네트워크 기준

현재 기준은 Runtime STANDARD@v2, 같은 인스턴스 내부 통신 허용, 다른
인스턴스·팀 격리, 공개 포트만 외부 노출, 기본 egress NONE입니다.
CI는 raw NetworkPolicy와 Kubernetes manifest를 전달하지 않으며
internal_connections를 다시 추가하지 않습니다.

기본 정책으로 출제 의도가 유지되지 않는 문제는 필요한 허용/차단 조건을 문서로
먼저 수집합니다. 제한된 네트워크 의도 DSL의 필드·허용값·기본값·Runtime 구현을
합의하기 전에는 network_policy 같은 임의 키를 발행하지 않습니다.

현재 Runtime은 컨테이너별 Pod·Service 구조입니다. 다른 컨테이너에 접속할 때는
Runtime이 생성한 해당 Service의 내부 DNS와 포트를 사용합니다. `localhost`는
자기 Pod를 가리키므로 다른 컨테이너의 DB 주소로 안내하지 않습니다. Compose의
서비스명이 Runtime의 실제 Service 이름과 같다고 가정하지 않으며, DNS 매핑과
DB_HOST 같은 실행 설정의 지원 계약을 Runtime·Backend·Scheduler와 확인합니다.

같은 Pod 안에 여러 컨테이너를 두는 일반 Kubernetes 구성은 별도 개념입니다.
이 경우에만 IP와 포트 공간을 공유합니다. 현재 Runtime이 이 방식으로 실행한다고
안내하지 않습니다. 표준 NetworkPolicy의 격리 단위는 Pod이므로 현재 구조에서는
Pod별 정책을 적용할 수 있지만, 실제 출제 의도에 맞는 허용·차단 규칙 적용은
Runtime 담당과 확인해야 합니다.
[Kubernetes Pod 네트워크](https://kubernetes.io/docs/concepts/workloads/pods/),
[NetworkPolicy](https://kubernetes.io/docs/concepts/services-networking/network-policies/).

## 담당별 요청

| 담당 | 요청 | 완료 조건 |
|---|---|---|
| DevSecOps + 출제자 | 점검표로 필수 실행 설정과 내부 통신 의도 확인 | 출제자 확인 기록, 지원/미지원 구분 |
| Backend | healthcheck 끝까지 보존, 신규 설정/비밀 참조 저장 계약 검토 | 등록·조회·DB 왕복 보존, 생성 요청에 포함 |
| Scheduler | 생성·reset 때 같은 실행 설정과 revision 전달 | 저장 후 재조회 및 reset 요청 동일성 확인 |
| Runtime | API 필드·준비 상태 판정·secret 주입·네트워크/스토리지 계약 제시 | 설정 적용, 실제 준비 확인, 종료된 컨테이너를 RUNNING으로 처리하지 않음 |

대표 테스트는 FLAG 필요 단일 컨테이너, web+db, HTTP healthcheck, 네트워크 분리
문제로 나눕니다. 정상 생성·접속·reset·삭제와 함께 필수 설정 누락, 비밀 참조
권한 실패, healthcheck 실패를 검사합니다. 원문 비밀은 로그·증거 자료에 남기지 않습니다.

## 점검 방법

```bash
python3 scripts/audit_execution_settings.py /path/to/2026_MSG_CTF \
  --source-sha <문제_저장소_commit_SHA> \
  --output-dir execution-settings
```

단일 문제 폴더도 점검할 수 있습니다. 루트와 for_organizer의 Compose에서 설정
이름·존재 여부를 읽고, for_organizer의 일부 코드와 .env에서 환경변수 이름을
추출합니다. Compose 실행·환경변수 보간·secret 값 출력은 하지 않습니다.
for_user, exploit, 링크와 의존 패키지는 제외합니다. 1 MiB 초과 텍스트나 읽지 못한
파일은 일부 미점검으로 표시합니다. 동적 변수명·셸 스크립트 등 모든 언어를
완전하게 분석하지 않으므로 미발견을 설정 불필요로 해석하지 않습니다.

두 reusable workflow에서 검증 전에 `<artifact_scope>-execution-settings` 자료를
업로드하며 14일 보관합니다. 이는 성공한 release bundle이 아닌 진단 자료입니다.
진단 도구나 자료 업로드가 실패해도 실제 명세·Gitleaks 검증은 계속 실행되며,
명세와 보안 검사 실패는 기존처럼 CI를 차단합니다.
문제 저장소 caller의 workflow와 devsecops_ref를 함께 업데이트해야 실제 문제
Actions에도 반영됩니다. 이번 PR에서 문제 저장소는 변경하지 않습니다.

## 2026-10-05 리뷰 반영과 다음 연결

- 이번 PR은 점검과 미지원 입력 차단입니다. 환경변수 19개는 참조 후보이며
  모두 실행 실패 또는 모두 필수라는 뜻이 아닙니다. 출제자가 필수 여부를 확인해야 합니다.
- 승인·병합 후 문제 저장소의 도구 checkout, branch workflow와 devsecops_ref,
  main workflow와 devsecops_ref 총 5곳을 동일한 새 커밋 SHA로 갱신합니다.
  이미 적용된 Afterimage indexer 한정 예외도 같은 도구 버전에 포함해야 합니다.
- info.yaml 원문에는 flag가 있으므로 Runtime에 파일을 통째로 전송하지 않습니다.
  검증한 허용 필드만 bundle로 정규화하고 Backend → Scheduler → Runtime이 전달합니다.
- 네트워크는 현재 STANDARD@v2, 내부 통신 허용, 인스턴스·팀 격리, 공개 포트만
  외부 노출, egress NONE을 유지합니다. internal_connections나 raw NetworkPolicy를
  다시 추가하지 않습니다. 문제별 예외 의도 DSL은 수신·보존·적용 계약 승인 전까지 미지원입니다.
- Runtime에 확인할 내용은 필드명, 허용 값, 기본값, Service DNS 매핑, 정책 버전과
  reset 보존 규칙입니다. Backend·Scheduler는 해당 값의 저장과 끝까지 전달을 확인합니다.
- GCP Runtime의 무인증 HTTPS 연결 점검은 실제 생성·접속·reset·삭제 검증과 다릅니다.
  실제 문제 배포 성공이나 전체 Linux/Docker 실행 검증으로 기록하지 않습니다.

확인 기준:
- DevSecOps main: b39f232fc4759b70928c4960e7a17bb33264bcec
- Backend 릴리스 PR #26: fb9d0df3fac0ec0bb424eabdbc1e9ff75d48b883
  (apps/instances/releases.py의 healthcheck 보존 확인, PR은 확인 시 Open)
- Runtime dev: 19d2fdffef753bb9415861c4a6b382b6408455ea
  (docs/api/secure-provisioner.openapi.yaml의 Workload/RuntimeContainer 확인.
  현재 healthcheck·env·command 필드 없음)
