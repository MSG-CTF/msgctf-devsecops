# 기존 Pod형 image-agent의 SSH 연결

호스트에 `runtime-image-agent` 파일이 없더라도 Runtime의 DaemonSet agent가 실행
중일 수 있습니다. 이 경로는 기존 agent를 그대로 호출하는 **수동 정비용 전송 어댑터**입니다.
새 다운로드 엔진·Runtime API·Pod·DaemonSet을 만들거나 기존 agent를 재배포하지 않습니다.

```text
기존 vm_image_prefetch 계획 검수·승인
 → 고정 SSH 명령
 → root 소유 vm-image-pod-bridge
 → 같은 노드의 승인된 agent Pod exec
 → 기존 image-agent의 inspect/pull/내용 검증
 → 전후 Node/Pod/호스트 identity 확인
 → 기존 파이프라인의 최종 전체 캐시 재검사
```

## 실제 Runtime 계약과 같은 부분

- 전용 Namespace `runtime-image-preparation`, agent label과 container `agent`를 사용합니다.
- 실행 명령은 `/usr/local/bin/image-agent --kubernetes`이며 JSON은 image·architecture·pull뿐입니다.
- K3s containerd의 같은 저장소를 확인하고, 불완전한 이미지에만 기존 agent가 pull을 수행합니다.
- Runtime 요청 등록·정책 승인·현재 readiness 등록이나 Backend operation 생성은 수행하지 않습니다.
- agent Pod가 Ready라는 사실만으로 문제 이미지의 private GHCR 인증·내용 완전성·실행 승인을 증명하지 않습니다.

## 고정 설치 파일과 권한

관리자가 승인한 정비에서 다음 두 새 파일만 준비합니다. **이 workflow는 설치하지 않습니다.**

| 고정 경로 | 내용 |
|---|---|
| `/usr/local/libexec/vm-image-pod-bridge` | 이 저장소의 `scripts/vm_pod_image_bridge.py`, root:root,0755 |
| `/etc/secure-provisioner/vm-image-pod-bridge.json` | 검수한 node/Pod identity와 경로, root:root,0600 |

`/usr/bin/python3`와 `/usr/local/bin/k3s`, root 소유·0600인
`/etc/rancher/k3s/k3s.yaml`이 필요합니다. 별도 Python 패키지·가상환경은 필요하지 않습니다.
브리지는 절대 Python 경로와 isolated mode로 실행하며 사용자 Python 환경을 상속하지 않습니다.
모든 파일·상위 디렉터리는 root 소유이고 group/other 쓰기와 symlink를 거절합니다.

설치 전에 파일·폴더가 이미 있는지 확인합니다. 기존 설치·권한·설정은 임의 덮어쓰기하지
않으며 폴더 생성이 필요하면 관리자와 조율합니다. 리뷰한 소스·파일 checksum과 root 설정을
확인한 뒤에만 다음 설치를 수행합니다. `curl | sudo ...` 형태로 실행하지 않습니다.

```bash
sudo install -o root -g root -m 0755 vm_pod_image_bridge.py /usr/local/libexec/vm-image-pod-bridge
sudo install -o root -g root -m 0600 vm-image-pod-bridge.json /etc/secure-provisioner/vm-image-pod-bridge.json
```

SSH 정비 계정에는 가능하면 다음 **정확한 명령 2개**의 비대화식 sudo만 허용합니다.
임의 kubectl·Pod exec·셸·kubeconfig 읽기 권한을 이 도구의 필요 권한으로 간주하지 않습니다.

```text
sudo -n /usr/local/libexec/vm-image-pod-bridge preflight
sudo -n /usr/local/libexec/vm-image-pod-bridge prepare
```

## root 설정과 노드 목록

설정 예시의 값은 실제 관측값으로 바꾸고 별도 보안 경로로 확인합니다. kubeconfig·토큰·
환경변수·명령 인자는 설정에 추가하지 않습니다. 다음 필드 이외에는 거절합니다.

```json
{
  "schema_version": 1,
  "node_name": "approved-node.example.internal",
  "node_uid": "00000000-0000-4000-8000-000000000001",
  "machine_id": "dddddddddddddddddddddddddddddddd",
  "boot_id": "00000000-0000-4000-8000-000000000003",
  "architecture": "AMD64",
  "agent_pod_name": "runtime-image-agent-example",
  "agent_pod_uid": "00000000-0000-4000-8000-000000000002",
  "agent_image": "ghcr.io/msg-ctf/secure-provisioner-image-agent@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "agent_image_id": "ghcr.io/msg-ctf/secure-provisioner-image-agent@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "image_fs_path": "/var/lib/rancher/k3s/agent/containerd"
}
```

`nodes.json`의 해당 노드는 기존 SSH·target·예산·identity 필드를 유지하되 다음을 적용합니다.

