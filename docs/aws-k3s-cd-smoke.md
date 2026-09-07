# Secure Provisioner 경유 AWS K3s Smoke Test

## 목적

문제 공급망이 생성한 digest 고정 `artifact-v2.json`을 Runtime팀의 Secure
Provisioner API로 전달해 실제 K3s 생성과 삭제를 검증합니다. CI가 Kubernetes
manifest를 만들거나 `kubectl`을 직접 실행하지 않으므로 Namespace, 보안 정책,
Service와 cleanup의 소유권은 Runtime에 유지됩니다.

## 연결 구조

```text
GitHub Actions
  -> AWS OIDC
  -> S3 임시 staging
  -> SSM Run Command
  -> Secure Provisioner API (127.0.0.1:8080)
  -> K3s create
  -> Operation poll
  -> K3s delete
  -> Operation poll
```

Secure Provisioner가 노드에서 loopback 주소로 수신하므로 API를 인터넷에 공개하지
않습니다. Service Bearer token도 GitHub Secret으로 복사하지 않고 노드의
`/etc/secure-provisioner/service-token`에서만 읽습니다.

## GitHub 설정

문제 저장소 또는 Organization에 다음 Secret을 설정합니다.

| Secret | 용도 |
|---|---|
| `AWS_ROLE_TO_ASSUME` | GitHub OIDC가 assume할 최소 권한 IAM role ARN |
| `AWS_REGION` | EC2, S3, SSM이 있는 AWS Region |
| `AWS_K3S_INSTANCE_ID` | Secure Provisioner와 K3s가 실행 중인 SSM managed EC2 ID |
| `AWS_CD_ARTIFACT_BUCKET` | artifact와 runner를 잠시 저장할 private S3 bucket |

caller는 다음 입력을 전달합니다.

```yaml
with:
  enable_k3s_smoke_deploy: true
  runtime_target_id: aws-k3s-lab
secrets: inherit
```

`runtime_target_id`는 Secure Provisioner의 `PROVISIONER_CLUSTER_REGISTRY`에 등록된
활성 target과 정확히 일치해야 합니다.

## AWS 권한

GitHub OIDC role에는 다음 최소 권한이 필요합니다.

- 지정 S3 prefix의 `s3:PutObject`, `s3:DeleteObject`
- 지정 EC2 instance의 `ssm:SendCommand`
- 실행한 command의 `ssm:GetCommandInvocation`

EC2 instance role에는 다음 권한이 필요합니다.

- 지정 S3 `runtime-smoke/` prefix의 `s3:GetObject`
- SSM managed instance 기본 권한

GHCR 인증은 Runtime node의 K3s/containerd Registry 설정에서 관리합니다. CI 요청,
S3 파일과 Runtime API body에는 GHCR credential을 포함하지 않습니다.

## 실행과 정리

1. CI가 `artifact-v2.json`, Runtime 요청 변환 runner와 검증된 config를 S3에 올립니다.
2. SSM이 EC2 내부에서 세 파일을 내려받습니다.
3. runner가 `POST /internal/v1/instances`를 호출합니다.
4. `GET /internal/v1/operations/{operation_id}`를 `SUCCEEDED`까지 조회합니다.
5. 같은 instance를 `DELETE /internal/v1/instances/{instance_id}`로 정리합니다.
6. 삭제 Operation도 `SUCCEEDED`인지 확인합니다.
7. Actions Summary에 `target_id`, `runtime_workload_id`, digest 이미지 목록,
   `endpoints`, 생성·삭제 결과와 단계별 소요 시간을 남깁니다.
8. 성공과 실패 모두 S3 staging 파일을 삭제합니다.

Smoke instance와 team UUID는 GitHub run 정보로 결정적으로 생성됩니다. 같은 run을
재시도해도 Runtime의 `request_id` 멱등 계약을 사용할 수 있습니다.

정상 실행 결과에는 다음 증거가 포함됩니다.

```json
{
  "registry_revision": 12,
  "images": [
    {
      "name": "web",
      "image": "ghcr.io/msg-ctf/challenges/example/web@sha256:..."
    }
  ],
  "endpoints": [
    {
      "container_name": "web",
      "port": 8080,
      "protocol": "HTTP",
      "service_url": "http://203.0.113.10:31042"
    }
  ],
  "create_status": "SUCCEEDED",
  "create_elapsed_seconds": 12.345,
  "delete_status": "SUCCEEDED",
  "delete_elapsed_seconds": 1.234
}
```

Smoke runner는 `artifact-v2.json`의 `revision`과 `registry_revision`이 같은지,
`isolation_profile`이 문제 category와 일치하는지, `scan_result`가 `PASS`인지 먼저
확인합니다. `containers[]`의 digest 이미지와 선택형 `internal_connections[]`는
같은 publish bundle에서 읽어 Runtime 요청에 전달합니다.

bundle의 컨테이너 포트는 다음처럼 Runtime PR #39 계약으로 변환합니다.

