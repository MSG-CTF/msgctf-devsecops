# MSG CTF Challenge DevSecOps

출제자가 올린 문제를 검사하고, 실행 이미지와 참가자 제공 파일을 발행하는 공통 CI 저장소입니다
백엔드는 성공한 발행 산출물을 가져와 문제와 배포 버전에 연결합니다

[플랫폼 전체 소개](https://github.com/MSG-CTF/msg-ctf.github.io)

## 맡은 일

- 문제 명세·빌드 경로·컨테이너·실행 설정 검사
- 이미지 빌드, 취약점·비밀값 검사와 SBOM 생성
- digest로 고정한 GHCR 이미지와 버전별 발행 bundle 생성
- 참가자 제공 파일 ZIP과 파일 manifest 발행
- 환경변수·비밀값 참조·네트워크 실행 프로필 전달
- 발행과 별도로 실행하는 런타임 시험, SSH·기존 Pod image-agent 연결

## 함께 만든 사람들

| 기여자 | 기여 내용 | 관련 PR |
| --- | --- | --- |
| [wlsdnd2367](https://github.com/wlsdnd2367) | 공통 문제 CI, 명세·보안 검사·SBOM·발행 bundle과 노드 이미지 준비 연결 | [#17](https://github.com/MSG-CTF/msgctf-devsecops/pull/17) · [#26](https://github.com/MSG-CTF/msgctf-devsecops/pull/26) · [#34](https://github.com/MSG-CTF/msgctf-devsecops/pull/34) |
| [jongcoding](https://github.com/jongcoding) | 실행 환경변수·비밀값 참조와 Crypto·Rev TCP 프로필 연동 | [#19](https://github.com/MSG-CTF/msgctf-devsecops/pull/19) · [#22](https://github.com/MSG-CTF/msgctf-devsecops/pull/22) |
| [goldsimchoi](https://github.com/goldsimchoi) | GCP 런타임 HTTPS 배포 시험 경로 | [#16](https://github.com/MSG-CTF/msgctf-devsecops/pull/16) |

2026-11-09까지 병합된 PR과 커밋을 기준으로 정리했습니다

## 기술 구성

GitHub Actions · Python · Docker/Buildx · GHCR · Trivy · Gitleaks

## 개발·운영 문서

- [참가자 제공 파일 계약](docs/participant-files-contract.md)
- [문제 저장소 호출 예제](docs/challenge-caller-example.yml)
- [GCP 런타임 시험](docs/gcp-runtime-https-smoke.md)
- [기존 Pod image-agent 연결](docs/vm-pod-image-agent.md)
- [기존 개발·설정 참고 문서](README.reference.md)
