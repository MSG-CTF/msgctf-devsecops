# 문제 공급망 도구

GitHub Actions에서 호출하는 문제 명세 검증 및 발행 자료 생성 도구를
관리합니다.

`runtime_api_smoke_runner.py`는 SSM managed K3s node에서 발행 artifact를 Secure
Provisioner API 요청으로 변환합니다. 생성 Operation을 조회한 뒤 같은 API로 즉시
삭제하고 cleanup 결과까지 검증합니다. Kubernetes manifest는 생성하지 않습니다.

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

컨테이너별 공급망 소요 시간을 검증해
`artifact-v2.json`의 `evidence.containers[].timing`에 보존합니다.

### `pipeline_timing.py`

GitHub Actions의 컨테이너별 `Build/Pull`, `Scan`, `GHCR Push` 구간을 측정하고
`timing.json`을 생성합니다. `total_seconds`는 세 구간의 합계이며 runner 대기와
job 준비 시간은 포함하지 않습니다.

### `render_publish_summary.py`

`artifact-v2.json`을 검증한 뒤 문제 slug, revision, 컨테이너별 GHCR digest와
공급망 소요 시간을 GitHub Actions Summary용 Markdown으로 출력합니다. tag-only
image나 검사 실패 artifact는 요약하지 않습니다.
