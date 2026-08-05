# 문제 image 저장 및 발행 정책

## 목적

출제 문제 image를 같은 입력에서 재현 가능하고 추적 가능한 상태로 보관하며,
Runtime이 변하지 않는 image를 실행하도록 합니다.

## 공식 저장소

- 문제 image의 공식 원본 Registry는 GHCR을 사용합니다.
- image 경로는 `ghcr.io/msg-ctf/challenges/<challenge_slug>/<container>`입니다.
- 출제자는 Registry 경로를 `info.yaml`에 직접 작성하지 않습니다. CI가 build 또는
  외부 OCI image pull 뒤 정해진 GHCR 경로로 발행합니다.
- Docker Hub는 base image와 명시적 외부 image를 읽는 용도로만 허용합니다. Runtime이
  문제 image를 Docker Hub에서 직접 pull하지 않습니다.

## version과 digest

- CI는 추적용 commit SHA tag를 발행할 수 있지만, Runtime과 Challenge Registry에는
  항상 `@sha256:<digest>` 형식만 전달합니다.
- `latest` tag는 생성하거나 Runtime에 전달하지 않습니다.
- 새 문제 patch는 새 revision과 새 digest를 만듭니다. 기존 실행 instance가 참조하는
  digest와 SBOM은 삭제하지 않습니다.

## 발행 조건

다음 조건을 모두 만족한 container image만 GHCR에 발행합니다.

- `info.yaml`과 Docker build context 검증 성공
- Gitleaks 저장소 secret 검사 성공
- Trivy Critical 취약점 검사 성공
- Trivy High/Critical image secret 검사 성공
- CycloneDX SBOM 생성 성공

`publish_image: false`인 dry-run은 동일한 검증과 image build를 수행하지만 GHCR
push, publish bundle 생성, Challenge Registry 등록 요청을 수행하지 않습니다.

## Registry mirror와 보존

- 대회 운영 노드는 GHCR의 digest를 기준으로 K3s/containerd OCI mirror 또는
  node cache를 사용할 수 있습니다.
- mirror는 GHCR을 대체하는 별도 version source가 아니라, 같은 digest의 가용성을
  높이기 위한 cache입니다.
- active revision과 실행 중 instance가 참조하는 image는 대회 종료 및 instance
  cleanup 확인 전까지 보존합니다.
- 미참조 image 삭제 시에는 Challenge Registry revision, Runtime instance 기록,
  SBOM 보존 여부를 함께 확인합니다.

## architecture와 Windows

- 현재 문제 image는 Linux `AMD64`, `ARM64`만 허용합니다.
- Windows container는 Linux image와 같은 runner나 K3s node pool에 배치하지 않습니다.
- Windows 지원 전에는 Windows runner, 별도 Windows node pool, image OS metadata,
  Runtime 격리 정책, Registry mirror 접근 정책을 함께 확정해야 합니다.

## 권한

- CI의 `GITHUB_TOKEN`만 GHCR package write 권한을 가집니다.
- Runtime node의 pull credential은 read-only package 권한만 가집니다.
- 외부 문제 저장소를 읽는 `CHALLENGE_REPOSITORY_TOKEN`은 해당 문제 저장소의
  `Contents: Read-only` 권한만 가집니다.
- Registry credential, cloud credential, 문제 flag를 source repository, image layer,
  CI log, artifact에 기록하지 않습니다.
