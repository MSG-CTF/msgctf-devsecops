# TCP 문제의 실행 설정

Crypto와 Rev 문제 중에도 HTTP 없이 TCP로 접속하는 문제가 있습니다
분야는 그대로 두고 deployment.isolation_profile에 PWN을 지정합니다

```yaml
category: crypto
deployment:
  runtime_type: KUBERNETES
  architecture: AMD64
  isolation_profile: PWN
```

선택값은 WEB과 PWN입니다 생략하면 기존처럼 Pwn 분야에는 PWN, 나머지에는 WEB을 사용합니다
Pwn 분야를 WEB으로 낮추는 설정은 거절합니다 PWN을 선택한 문제에는 기존 공개 컨테이너·포트 제한도 적용합니다

이 값은 문제 명세 검사, 발행 JSON, 발행 결과 요약, 런타임 시험 요청까지 유지됩니다
실제 격리와 이미지별 허용 설정은 런타임이 검증합니다

중앙 파이프라인이 반영된 뒤 문제 저장소의 고정 참조를 갱신해야 합니다
그 전에는 info.yaml에 필드만 추가해도 기존 검사에서 거절됩니다