- `agent_transport`는 `kubernetes`로 명시합니다. 기본 호스트형과 섞어 사용할 수 있습니다.
- `agent_sha256`은 넣지 않습니다. 대신 root 설정과 같은 node_name·agent_pod_name·
  agent_pod_uid·agent_image·agent_image_id를 추가합니다.
- 브리지 소스 checksum은 계획에 포함되고 preflight 결과와 대조합니다.
- Node UID와 Runtime/Broker target ID를 같은 값으로 추정하지 않습니다. target은 승인된 대응을 사용합니다.
- image와 imageID는 같은 Runtime agent package의 정확한 digest여야 합니다. OCI index와 실행 manifest가
  다른 경우 각각 검토한 값을 명시합니다. `containerd://...` config ID를 manifest로 추정하지 않습니다.

VM 부팅 후 실제 machine/boot·노드 UID를 확인합니다. Pod가 교체되면 이름뿐 아니라 UID도
다시 승인합니다. 브리지가 새 Pod나 boot를 자동 신뢰하지 않습니다. 현재 관측값은 이전 관측과
구분해 기록하며 과거 Ready를 현재 실행 권한으로 재사용하지 않습니다.

## 실행 경계

우선 `{}` 입력의 preflight로 연결·identity·공간만 확인할 수 있습니다. 그 후 실제 운영
release·전체 digest·승인 target·예산을 확정하고 기존 `scripts.vm_image_prefetch`의
plan/approved SHA/apply 순서를 따릅니다. 이 어댑터 때문에 기존 출처·승인·만료·디스크·
단일 순차 실행·최종 재검사 조건을 제거하지 않습니다. 호스트형으로 자동 fallback하지 않습니다.

리뷰한 파일과 설정의 설치 후, 다운로드 없는 초기 확인 명령은 다음과 같습니다.

```bash
printf '%s' '{}' | sudo -n /usr/local/libexec/vm-image-pod-bridge preflight
```

첫 정비는 GitHub에 SSH 키를 등록하지 않고 맥의 기존 CLI로 실행할 수도 있습니다.
로컬 SSH 키 경로와 비공개 JSON을 사용하며 원래 plan 승인·identity·예산 검사는 같습니다.
GitHub Actions로 옮길 때만 별도 Environment·Secret·암호화 결과 설정을 준비합니다.

브리지의 매 호출은 live Node/Ready와 host machine/boot/architecture를 대조합니다.
해당 노드·label에서 Ready agent가 정확히 하나여야 하며 이름·UID·이미지·실제 imageID·
컨테이너 Running/Ready가 고정값과 일치해야 합니다. prepare 전후에 같은 검사를 합니다.
Kubernetes exec에는 Pod UID 원자적 precondition이 없으므로 전후 검사를 전환 잠금으로
오해하지 않습니다. 동시 DaemonSet 정비를 피하고, 호출 도중 변경되면 이미 cache 작업이
일부 수행됐더라도 성공으로 기록하거나 다음 이미지로 진행하지 않습니다.

호스트 subprocess는 고정 kubeconfig와 TLS 검증을 사용하고 shell·proxy·GitHub/Python
인증 환경을 상속하지 않습니다. Node/Pod JSON은 최대1MiB, agent 출력은64KiB, 입력은4KiB,
브리지 호출 전체는115초 예산이며 API 개별 조회는 최대5초입니다. 시간이 부족하면 전체
검사를 생략하지 않고 중단합니다. 오류 본문·stderr·kubeconfig는 결과에 복사하지 않습니다.

디스크 예산과 실행 대상 승인은 기존 중앙 파이프라인에서 검수합니다. 브리지 자체는
Runtime의 실행 정책 승인·OS 강제 disk quota·SLA·Backend operation을 대신하지 않습니다.
공용 캐시 삭제·Pod 생성/삭제·active 전환·기존 Namespace/Service·NetworkPolicy 변경은 없습니다.

## 고정 소스 대조

- [Runtime의 Pod 선택·exec 요청](https://github.com/MSG-CTF/secure-provisioner/blob/a4e58014bde0ee984b3a1e2120856b5ba1947a44/internal/k3s/image_agent.go)
- [Runtime의 kubernetes mode와 node identity](https://github.com/MSG-CTF/secure-provisioner/blob/a4e58014bde0ee984b3a1e2120856b5ba1947a44/cmd/image-agent/main.go)
- [기존 agent의 내용 검증과 pull](https://github.com/MSG-CTF/secure-provisioner/blob/a4e58014bde0ee984b3a1e2120856b5ba1947a44/internal/imageprep/agent.go)

이 source 대조·모의 검사와 사용자가 전달한 메타데이터는 브리지 설치·실제 SSH·GHCR
문제 이미지 pull·현재 readiness의 독립 검증이 아닙니다. 실제 정비는 리뷰·승인 후 진행합니다.
