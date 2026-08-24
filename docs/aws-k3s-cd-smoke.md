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
  runtime_target_id: aws-k3s-001
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
7. Actions Summary에 `target_id`, `runtime_workload_id`, 생성·삭제 결과를 남깁니다.
8. 성공과 실패 모두 S3 staging 파일을 삭제합니다.

Smoke instance와 team UUID는 GitHub run 정보로 결정적으로 생성됩니다. 같은 run을
재시도해도 Runtime의 `request_id` 멱등 계약을 사용할 수 있습니다.

## 현재 제약

- Runtime팀 API의 현재 격리 profile에 맞춰 `pwn`은 `PWN`, 나머지는 `WEB`을 사용합니다.
- `info.yaml`에 `run_as_user`가 없으면 smoke 요청은 non-root UID `10001`을 사용합니다.
- 한 컨테이너 안에서 public 포트와 private 포트를 섞는 artifact는 Runtime의 현재
  container 단위 `expose` 계약으로 손실 없이 변환할 수 없어 거부합니다.
- 운영 참가자 instance 생성은 Backend, Scheduler, Broker, Runtime 경로가 담당합니다.
  이 job은 문제 revision 발행 직후의 임시 통합 검증입니다.

## 실행 전 확인

- Secure Provisioner `dev` 버전이 EC2에서 실행 중이어야 합니다.
- `/etc/secure-provisioner/service-token` 권한과 token 형식이 유효해야 합니다.
- `PROVISIONER_CLUSTER_REGISTRY`의 target과 K3s kubeconfig가 유효해야 합니다.
- K3s/containerd가 private GHCR digest를 pull할 수 있어야 합니다.
- 실패 후 Runtime Operation과 Namespace가 남지 않았는지 확인해야 합니다.
