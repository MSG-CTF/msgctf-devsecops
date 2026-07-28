# MSGCTF 팀 저장소 계약 연동 설계

> 2026-07-29 전체 아키텍처 승인에 따라 구현 기준은
> `docs/superpowers/plans/2026-07-29-architecture-aligned-supply-chain.md`로
> 갱신되었습니다. 신규 기준은 SBOM, Atomic Publish, OCI Registry/Mirror,
> Runtime의 Kubernetes manifest·policy·cleanup 소유권을 포함합니다.

## 목적

DevSecOps 파이프라인을 `MSG-CTF` 조직의 실제 팀 저장소 구조와 계약에 맞춘다. 문제 저장소의 `info.yaml`을 기준으로 멀티 컨테이너 이미지를 빌드·검사·등록하고, 개별 플랫폼 저장소가 공통 CI를 호출할 수 있게 한다.

## 확인된 기준

### 문제 저장소

`MSG-CTF/2026_MSG_CTF`의 default branch와 `readme.md`, `web-notebook/info.yaml`을 문제 제출 계약의 우선 기준으로 사용한다.

- 문제 디렉터리 이름을 `challenge_slug`로 사용한다.
- `info.yaml`의 `deployment.containers[]`를 이미지 작업 목록으로 사용한다.
- `build`가 있으면 지정된 Docker build context로 이미지를 빌드한다.
- `image`가 있으면 외부 이미지를 pull한다.
- `ports`는 정수 목록이며 `expose`는 해당 컨테이너의 참가자 노출 여부다.
- `resource_profile`은 전체 컨테이너의 합산값이다.
- `flag`는 검증 여부만 확인하고 값은 출력, artifact, Docker label, SARIF에 포함하지 않는다.

### Scheduler와 Broker

Scheduler 코드의 DTO를 필드명과 타입의 우선 기준으로 사용한다.

- `challenge_id`: `BIGINT/Long`
- `runtime_type`: `KUBERNETES | DOCKER | VM`
- `architecture`: `AMD64 | ARM64`
- `resource_profile.cpu_millicores`: 정수
- `resource_profile.memory_mib`: 정수
- `resource_profile.ephemeral_storage_mib`: 정수

현재 Scheduler의 Runtime DTO는 단일 `image`, `container_port`, `service_url`만 지원한다. 따라서 멀티 컨테이너 artifact는 생성하되 Scheduler 또는 Runtime으로 자동 전달하지 않는다.

### 플랫폼 저장소

Backend, Scheduler, Runtime, Broker, Monitoring은 별도 저장소로 운영한다. DevSecOps 저장소의 샘플 컴포넌트 디렉터리를 실제 플랫폼 source로 취급하지 않는다.

## 문제 이미지 파이프라인 v2

### 호출 방식

`challenge-v2.yml`을 reusable workflow로 제공한다. 문제 저장소는 얇은 caller workflow에서 다음 값을 전달한다.

- `challenge_path`: `info.yaml`이 있는 문제 디렉터리
- `registry`: 기본값 `ghcr.io`

호출된 workflow는 caller 저장소를 먼저 checkout하고 DevSecOps 저장소를 도구 경로에 별도로 checkout한다.

### 검증

새 검증기는 다음 조건을 확인한다.

- `info.yaml`이 challenge path 바로 아래에 존재한다.
- `name`, `category`, `flag`가 존재하되 `flag` 값은 출력하지 않는다.
- 서버 문제라면 `deployment.runtime_type`, `architecture`, `containers`, `resource_profile`이 존재한다.
- `runtime_type`과 `architecture`는 Scheduler enum과 일치한다.
- 컨테이너 이름은 문제 안에서 유일하고 안전한 소문자 식별자다.
- 각 컨테이너에는 `build` 또는 `image` 중 하나만 존재한다.
- `build` 경로는 challenge directory 내부에 있고 Dockerfile이 존재한다.
- `ports`는 `1..65535` 정수 목록이다.
- `expose`는 boolean이다.
- resource 값은 모두 양의 정수다.

검증 결과는 flag를 제외한 JSON으로 생성한다.

### 이미지 처리

컨테이너마다 독립된 matrix job을 실행한다.

- `build`: 제한된 context에서 Docker image를 build한다.
- `image`: 외부 이미지를 pull한 후 source digest를 기록한다.
- Trivy vulnerability scan에서 Critical 발견 시 차단한다.
- Trivy image secret scan에서 High 또는 Critical 발견 시 차단한다.
- 통과한 이미지만 MSGCTF GHCR에 push한다.
- `latest`는 생성하지 않는다.
- 최종 참조는 반드시 `@sha256:<digest>` 형식으로 기록한다.

