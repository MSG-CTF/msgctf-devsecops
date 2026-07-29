# 출제 문제 검증 파이프라인 설계

## 목적

`MSG-CTF/msgctf-devsecops`는 플랫폼 컴포넌트를 빌드하는 저장소가 아니라,
별도 `2026_MSG_CTF` 문제 저장소가 호출하는 출제 문제 검증 전용 CI/CD
도구 저장소로 사용한다.

## 저장소 경계

- 출제자는 `2026_MSG_CTF/<분야>-<문제명>/` 아래에 문제를 제출한다.
- 문제 디렉터리의 `info.yaml`이 build, 외부 image, 포트, 노출 여부,
  architecture 및 resource profile의 단일 소스다.
- `msgctf-devsecops`는 reusable workflow, 검증 스크립트, artifact 생성기와
  호출 예시만 소유한다.
- CI는 Kubernetes 리소스를 직접 생성하지 않는다. Runtime이 digest 고정
  workload를 받아 Namespace, Pod, Service 및 격리 정책을 생성한다.

## 처리 흐름

정적 문제는 공통 metadata와 디렉터리 이름만 검증하고 image를 만들지 않는다.
`deployment`가 있는 서버 문제는 컨테이너별로 `build` 또는 `image`를 처리한
뒤 Gitleaks, Trivy, CycloneDX SBOM, OCI push, digest 고정과 publish bundle
생성을 수행한다.

`2026_MSG_CTF` caller workflow는 push에서 변경된 최상위 문제 디렉터리를
찾아 각 경로를 reusable workflow의 `challenge_path`로 전달한다.

## 미확정 정책

- MVP 검증 registry는 GHCR을 사용하지만 최종 source registry와 node mirror는
  운영 결정 후 교체할 수 있어야 한다.
- Linux `AMD64`와 `ARM64`만 현재 지원한다.
- Windows container는 runner, node pool, registry 및 Runtime 지원 정책이
  확정되기 전까지 검증 단계에서 거부한다.
- Registry API와 active revision 전환은 Backend 계약 확정 전까지 수행하지
  않고 `registry-publish.json`만 생성한다.

## 성공 기준

- 공식 문제 디렉터리와 `info.yaml`을 검증한다.
- 정적 문제 검증은 Docker job 없이 성공한다.
- 서버 문제의 Dockerfile image와 외부 OCI image를 모두 처리한다.
- 검사한 동일 image만 digest로 고정해 발행한다.
- 플랫폼용 workflow가 자동 또는 수동 실행 목록에 남지 않는다.
- 샘플 서버 문제로 GitHub Actions 공급망 실행이 성공하고 publish bundle이
  생성된다.
