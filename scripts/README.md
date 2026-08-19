# 문제 공급망 도구

GitHub Actions에서 호출하는 문제 명세 검증 및 발행 자료 생성 도구를
관리합니다.

`render_k3s_smoke_manifest.py`는 발행 artifact를 AWS K3s smoke test용 단일 컨테이너 Deployment와 ClusterIP Service로 변환합니다. 운영 Runtime manifest를 대신하지 않습니다.

`k3s_smoke_runner.py`는 SSM managed K3s node에서 임시 namespace 생성, GHCR image pull secret 생성, rollout/TCP probe, namespace 정리를 실행합니다.

## 파일

### `discover_changed_challenges.py`

Git 변경 내역에서 `info.yaml`이 있는 문제 디렉터리를 찾아 검증 대상으로
선정합니다.

### `validate_info_spec.py`

`info.yaml`, 컨테이너 정의, Docker build context, architecture, port,
healthcheck, resource profile을 검증합니다. 검증 결과에서는 flag를
제거하고 build matrix와 정규화된 metadata를 생성합니다.

### `generate_publish_bundle.py`

검사와 발행을 통과한 컨테이너별 digest 및 SBOM을 모아 다음 자료를
생성합니다.

- `artifact-v2.json`: Runtime과 Scheduler가 사용할 immutable workload
- `registry-publish.json`: Challenge Registry revision 등록 요청 자료

### `render_publish_summary.py`

`artifact-v2.json`을 검증한 뒤 문제 slug, revision과 컨테이너별 GHCR digest를
GitHub Actions Summary용 Markdown으로 출력합니다. tag-only image나 검사 실패
artifact는 요약하지 않습니다.
