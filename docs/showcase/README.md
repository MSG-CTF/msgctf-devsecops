# README 그림과 구현 근거

- [발행본 연동](https://github.com/MSG-CTF/msgctf-devsecops/blob/d6c0008df4df2755e0470e6d5e693b42c57dba1d/docs/challenge-registry-integration.md)
- [이미지 준비](https://github.com/MSG-CTF/msgctf-devsecops/blob/d6c0008df4df2755e0470e6d5e693b42c57dba1d/docs/node-image-prefetch.md)

구성도는 데이터 흐름을 설명하며 실시간 서비스 상태나 전체 대상의 운영 검증 결과를 나타내지 않습니다

## SLA 수집·알림

서비스 API·전체 인스턴스 목록·노드 수집기를 Sentinel에 연결했습니다
Discord 알림과 Prometheus 메트릭 조회는 별도 경로로 표시했습니다

[구현 근거](https://github.com/MSG-CTF/msg-ctf.github.io/blob/main/docs/sla-flow.md) · [Sentinel 기준 커밋](https://github.com/MSG-CTF/sentinel/tree/849f267795a3878bf234eb5db7054177ad5614b8)
