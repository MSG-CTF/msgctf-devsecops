# 테스트

출제 문제 공급망의 명세, 보안 경계, 발행 자료 및 GitHub Actions 계약을
검증합니다.

## 테스트 구성

### `test_validate_runtime_smoke_source.py`

공식 main 성공 실행·전체 artifact pagination·시도 번호·만료·출처·SHA·revision과
digest 검증을 확인합니다. KOTH·PWN·VM·멀티 컨테이너의 암묵적 승인과 비밀값 노출을
차단하고, 독립 workflow가 발행·권한 확대·실패 무시를 하지 않는지 검사합니다.
첫 승인 step의 실제 셸을 이벤트·ref 28개 조합과 승인 누락 입력으로 실행합니다.
독립 workflow만 바뀌어도 push·PR 자체 검사가 실행되는지 확인하고,
실패 job만 재실행한 run의 이전 attempt bundle은 자동 재사용하지 않도록 검증합니다.

### `test_audit_execution_settings.py`

설정 이름만 출력하는 비밀값 보호, info.yaml 전용 점검 범위, KOTH 합산 자원 보존과
미확정 배포 계약 표시를 검증합니다. VM이나 참가자 .exe 파일만으로 Windows 실행을
추측하지 않으며 원본 명세·bundle·배포 승인 상태를 바꾸지 않는지 확인합니다.

### `test_discover_changed_challenges.py`

변경된 문제 탐색과 안전하지 않은 문제 경로 차단을 검증합니다.

### `test_validate_info_spec.py`

정적·서버 문제 구분, Docker build context, 외부 image tag, container,
port, healthcheck, resource profile 검증을 담당합니다.
백엔드팀의 공식 KOTH 템플릿 계약도 같은 validator로 검증합니다.

### `test_generate_publish_bundle.py`

digest 고정, SBOM 증거, scan 결과, revision, flag 제외와 Runtime·Registry
발행 자료 생성과 컨테이너별 공급망 시간 보존을 검증합니다.

### `test_pipeline_timing.py`

Build/Pull, Scan, GHCR Push 시간과 합계 계산, 잘못된 시각 입력 차단을 검증합니다.

### `test_package_user_files.py`

`prob/for_user/` ZIP과 무결성 manifest 생성, 파일이 없는 문제 처리, 심볼릭 링크,
파일 수와 크기 제한을 검증합니다.

### `test_render_publish_summary.py`

Actions Summary에 컨테이너별 GHCR digest, publish bundle 이름과 단계별 시간이
표시되고, tag-only image가 거부되는지 검증합니다.

### `test_workflow_contracts.py`

reusable workflow와 자체 검증 workflow가 필요한 단계만 포함하고 Runtime
배포 책임을 침범하지 않는지 확인합니다.

### `test_runtime_api_smoke_runner.py`

publish artifact를 Secure Provisioner 다중 컨테이너 계약으로 변환하고, 실제 로컬
HTTP 경계에서 생성·조회·삭제 Operation이 순서대로 완료되는지 검증합니다.

### `fixtures/`

멀티 컨테이너와 KOTH `info.yaml`, 샘플 Dockerfile, 컨테이너별 CycloneDX SBOM
등 자동 테스트 입력 자료를 보관합니다.

## 실행

```bash
python3 -m pip install -r ci/requirements.txt
python3 -m unittest discover -s tests -v
python3 -m py_compile scripts/*.py
```
