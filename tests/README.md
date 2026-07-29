# 테스트

출제 문제 공급망의 명세, 보안 경계, 발행 자료 및 GitHub Actions 계약을
검증합니다.

## 테스트 구성

### `test_discover_changed_challenges.py`

변경된 문제 탐색과 안전하지 않은 문제 경로 차단을 검증합니다.

### `test_validate_info_spec.py`

정적·서버 문제 구분, Docker build context, 외부 image tag, container,
port, healthcheck, resource profile 검증을 담당합니다.

### `test_generate_publish_bundle.py`

digest 고정, SBOM 증거, scan 결과, revision, flag 제외와 Runtime·Registry
발행 자료 생성을 검증합니다.

### `test_workflow_contracts.py`

reusable workflow와 자체 검증 workflow가 필요한 단계만 포함하고 Runtime
배포 책임을 침범하지 않는지 확인합니다.

### `fixtures/`

멀티 컨테이너 `info.yaml`, 샘플 Dockerfile, 컨테이너별 CycloneDX SBOM 등
자동 테스트 입력 자료를 보관합니다.

## 실행

```bash
python3 -m pip install -r ci/requirements.txt
python3 -m unittest discover -s tests -v
python3 -m py_compile scripts/*.py
```
