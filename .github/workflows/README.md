# GitHub Actions Workflow

출제 문제를 검증하고 실행 가능한 OCI image와 배포 자료로 발행하는 자동화
workflow를 관리합니다.

## 파일

### `node-image-prefetch-plan.yml`

문제 저장소의 수동 main caller에서 호출하는 읽기 전용 reusable workflow입니다.
현재 문제와 성공한 bundle 전체를 대조해 아키텍처별 이미지 목록, 이전 목록과의
변경분과 Actions Summary를 보관합니다. 누락·조회·입력 실패는 전체 취합 실패로
처리하며 노드 다운로드, release 활성화나 이미지 삭제는 수행하지 않습니다.
[연동 기준과 caller 예시](../../docs/node-image-prefetch.md)를 확인합니다.

### `published-runtime-smoke.yml`

성공한 main 발행본을 선택하는 별도 수동 caller용 reusable workflow입니다.
선택한 실행·artifact·bundle의 출처를 검증한 뒤 승인된 단일 WEB 문제의 Runtime
생성·삭제를 시험합니다. 이미지 재발행이나 Backend 등록은 하지 않으며, 시험이
실패해도 원래 발행 실행의 상태에는 영향을 주지 않습니다.
[실행 조건과 검증 범위](../../docs/published-runtime-smoke.md)를 확인합니다.

### `ghcr-cleanup-dry-run.yml`

수동 실행하는 GHCR 이미지 정리 후보 조회입니다. package 읽기 권한만 사용하고
inventory와 보존·검토 보고서를 보관합니다. 실제 삭제와 자동 실행은 없습니다.

### `challenge-branch-validation.yml`

출제자 branch와 PR에서 호출하는 최소 권한 reusable workflow입니다.

- `contents: read`만 사용
- `info.yaml`과 Docker build context 검증
- Gitleaks와 Trivy 취약점·image secret 검사
- Docker build 또는 외부 OCI image pull
- CycloneDX SBOM을 Actions artifact로 14일 보관
- GHCR, Challenge Registry, AWS/K3s credential을 사용하지 않음

caller는 자동 실행에서 `source_ref: ${{ github.sha }}`를 전달합니다. 기존 branch를
수동 재검사할 때는 해당 branch명을 `source_ref`로 전달합니다.

### `challenge-supply-chain.yml`

문제 저장소가 호출하는 reusable workflow입니다.

- `info.yaml`과 Docker build context 검증
- 문제 저장소 Gitleaks 검사
- 컨테이너별 Docker build 또는 외부 OCI image pull
- Trivy 취약점·image secret 검사
- CycloneDX SBOM 생성
- GHCR push와 image digest 추출
- `artifact-v2.json`과 수동 검증용 `registry-publish.json` 생성
- Actions Summary에 컨테이너별 GHCR digest 표시
- Build/Pull, Trivy Scan, GHCR Push와 합계 시간 측정
- publish bundle을 90일 보관하고 artifact 이름을 caller output으로 제공
- `prob/for_user/`를 ZIP과 무결성 manifest로 만들어 별도 artifact로 90일 보관
- 설정된 경우 SSM을 통해 Secure Provisioner API로 K3s 생성·삭제 smoke test

승인된 `main` 실행만 이 workflow를 호출해 image와 publish bundle을 발행합니다.
출제자 branch와 PR은 `challenge-branch-validation.yml`을 호출합니다.

성공한 실행은 `-publish-bundle` suffix의 Actions artifact를 남깁니다.
`artifact-v2.json`은 Backend poller가 자동 수집하는 공식 입력이고,
`registry-publish.json`은 같은 artifact를 감싼 수동 API 검증용 wrapper입니다.
workflow와 caller는 Backend base URL 또는 service token을 사용하지 않으며,
Backend poller가 수집, challenge 매핑, release 등록, 중복 처리를 수행합니다.
Backend/admin이 active release 전환과 롤백을 수행합니다. K3s smoke test는
Runtime API를 거치며 Kubernetes resource를 직접 생성하지 않습니다.

### `pipeline-self-test.yml`

이 저장소의 공급망 도구를 검증하는 자체 테스트 workflow입니다.

수동 실행에서 `check_gcp_runtime_connection=true`를 선택하면 별도 읽기 전용
HTTPS 사전 점검을 실행합니다. Runtime token을 사용하거나 workload를 생성하지 않습니다.

- Python 단위 테스트와 문법 검사
- 샘플 서버 문제 image build
- 백엔드팀 KOTH 공식 양식과 동일한 `service` image build
- Trivy 보안 검사
- GHCR 발행
- publish bundle 생성
- 일반 문제와 KOTH 문제를 한 run에서 실행해 artifact 이름 충돌 방지 확인

플랫폼 Backend·Frontend를 빌드하거나 Runtime이 Kubernetes workload를 직접
배포하는 workflow는 이 디렉터리에서 관리하지 않습니다.
