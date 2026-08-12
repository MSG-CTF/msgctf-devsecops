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

## 현재 연동 계약 상태

2026-08-12 기준으로 GitHub의 각 팀 저장소에서 확인한 상태입니다. 아래의
미확정 항목은 DevSecOps workflow가 임의로 변환하거나 호출하지 않습니다.

### 문제 저장소

- `2026_MSG_CTF` 최상위의 `.github/workflows/challenge-validation.yml`이
  `msgctf-devsecops` reusable workflow를 호출합니다.
- `pwn-random6`은 validation, build, Gitleaks, Trivy, SBOM, GHCR 발행,
  publish bundle 생성까지 통과했습니다.
- `web-notebook`의 `db` image는 Trivy Critical 취약점
  `CVE-2025-68121` 때문에 발행이 차단됐습니다. 이는 예외 처리하지 않고
  문제 Dockerfile 또는 base image를 수정한 뒤 재검증해야 합니다.

### Resource Broker

- Broker의 `ResourceProfile`은 `cpu_millicores`, `memory_mib`,
  `ephemeral_storage_mib`, `architecture`를 사용합니다.
- publish bundle은 앞의 세 리소스 값을 `resource_profile`에, architecture를
  artifact 최상위에 기록합니다. Scheduler가 Broker 요청을 만들 때
  artifact의 `architecture`를 `resource_profile.architecture`로 옮기는 것이
  현재 계약입니다.
- CI는 Broker API를 직접 호출하지 않습니다. 대상 선택은 Scheduler와 Broker의
  운영 요청 경로에서 수행합니다.

### Scheduler와 Runtime

- 현재 Scheduler의 `RuntimeWorkload` DTO는 단일 `image`, `container_port`,
  `resource_limits`만 수용합니다.
- DevSecOps artifact는 `info.yaml` 규약대로 멀티 컨테이너
  `workload.containers[]`를 보존합니다. 따라서 멀티 컨테이너 문제를 운영에
  연결하기 전에 Scheduler와 Runtime은 이 구조를 수용하는 DTO/API를 확정해야
  합니다.
- 단일 컨테이너 문제는 digest image, 공개 포트, resource profile을 현재
  Scheduler DTO로 변환할 수 있습니다. 변환 책임은 Registry 또는
  Scheduler/Runtime 경계에 두고, CI artifact를 단일 컨테이너로 손실 변환하지
  않습니다.

### Monitoring과 CD

- Monitoring 팀의 현재 Prometheus 지표는 플랫폼 Django 상태 중심입니다.
  Challenge Pod의 readiness, image pull 실패, healthcheck 실패 지표와 알림
  규칙은 Runtime·Monitoring 팀이 별도로 확정해야 합니다.
- GitHub Actions는 검증, GHCR 발행, publish bundle 생성까지 담당합니다.
  참가자 요청에 따른 Namespace, Pod, Service, TTL cleanup은 Runtime과
  Scheduler의 운영 책임입니다.
