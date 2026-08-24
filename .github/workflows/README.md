# GitHub Actions Workflow

출제 문제를 검증하고 실행 가능한 OCI image와 배포 자료로 발행하는 자동화
workflow를 관리합니다.

## 파일

### `challenge-supply-chain.yml`

문제 저장소가 호출하는 reusable workflow입니다.

- `info.yaml`과 Docker build context 검증
- 문제 저장소 Gitleaks 검사
- 컨테이너별 Docker build 또는 외부 OCI image pull
- Trivy 취약점·image secret 검사
- CycloneDX SBOM 생성
- GHCR push와 image digest 추출
- Runtime artifact와 Challenge Registry publish document 생성
- Actions Summary에 컨테이너별 GHCR digest 표시
- Build/Pull, Trivy Scan, GHCR Push와 합계 시간 측정
- publish bundle을 90일 보관하고 artifact 이름을 caller output으로 제공
- 설정된 경우 publish document를 Challenge Registry HTTPS API에 등록

Challenge Registry 등록은 `publish_registry: true`,
`CHALLENGE_REGISTRY_URL`, `CHALLENGE_REGISTRY_TOKEN`이 모두 설정된 경우에만
실행합니다. URL과 token은 임의 실행 입력이 아닌 GitHub Secret으로 관리합니다.
기본값은 비활성화이며 Backend DB, Scheduler, Broker, Runtime을 workflow가 직접
조작하지 않습니다.

### `pipeline-self-test.yml`

이 저장소의 공급망 도구를 검증하는 자체 테스트 workflow입니다.

- Python 단위 테스트와 문법 검사
- 샘플 서버 문제 image build
- 백엔드팀 KOTH 공식 양식과 동일한 `service` image build
- Trivy 보안 검사
- GHCR 발행
- publish bundle 생성
- 일반 문제와 KOTH 문제를 한 run에서 실행해 artifact 이름 충돌 방지 확인

플랫폼 Backend·Frontend를 빌드하거나 Runtime이 Kubernetes workload를 직접
배포하는 workflow는 이 디렉터리에서 관리하지 않습니다.