- bundle의 전체 `ports[].port`는 Runtime 요청의 `ports`가 됩니다.
- `ports[].public: true`인 포트만 Runtime 요청의 `exposed_ports`가 됩니다.
- 모두 private인 컨테이너는 `exposed_ports: []`를 보냅니다.
- PWN은 공개 컨테이너가 정확히 1개여야 하며, 해당 컨테이너의 전체 포트도
  정확히 1개여야 합니다.
- Runtime 요청에는 기존 `expose`를 함께 보내지 않습니다.

따라서 한 컨테이너에 `8080 public`, `9000 private`가 함께 있어도 8080만 외부
endpoint로 요청할 수 있습니다. Runtime 응답의 `endpoints[]`는 요청한 모든
`(container_name, port)`와 누락, 추가, 중복 없이 정확히 일치해야 합니다. endpoint
각 항목의 `container_name`, `port`, `protocol`, `service_url`도 모두 검증합니다.

`create_elapsed_seconds`는 생성 요청을 처음 제출한 시점부터 생성 Operation이
`SUCCEEDED`가 될 때까지의 시간입니다. 이미지 pull뿐 아니라 Pod와 Service 준비
시간도 포함하므로 순수 네트워크 처리량으로 해석하지 않습니다.

## GHCR pull 검증

Issue #30을 닫기 전 정상 cold pull, GHCR 인증 실패와 `ImagePullBackOff`를 각각
재현합니다. 장애 주입은 승인된 publish bundle을 변조하지 않고 Secure Provisioner
팀이 제공하는 전용 test target에서 수행합니다.

| 시나리오 | DevSecOps 증거 | Secure Provisioner 준비와 확인 |
|---|---|---|
| cold pull | 실제 digest와 `create_elapsed_seconds` 기록 | 실행 전 해당 test digest의 node cache 제거 |
| 인증 실패 | 정상 검사된 private GHCR digest 제공 | 잘못되거나 제거된 pull credential을 가진 전용 target에서 실패 재현 |
| `ImagePullBackOff` | 운영 bundle과 분리된 테스트임을 기록 | 존재하지 않는 digest로 Pod 상태와 Operation 오류를 확인 |

cold pull 확인은 같은 digest가 없는 상태에서 한 번 실행하고, 같은 node에서 다시
실행한 warm-cache 결과와 비교합니다. cache 제거, pull credential 변경과 Pod 상태
수집은 Runtime 소유 작업이며 CI가 `crictl`, `containerd`, Kubernetes Secret 또는
`kubectl`을 직접 조작하지 않습니다.

GHCR 인증 실패와 `ImagePullBackOff`는 정상 문제 발행의 성공 조건이 아닙니다.
따라서 일반 `k3s-smoke-deploy` job에 가짜 digest나 credential을 넣지 않고 Runtime
통합 테스트에서 실패 Operation의 `last_error_code`, Pod waiting reason과 cleanup
결과를 증거로 남깁니다. credential, service token과 raw pull 오류는 Actions Summary,
S3 staging 파일 또는 API body에 기록하지 않습니다.

## 현재 제약

- Runtime팀 API의 현재 격리 profile에 맞춰 `pwn`은 `PWN`, 나머지는 `WEB`을 사용합니다.
- `info.yaml`에 `run_as_user`가 없으면 smoke 요청은 non-root UID `10001`을 사용합니다.
- 운영 smoke 대상은 Runtime팀에서 전달한 `aws-k3s-lab`을 사용합니다.
- `aws-k3s-lab` node에서 읽을 Runtime API service token이 아직 준비되지 않아 실제
  K3s 생성·endpoint 확인·삭제는 실행하지 않았습니다. 현재 완료 범위는 요청 변환과
  cleanup 동작의 단위 테스트입니다.
- 운영 참가자 instance 생성은 Backend, Scheduler, Broker, Runtime 경로가 담당합니다.
  이 job은 문제 revision 발행 직후의 임시 통합 검증입니다.

## 실행 전 확인

- Secure Provisioner `dev` 버전이 EC2에서 실행 중이어야 합니다.
- `/etc/secure-provisioner/service-token` 권한과 token 형식이 유효해야 합니다.
- `PROVISIONER_CLUSTER_REGISTRY`의 target과 K3s kubeconfig가 유효해야 합니다.
- K3s/containerd가 private GHCR digest를 pull할 수 있어야 합니다.
- 실패 후 Runtime Operation과 Namespace가 남지 않았는지 확인해야 합니다.
- create operation 결과가 불완전하면 runner가 `runtime-status`에서 workload ID를
  cleanup 제한 시간까지 재시도해 복구하고 삭제합니다. status 조회에서도 ID를 얻지
  못하면 Runtime팀이 해당 instance의 잔존 리소스를 확인해야 합니다.
- cold pull 검증은 다른 workload가 없는 전용 target에서 Runtime팀이 image cache
  상태를 확인한 뒤 실행해야 합니다.
