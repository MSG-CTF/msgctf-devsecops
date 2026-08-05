# AWS K3s CD Smoke Test 구현 계획

**목표:** 출제 문제 공급망 workflow가 생성한 digest 고정 artifact를 AWS EC2의 AMD64 K3s에 임시 배포하고, TCP 또는 HTTP 연결을 확인한 뒤 정리한다.

**구조:** GitHub Actions는 OIDC로 제한된 AWS role을 가정하고, 생성한 manifest와 배포 도구를 S3에 올린다. SSM이 K3s node 내부에서 image pull secret 생성, namespace 배포, readiness 확인, TCP/HTTP probe, cleanup을 수행한다. 이 흐름은 Runtime API가 준비되기 전의 CD smoke test이며 운영 Runtime을 대체하지 않는다.

## 제약

- 대상 node는 AMD64 Linux EC2 한 대의 K3s smoke 환경이다.
- 문제 image는 GHCR private package이며 node는 AWS Secrets Manager의 read-only deploy token으로 pull한다.
- GitHub Actions는 장기 AWS access key를 사용하지 않고 OIDC role만 사용한다.
- 문제 Pod는 `ci-smoke-` namespace에만 생성하며 성공·실패와 관계없이 삭제한다.
- Runtime이 운영 Pod, NetworkPolicy, 외부 endpoint, lifecycle을 소유한다. 이 구현은 image 실행 검증 목적이다.

## GitHub Actions 설정

문제를 올리는 저장소에서 reusable workflow를 호출할 때 아래 secret을 전달한다.

| Secret | 용도 |
|---|---|
| `AWS_ROLE_TO_ASSUME` | GitHub OIDC가 assume할 최소 권한 IAM role ARN |
| `AWS_REGION` | K3s EC2, S3, SSM이 있는 AWS Region |
| `AWS_K3S_INSTANCE_ID` | SSM managed AMD64 K3s EC2 instance ID |
| `AWS_CD_ARTIFACT_BUCKET` | manifest와 runner를 잠시 저장할 private S3 bucket |
| `GHCR_PULL_SECRET_ARN` | GHCR pull token을 가진 Secrets Manager secret ARN |

Secrets Manager의 GHCR credential은 다음 JSON 형식으로 저장한다. PAT에는 필요한 package read 권한만 부여한다.

```json
{
  "username": "msgctf-registry-bot",
  "token": "ghp_..."
}
```

호출 저장소 workflow에서는 `enable_k3s_smoke_deploy: true`와 함께 위 secret을 전달한다. 기본값은 `false`이므로 기존 CI 호출과 정적 문제에는 영향이 없다.

```yaml
jobs:
  publish:
    uses: MSG-CTF/msgctf-devsecops/.github/workflows/challenge-supply-chain.yml@main
    with:
      challenge_path: pwn-random6
      revision: "1"
      enable_k3s_smoke_deploy: true
    secrets: inherit
```

K3s node에는 `k3s kubectl`이 `kubectl`로 동작하도록 설정하고, Python 3와 AWS CLI를 설치한다. node IAM role에는 staging S3 prefix의 `s3:GetObject`, 지정한 `GHCR_PULL_SECRET_ARN`의 `secretsmanager:GetSecretValue`, SSM managed instance 기본 권한만 부여한다.

GitHub OIDC role에는 staging bucket의 `s3:PutObject`, `s3:DeleteObject`와 해당 instance의 `ssm:SendCommand`, `ssm:GetCommandInvocation`만 부여한다.

## 실행 흐름

1. CI가 `artifact-v2.json`에서 digest 고정 image와 resource profile을 읽는다.
2. `ci-smoke-<challenge>-<run>` namespace용 Deployment와 ClusterIP Service를 렌더링한다.
3. manifest와 runner를 private staging S3에 업로드한다.
4. SSM이 K3s node에서 GHCR pull secret을 만들고 Deployment rollout을 기다린다.
5. node 내부 `kubectl port-forward`로 공개 TCP port에 연결한다.
6. 성공과 실패 모두 namespace와 S3 staging object를 정리한다.

이 smoke test는 단일 컨테이너·공개 TCP port 하나만 지원한다. 멀티 컨테이너, HTTP health path, NetworkPolicy, 외부 Service/Gateway, TTL 관리는 Runtime 계약이 확정된 뒤 Runtime이 구현한다.

## 작업

1. artifact-v2.json을 K3s Deployment와 ClusterIP Service manifest로 변환하는 Python 도구와 단위 테스트를 추가한다.
2. K3s node 내부에서 deploy, probe, cleanup을 실행하는 smoke runner를 추가한다.
3. challenge-supply-chain reusable workflow에 선택적 AWS K3s CD smoke job을 추가한다.
4. AWS VPC, EC2, SSM, S3 staging bucket, 최소 IAM policy를 만드는 Terraform 모듈을 추가한다.
5. K3s node bootstrap과 Registry Mirror를 관리하는 Ansible Playbook 및 운영 문서를 추가한다.
6. pwn-random6 caller workflow에서 `runtime_type: KUBERNETES`와 CD smoke input을 사용해 실제 배포를 검증한다.