이미지 이름은 다음 규칙을 사용한다.

```text
ghcr.io/msg-ctf/challenge-<challenge_slug>-<container_name>:<commit_sha>
ghcr.io/msg-ctf/challenge-<challenge_slug>-<container_name>@sha256:<digest>
```

### artifact v2

최종 artifact는 다음 구조를 사용한다.

```json
{
  "schema_version": "2.0",
  "challenge_slug": "web-notebook",
  "name": "Notebook",
  "category": "web",
  "runtime_type": "KUBERNETES",
  "architecture": "AMD64",
  "workload": {
    "containers": [
      {
        "name": "web",
        "image": "ghcr.io/msg-ctf/challenge-web-notebook-web@sha256:...",
        "ports": [8080],
        "expose": true
      }
    ]
  },
  "resource_profile": {
    "cpu_millicores": 700,
    "memory_mib": 768,
    "ephemeral_storage_mib": 1024
  },
  "source_ref": "<commit_sha>",
  "scan_result": "PASS"
}
```

`challenge_id`는 현재 `info.yaml`에 없으므로 생성하거나 추측하지 않는다. Backend 또는 Challenge Registry가 slug와 `BIGINT challenge_id`의 매핑을 확정하면 artifact와 등록 요청에 추가한다.

`healthcheck`도 현재 `info.yaml`의 기계 판독 필드가 아니므로 SLA 문서에서 임의 추출하지 않는다. 팀 계약에 필드가 추가되면 검증기와 artifact를 확장한다.

## 플랫폼 공통 파이프라인

`component-cicd.yml` reusable workflow를 추가한다.

입력:

- `component_name`
- `context`
- `dockerfile`
- `test_command`
- `push_image`

처리:

1. caller 저장소 checkout
2. 팀이 지정한 test command 실행
3. Gitleaks 검사
4. Docker image build
5. Trivy vulnerability scan
6. main 또는 dev의 승인된 push에서만 GHCR push
7. digest 추출 및 artifact 업로드

Backend와 Scheduler는 아직 Dockerfile이 없으므로 실제 image build 성공을 가정하지 않는다. 각 팀이 Dockerfile과 caller workflow를 추가하면 공통 workflow를 사용할 수 있다.

기존 `platform-cicd.yml`은 샘플 호환용 수동 workflow로 남기고 자동 push trigger를 제거한다. 실제 플랫폼 source로 간주하지 않는다.

## 보안 경계

- private 문제 저장소의 flag를 stdout, output, artifact, cache key, image tag와 label에 포함하지 않는다.
- Docker build context를 각 `build` 경로로 제한한다.
- pull한 외부 이미지는 digest를 고정한 뒤 검사한다.
- GHCR에는 검사한 동일 image만 push한다.
- Runtime은 tag가 아닌 digest를 사용한다.
- caller PR에서는 package push와 배포를 수행하지 않는다.
- job별 권한은 `contents: read`, `packages: write`, `security-events: write` 등 필요한 범위로 분리한다.

## 기존 MVP와의 관계

- `challenge-deployment.yml`, `challenge.toml`, v1 artifact 생성기는 즉시 삭제하지 않는다.
- v1은 `workflow_dispatch`와 기존 검증 회귀용으로만 유지한다.
- 새 문제 제출은 v2 reusable workflow를 기준으로 한다.
- v2가 실제 문제 저장소 caller에서 성공하면 v1 제거 여부를 다시 결정한다.

## 검증

- flag를 포함한 fixture로 검증기를 실행하고 출력에 flag가 없는지 확인한다.
- 잘못된 build path, 중복 컨테이너, 잘못된 enum, 포트 범위를 각각 거부하는 테스트를 작성한다.
- build container와 external image container가 포함된 matrix 생성 테스트를 작성한다.
- artifact의 모든 image가 digest 참조인지 검사한다.
- workflow YAML 파싱과 GitHub Actions 정적 검사를 실행한다.
- 기존 Python 문법 검사와 컴포넌트 샘플 테스트를 유지한다.

## 완료 조건

- 실제 `info.yaml` 형식을 검증할 수 있다.
- 멀티 컨테이너 image 작업 matrix와 artifact v2를 생성할 수 있다.
- reusable challenge workflow와 component workflow가 저장소에 존재한다.
- 기존 v1 pipeline이 자동 실행되지 않고 수동 회귀용으로 유지된다.
- 문서가 실제 팀 저장소와 미확정 계약을 구분한다.
- 변경사항이 검증되고 `MSG-CTF/msgctf-devsecops`에 push된다.
