# MSGCTF DevSecOps 운영 절차

## 정상 발행

1. 문제 저장소 caller workflow에서 `challenge_path`와 새 `revision`을 지정합니다.
2. `info.yaml` validation과 Gitleaks 결과를 확인합니다.
3. 각 container의 build 또는 pull 결과를 확인합니다.
4. Trivy vulnerability 및 image secret gate를 확인합니다.
5. 컨테이너별 CycloneDX SBOM 생성을 확인합니다.
6. GHCR 또는 승인된 OCI Registry의 commit tag와 digest를 확인합니다.
7. `<challenge_slug>-publish-bundle`을 내려받아 `artifact-v2.json`과 `registry-publish.json`을 검토합니다.
8. Challenge Registry API가 연결돼 있으면 publish document를 한 transaction으로 등록합니다.
9. Runtime 통합 테스트에서 digest workload로 instance를 생성합니다.

## 발행 전 검수

- 모든 image가 `@sha256:` 참조인지 확인합니다.
- `latest` 참조가 없는지 확인합니다.
- container 수와 `info.yaml`의 container 수가 일치하는지 확인합니다.
- `ports[].public`이 `expose`와 일치하는지 확인합니다.
- healthcheck container와 port가 workload에 존재하는지 확인합니다.
- SBOM 파일이 container마다 하나씩 존재하는지 확인합니다.
- `source_ref`와 revision이 운영 승인 대상과 일치하는지 확인합니다.

## 실패 대응

### `info.yaml` 검증 실패

- 오류가 발생한 필드만 수정합니다.
- build path가 문제 디렉터리 밖을 가리키지 않는지 확인합니다.
- Dockerfile이 build context 바로 아래에 있는지 확인합니다.
- flag 값을 Actions 로그에 붙여 넣지 않습니다.

### Gitleaks 실패

1. 탐지된 credential을 즉시 폐기합니다.
2. 저장소 history와 현재 파일에서 값을 제거합니다.
3. 새 credential은 GitHub Secret 또는 외부 Secret Manager에 저장합니다.
4. 재실행 전에 기존 image layer에도 값이 없는지 확인합니다.

### Trivy 실패

- Critical 취약점이면 base image 또는 dependency를 수정합니다.
- image secret이면 해당 layer를 포함하지 않도록 Dockerfile을 수정합니다.
- 예외 발행은 대상 digest, 사유, 승인자, 만료일이 기록된 경우에만 허용합니다.

### OCI Registry push 실패

- workflow job의 `packages: write` 권한을 확인합니다.
- 조직 package 정책과 image 경로의 소문자 여부를 확인합니다.
- 동일 commit image를 다시 build하지 않고 검사를 통과한 job을 재실행합니다.
- 부분적으로 push된 tag는 Runtime에 전달하지 않습니다.

### Registry publish 실패

- 기존 active revision을 유지합니다.
- OCI image가 존재하더라도 publish document 처리 전에는 배포 가능 상태로 표시하지 않습니다.
- Registry API 복구 후 같은 revision과 digest로 idempotent하게 재시도합니다.
- 실행 중 revision을 정리 대상으로 표시하지 않습니다.

### Runtime image pull 실패

- workload가 tag가 아닌 digest를 사용하는지 확인합니다.
- Registry pull credential과 mirror 동기화 상태를 확인합니다.
- `ImagePullBackOff` event와 node architecture를 확인합니다.
- DevSecOps는 임의로 Pod를 수정하지 않고 Runtime팀에 digest와 SBOM을 전달합니다.

## 긴급 문제 수정

1. 기존 revision을 수정하지 않고 새 revision을 만듭니다.
2. 전체 validation, build, scan, SBOM, publish 과정을 다시 실행합니다.
3. Challenge Registry에서 새 revision을 active로 전환합니다.
4. 기존 instance가 참조하는 revision과 digest는 유지합니다.
5. 신규 instance부터 새 active revision을 사용합니다.
6. rollback이 필요하면 이전 revision을 다시 active로 전환합니다.

## 대회 전 점검

- 문제별 active revision과 digest 목록을 고정합니다.
- 모든 digest가 OCI Registry와 mirror에 존재하는지 확인합니다.
- AMD64·ARM64 target과 image architecture가 일치하는지 확인합니다.
- 100~150팀 규모에서 cold pull과 warm pull 시간을 측정합니다.
- Registry 장애, mirror 지연, node 부족, image pull 실패를 리허설합니다.
- Terraform/Ansible 변경은 검토와 승인을 거친 버전만 적용합니다.
- Runtime·격리보안팀과 challenge Namespace의 Pod Security `restricted` 적용 상태를 확인합니다.
