# 실행 설정 연동 검수

검수일: 2026년 10월 8일

백엔드가 비밀값 버전을 선택하고 런타임이 조회·주입하는 경로를 확인했습니다
환경변수와 참조는 CI 발행 파일부터 생성·reset까지 보존됩니다
네트워크는 기존 격리 프로필과 포트 계약을 사용합니다

## 확인한 명세

| 문서 | 확인한 계약 |
| --- | --- |
| [Runtime API 10월 5일](https://app.notion.com/p/3f00f19c72be80e0a37bd22cb115749e) | 승인 이미지·비동기 실행·NetworkPolicy, 기존 FLAG 파일 모델 |
| [백엔드 릴리스 API](https://app.notion.com/p/3c80f19c72be811b9bc7fa7acaf9c753) | 릴리스 이력과 활성 포인터 |
| [Registry와 백엔드](https://app.notion.com/p/3bb0f19c72be8194817bd79af9ba1822) | CI 발행 파일을 백엔드가 수집, 스케줄러는 Registry를 읽지 않음 |
| [스케줄러 API](https://app.notion.com/p/3a50f19c72be804d81f7dba8d8876fa8) | 백엔드 생성 요청과 저장된 설정으로 reset |

FLAG 관리 주체는 이번 요청에서 백엔드로 이전하도록 정했습니다
10월 5일의 VM 파일 방식은 구현과 문서에서 제거했습니다
공유 노션 페이지는 수정하지 않았습니다

## 코드 기준

| 저장소 | 검수 시작 commit |
| --- | --- |
| [백엔드 #26](https://github.com/MSG-CTF/msg-backend/pull/26) | 8642e68f05670b81b6aa36bb1180d685d5a9bf8d |
| [스케줄러 #59](https://github.com/MSG-CTF/instance-scheduler/pull/59) | c66b18e0bedf7ea027ec048fcd68606d4912196a |
| [런타임 #45](https://github.com/MSG-CTF/secure-provisioner/pull/45) | 701567f410a68518bb628463c8d5480559f31efc |
| DevSecOps main | 40513968fa9e4a8a624dc7c11a6e0a399aada323 |
| [문제 caller #79](https://github.com/MSG-CTF/2026_MSG_CTF/pull/79) | 9e53cf53abffe3f38214804192df578e8e6325e9 |
| [Broker #4](https://github.com/MSG-CTF/resource-broker/pull/4) | 99ff5b884e4bf2198dabca84a179c11f5a516785 |
| 프론트 main | c1aea65015fd89d4c0b7f09f27a34f70d2ca9f14 |

프론트의 생성 요청은 이미 challenge_id만 보내고 있어 수정하지 않았습니다
Broker는 현재 구현이 있는 #4로 실행했으며 코드 변경은 없습니다
조직의 전체 PR과 모든 문제의 풀이를 검수했다는 뜻은 아닙니다

## 자동 검사

| 대상 | 결과 | 실행 범위 |
| --- | --- | --- |
| 백엔드 | 99개 통과 | apps.instances 전체, PostgreSQL 17, 새 마이그레이션 확인 |
| 스케줄러 | 382개 통과, 100개 skip | Gradle 전체, Docker가 필요한 자동 통합 검사는 skip |
| 런타임 | 793개 통과, 4개 skip | Go 전체와 PostgreSQL 저장·재시작·worker 검사, 하위 사례 포함 |
| DevSecOps | 194개 통과 | Linux 전체, 발행 계약·입력 검증·workflow 의존 파일 검사 |

Runtime의 기존 K3s 환경 전용 4개 검사는 필요한 환경변수를 지정하지 않아 skip됐습니다
아래 실제 연동은 별도로 구성한 로컬 K3s에서 실행했습니다
Windows DevSecOps 전체 검사는 symlink·Git·bash 환경 차이로 실패해 Linux에서 다시 실행했습니다

## 실제 연동 결과

CI generator → 백엔드 → 스케줄러 → 실제 Broker → 런타임 → K3s를 연결했습니다
세 서비스의 저장소는 PostgreSQL을 사용했습니다
K3s는 v1.34.1+k3s1이며 일반 WEB 프로필의 시험용 이미지로 검사했습니다
이미지는 로컬 containerd에 미리 넣었고 scan·SBOM 자료는 검사 fixture를 사용했습니다

| 검수 | 결과 |
| --- | --- |
| 일반 env와 FLAG·INTERNAL_TOKEN 주입 | 앱의 일반 값과 비밀값 hash 일치 |
| Kubernetes 변수 보간 | $(APP_MODE)를 입력 문자열 그대로 전달 |
| 컨테이너별 Secret | 변경 불가 Secret, app 키만 연결, helper에는 연결 없음 |
| 같은 인스턴스의 비공개 helper | 접속 성공, helper는 ClusterIP |
| 다른 인스턴스의 비공개 helper | 접속 실패 |
| 새 릴리스·비밀값 버전으로 새 팀 생성 | revision 2와 새 값 선택 |
| 기존 팀 reset | revision 1과 기존 env·비밀값 버전 유지 |
| 참가자의 실행 설정·비밀값 등록 | 400·403, 관리자 JWT로 내부 조회도 401 |
| 스케줄러 v2 무인증 요청 | 401 |
| 저장소·메타데이터·로그 | 비밀값 원문 없음, 백엔드 DB는 암호문으로 저장 |
| reset·삭제 정리 | 세 namespace와 Secret 제거 |

원문 비밀값 대신 hash와 성공 여부만 기록했습니다
상세 결과: [로컬 연동 기록](2026-10-08-execution-settings.json)

## 반영할 때 남는 일

운영자는 암호화 키·worker 토큰과 문제별 비밀값을 등록해야 합니다
새 FLAG 릴리스를 승인하기 전에는 생성·reset을 잠시 중단하고 구형 대기 요청을 정리해야 합니다
인스턴스별 비밀값 생성과 FLAG 채점 hash의 릴리스별 관리, 외부 통신 예외는 별도 작업입니다
AFTERIMAGE와 Notebook의 기존 차단은 유지합니다
운영 GCP·PWN/gVisor·실제 문제 풀이·GHCR cold pull·새 공급망 scan은 이번 시험에 포함되지 않습니다

명세 이름 검사는 새 필드에서 위반이 없었습니다
기존 runtime-status 경로 한 건은 시작 commit과 현재 명세에 동일하게 남아 있습니다
호출 경로를 바꾸는 작업은 이 변경에 포함하지 않았습니다
