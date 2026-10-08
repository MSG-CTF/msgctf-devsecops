# 문제 실행 설정

info.yaml에는 일반 환경변수 값과 백엔드 비밀값 이름을 적습니다
CI는 검증한 설정을 릴리스 파일에 담고 백엔드가 해당 문제의 비밀값 버전을 선택합니다
실제 값 주입과 NetworkPolicy 적용은 런타임이 맡습니다

| 입력 | 발행 파일 | 실행 때 처리 |
| --- | --- | --- |
| containers[].env | workload.containers[].env | 문자열 그대로 주입 |
| containers[].secret_env | workload.containers[].secret_env | 백엔드가 버전을 고정한 secret_ref로 변환 |
| healthcheck | workload.healthcheck | 승인된 HTTP readiness 검사 |
| category | isolation_profile | WEB·PWN 격리 프로필 선택 |
| ports·expose | ports[].port/public | 공개 포트 선택 |
| info.yaml의 flag | 포함하지 않음 | 운영자가 백엔드에 별도 등록 |

~~~yaml
deployment:
  runtime_type: KUBERNETES
  architecture: AMD64
  containers:
    - name: app
      build: prob/for_organizer
      ports: [8080]
      expose: true
      env:
        APP_MODE: ctf
      secret_env:
        FLAG: flag
        INTERNAL_TOKEN: internal_token
  resource_profile:
    cpu_millicores: 500
    memory_mib: 512
    ephemeral_storage_mib: 1024
~~~

env와 secret_env의 이름은 64자 이하의 대문자 식별자입니다
일반 값은 문자열만 허용하며 숫자·boolean은 따옴표로 감싸야 합니다
FLAG와 SECRET·TOKEN·PASSWORD·PASSWD·PRIVATE_KEY·API_KEY·CREDENTIAL 이름의 값은 secret_env를 사용합니다
비밀값 이름은 64자 이하의 소문자 식별자이며 FLAG는 flag를 참조합니다
같은 변수 이름을 두 필드에 중복해서 넣을 수 없습니다

컨테이너당 합계 32개, 일반 값당 UTF-8 4096바이트, 일반 이름과 값의 합계 16384바이트까지 허용합니다
백엔드와 런타임은 비밀값을 포함한 합계도 다시 검사합니다
원문 비밀값은 Git·발행 파일·참가자 ZIP·검수 자료에 넣지 않습니다

## 적용 순서

1) 백엔드의 비밀값 저장·조회 API와 암호화 키를 준비합니다
2) 런타임을 백엔드 조회 방식으로 바꾸고 새 스케줄러를 배포합니다
3) 문제별 비밀값을 등록하고 새 릴리스를 등록·활성화합니다
4) 문제 저장소 caller의 도구 checkout·두 workflow·두 devsecops_ref를 같은 고정 SHA로 갱신합니다

새 env·secret_env가 있으면 artifact schema 2.1로 발행합니다
없으면 기존 schema 2.0 형식을 유지합니다
구형 백엔드는 2.1을 거절하며 새 백엔드도 2.0에 새 필드를 넣으면 거절합니다
파일 이름은 artifact-v2.json을 유지합니다

직접 Runtime smoke에는 일반 env만 전달할 수 있습니다
secret_env가 있으면 백엔드 승인 경로가 필요하다는 오류로 중단합니다
CI 토큰에 비밀값 조회 권한을 주거나 참조를 임의로 만들어 보내지 않습니다

## 검수표

| 확인할 것 | 기대 결과 |
| --- | --- |
| info.yaml → metadata → 발행 파일 | env·비밀값 이름 보존, flag 원문 없음 |
| 비밀값 누락·다른 문제의 이름 | 백엔드 릴리스 등록 실패 |
| 활성 릴리스 변경 후 기존 인스턴스 reset | 처음 선택한 revision·env·비밀값 버전 유지 |
| 비밀값 조회 실패 | Pod 생성 전에 실패, 원문 없는 오류 |
| 같은 인스턴스 내부 통신 | 허용 |
| 다른 인스턴스 통신·외부 egress | 기존 정책대로 차단 |
| 삭제 | namespace와 Secret 제거 |

현재 네트워크는 STANDARD@v2, DNS와 같은 인스턴스 내부 통신 허용, 지정 포트 공개, egress NONE입니다
raw NetworkPolicy·internal_connections·외부 통신 예외는 입력받지 않습니다
컨테이너는 각각 별도 Pod이므로 내부 연결에는 대상 Service DNS를 사용합니다
Compose 서비스명이 Runtime Service 이름과 같은지도 확인해야 합니다

command·volumes·임의 네트워크 설정은 계속 미지원입니다
AFTERIMAGE의 인스턴스별 비밀값 생성과 Notebook의 DB 경로 문제는 별도 작업이며 기존 이미지 차단을 해제하지 않습니다

기존 37개 문제의 설정 후보는 [점검표](reports/2026-10-02-execution-settings/execution-settings.md)에 있습니다
이 목록은 실행 성공 판정이 아니며 출제자가 필수 값·주소·reset 동작을 확인해야 합니다
검사 코드는 [실행 설정 계약 테스트](../tests/test_execution_settings_contract.py)에서 확인할 수 있습니다
