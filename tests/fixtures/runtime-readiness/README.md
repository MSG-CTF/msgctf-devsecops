# Runtime readiness 계약 예제

다음 공식 예제를 원문 그대로 보관합니다.

- [query.json](https://github.com/MSG-CTF/secure-provisioner/blob/619423a35876d3e823df17b812cb0b1539001c13/docs/api/examples/image-preparation/query.json)
- [response.json](https://github.com/MSG-CTF/secure-provisioner/blob/619423a35876d3e823df17b812cb0b1539001c13/docs/api/examples/image-preparation/response.json)

이는 실제 운영 결과가 아닌 계약용 가상 target·이미지입니다. 타임스탬프를 현재로
바꾸지 않고 2026-10-24T00:00:30Z 기준으로 재현합니다. 공식 canonical image_set_id,
target-a의1/2 부분 준비, target-b의 미준비와 unknown-target의 응답 누락을 검사합니다.
