# 문제 공급망 도구

GitHub Actions에서 호출하는 문제 명세 검증 및 발행 자료 생성 도구를
관리합니다.

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
