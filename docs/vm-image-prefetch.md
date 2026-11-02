# 운영 VM 이미지 사전 다운로드

이 경로는 **일반 SSH로 운영 문제 이미지 캐시를 채우는 수동 정비 작업**입니다.
새 Runtime API나 다운로드 엔진을 만들지 않습니다. 기존 Runtime image-agent의
JSON 요청·전체 내용 검증을 재사용합니다. Backend 준비 operation 등록, Runtime
readiness 등록·정책 승인, Pod 실행·삭제, active 전환·무중단 교체는 수행하지 않습니다.
Broker 후보 자격·예약·Scheduler fallback도 변경하지 않습니다.

## 실행 전 필수 검수

1. 최신 운영 선택에서 일반 Linux K3s release별 전체 컨테이너 digest를 확정합니다.
   최신 발행본을 운영 버전으로 추측하지 않습니다. 기존 버전·롤백 이미지는 보존합니다.
2. 실제 실행 후보 VM 전체와 canonical target·Node UID·machine/boot ID·architecture를
   대조합니다. Backend·Broker·Runtime의 ID를 같은 값으로 가정하지 않습니다.
3. **VM을 켠 뒤** host identity를 읽어 검수합니다. 재부팅된 VM은 이전 boot ID 승인으로
   실행하지 않습니다. 자동으로 새 identity를 신뢰하거나 기존 Node UID를 생성하지 않습니다.
4. 각 VM의 실제 image filesystem, 추가 허용량·임시/압축 해제 공간·보존 여유를 확정합니다.
   최소20% 여유와 명시한 reserve를 유지합니다. 예산은 검사 장치이지 OS 강제 quota가 아닙니다.
   한 이미지의 공간 상한도 운영자가 산정해야 합니다. 동시 정비·다른 대량 pull과 조율합니다.
5. 정적 문제는 제외합니다. The Quiet Second의 예전 접속형 이미지를 새 파일형 문제를 위해
   받지 않습니다. KOTH·Windows·DOCKER·VM과 미승인 digest를 K3s로 임의 변환하지 않습니다.
   AFTERIMAGE 등 별도 정책 검토 중인 버전은 승인 전 보류합니다.

선택 파일은24시간 이내의 운영자 승인 snapshot입니다. 이 도구가 Backend active나
전체 운영 VM의 누락 여부, Runtime 정책 승인을 독립 조회한 것은 아닙니다.
보고서 범위는 **입력한 release와 VM만**입니다. 제외 항목도 남깁니다.

## VM 설치 조건

다운로드는 기존 Runtime의 [고정 SSH 명령과 agent](https://github.com/MSG-CTF/secure-provisioner/blob/619423a35876d3e823df17b812cb0b1539001c13/docs/operations/image-preparation.md#L93)를 사용합니다.

- `/usr/local/libexec/runtime-image-agent`: 검토한 Runtime 바이너리. VM별 SHA-256을 고정합니다.
- `/etc/secure-provisioner/image-agent.json`: 실제 Node UID와 K3s binary 절대경로를 담은 기존 설정.
- `/usr/local/libexec/vm-image-cache-preflight`: 이 저장소의 `scripts/vm_cache_preflight.py`.
- `/etc/secure-provisioner/vm-prefetch.json`: `{"image_fs_path":"실제 K3s imageFS 절대경로"}`.

관리자가 사전에 승인한 설치를 수행합니다. 이 workflow는 설치 파일·서비스·기존
K3s 설정을 덮어쓰거나 재시작하지 않습니다. 준비 도구가 없으면 보류합니다.
Linux VM에 `/usr/bin/python3`가 있어야 하며, Runtime agent는 원래 저장소의 검토한
소스·빌드 결과를 사용합니다. 임의의 대체 다운로드 프로그램을 sudo로 실행하지 않습니다.
파일과 상위 디렉터리는 root 소유, group/other 쓰기 금지이며 symlink를 허용하지 않습니다.
preflight 파일은 다음과 같이 고정 경로에 설치할 수 있습니다.

```bash
sudo install -o root -g root -m 0755 scripts/vm_cache_preflight.py /usr/local/libexec/vm-image-cache-preflight
```

preflight는 machine/boot·architecture·설정의 Node UID·binary hash·디스크만 읽습니다.
Node UID는 operator-pinned 설정값이며 Kubernetes API의 독립 UID 재조회가 아닙니다.
관리자는 실제 노드 대응을 먼저 검수해야 합니다. 일반 `docker pull`은 사용하지 않습니다.
agent는 `/run/k3s/containerd/containerd.sock`, `k8s.io`에서 실제 manifest·config·layer를 확인합니다.

SSH 계정에는 가능하면 위 **고정 명령2개**의 비대화식 sudo 권한만 부여합니다.
공유 프로젝트 관리자 키를 CI에 영구 등록하지 않습니다. 개인키·GCP 계정 키·token은
채팅·commit·보고서에 넣지 않습니다. 노드의 기존 private GHCR 읽기 인증을 사용하고
registry token을 SSH 인자나 agent 입력에 전달하지 않습니다.

## 비공개 입력

`scope.json` 예시입니다. 값은 실행 당일 실제 운영 선택과 원본 발행 기록으로 채웁니다.
실제 inventory는 공개 저장소에 commit하지 않습니다.

```json
{
  "schema_version": 1,
  "selection_mode": "OPERATOR_APPROVED_ACTIVE_RELEASES",
  "inventory_complete_as_attested": true,
  "observed_at": "2026-11-02T00:00:00Z",
  "valid_until": "2026-11-02T01:00:00Z",
  "releases": [{
    "challenge_slug": "web-example",
    "release_id": "00000000-0000-4000-8000-000000000001",
    "registry_revision": 1,
    "publish_run_id": 1,
    "publish_artifact_id": 1,
    "source_sha": "원본 main 커밋 소문자40자리",
    "artifact_sha256": "원본 artifact-v2.json SHA-256 소문자64자리",
    "architecture": "AMD64",
    "policy_approved": true,
    "approved_target_ids": ["target-example"],
    "containers": [{"name":"web", "image":"ghcr.io/msg-ctf/challenges/web-example/web@sha256:실제64자리"}]
  }, {"challenge_slug":"crypto-reused-seal", "exclude_reason":"STATIC_CONVERSION"}]
}
```

정확한 release의 전체 컨테이너 세트가 공식 성공 main Actions bundle·검사 증거·checksum과
일치해야 합니다. 원본 조회에는 문제 저장소 Actions artifact 읽기 인증이 필요합니다.
정책 승인은 운영자 확인값입니다. 다운로드 자체가 실행 승인을 부여하지 않습니다.
`exclude_reason` 허용값은 STATIC_CONVERSION, KOTH, WINDOWS, NOT_APPROVED,
NOT_IN_THIS_MAINTENANCE입니다. 제외를 준비 성공으로 집계하지 않습니다.

`nodes.json`에는 schema_version1과 nodes 배열을 넣습니다. VM마다 다음 값이 필요합니다.

| 필드 | 의미 |
|---|---|
| node_id | 보고서용 안전한 별칭 |
| target_id, node_uid, machine_id, boot_id | 검수한 실제 대응과 현재 identity |
| architecture | AMD64 또는 ARM64 |
| ssh_host, ssh_port, ssh_user | 일반 SSH 주소·포트·전용 계정 |
| ssh_host_key | 별도 보안 경로로 확인한 `ssh-ed25519 BASE64` 공개 host key |
| agent_sha256 | 설치된 Runtime agent의 검토된 binary SHA-256 |
| image_fs_path | 실제 K3s containerd 데이터 filesystem 경로 |
| reserve_bytes | 보존·운영용 최소 잔여 공간 |
| max_additional_bytes | 이번 전체 정비의 추가 공간 예산 |
| per_image_workspace_bytes | 이미지 한 건의 임시·압축 해제 포함 작업 여유 |

동일 architecture의 입력 VM 전체를 각 release의 approved_target_ids가 포함해야 합니다.
한 정비 계획은 최대50개 VM·100개 release·1000개 이미지/VM 쌍까지 허용합니다.
VM 주소·Node UID·machine ID 중복이나 누락을 허용하지 않습니다. host key를 현장에서
무인증 `ssh-keyscan` 결과만으로 신뢰하거나 StrictHostKeyChecking을 끄지 않습니다.

## 로컬 실행과 결과

```bash
python3 -B -m scripts.vm_image_prefetch --scope /private/scope.json --nodes /private/nodes.json --output-dir /private/new-plan
```

기본은 GitHub 원본 대조와 계획 생성뿐이며 SSH에 접속하지 않습니다.
`plan.json`의 전체 이미지·노드·제외/보류를 검수한 뒤 표시된 plan_sha256을 승인합니다.
실제 실행은 같은 입력을 다시 검수하므로 source·VM·예산이 바뀌면 새 승인이 필요합니다.

```bash
python3 -B -m scripts.vm_image_prefetch --scope /private/scope.json --nodes /private/nodes.json --output-dir /private/new-apply --ssh-key /private/ssh-key --expected-plan-sha256 APPROVED_SHA256 --apply
```

모든 VM의 identity·도구 hash·공간을 먼저 확인한 후 한 VM·한 이미지씩 처리합니다.
캐시가 완전하면 REUSED_VERIFIED, 없거나 불완전해 pull 후 검증하면 PULLED_OR_REPAIRED입니다.
후자는 cold pull의 증거가 아닙니다. agent_prepare_seconds도 실제 registry 전송 시간만을
측정한 값이 아닙니다. 실패 시 다음 이미지로 넘어가지 않으며, 캐시 삭제·자동 retry는 없습니다.
다시 승인해 실행하면 이미 준비된 이미지를 검증·재사용할 수 있습니다.
마지막에는 전체 이미지/VM 쌍을 pull 없이 다시 검사합니다. 최종 검사에서 GC·내용 누락·
identity 변경이 발견되면 완료로 표시하지 않고 중단합니다. 최종 관측 시각도 각 쌍에 남깁니다.
검사 중 승인이 만료되면 실제 pull을 시작하지 않으며, 만료된 최종 검사를 성공으로 기록하지 않습니다.

새 출력 디렉터리는0700, plan/results/summary는0600입니다. 결과가 부분 실패해도 완료한
쌍과 실패 위치를 남깁니다. Runtime readiness·Backend operation에 결과를 등록하지 않으므로
기존 플랫폼의 별도 조회와 대조해야 합니다. 실제 Pod imageID·HTTP 접속·무중단은 후속 시험입니다.

이는 관측 당시의 캐시 보유 결과입니다. kubelet의 이미지 GC, VM 삭제·디스크 교체로
캐시가 사라질 수 있고 이 도구는 GC를 끄거나 영구 보존을 강제하지 않습니다. PWN의
이미지 준비도 gVisor·실행 격리 승인을 뜻하지 않습니다. 새 서버 자동 준비와 패치 시
자동 호출은 기존 플랫폼 연동의 후속이며 이번 수동 정비 workflow가 대신하지 않습니다.

## GitHub 수동 workflow

`.github/workflows/vm-image-prefetch.yml`은 공식 저장소 main의 수동 실행만 허용합니다.
동시 실행을 막고 실제 실행은 기본 비활성입니다. 일반 SSH에 접근 가능한 승인된 러너가
필요합니다. 이를 위해 SSH 방화벽을 인터넷 전체에 열지 않습니다. IAP/VPN 어댑터는 포함하지 않습니다.

- repo Secrets: VM_IMAGE_PREFETCH_SCOPE, VM_IMAGE_PREFETCH_NODES,
  CHALLENGE_ARTIFACT_READ_TOKEN (문제 저장소 Contents: Read + Actions: Read).
- `vm-image-prefetch` Environment Secret: VM_IMAGE_PREFETCH_SSH_KEY,
  VM_IMAGE_PREFETCH_REPORT_CERT (결과 수신자의 공개 PEM 인증서, 개인키 아님).
- Environment 변수 VM_IMAGE_PREFETCH_REPORT_CERT_SHA256: 인증서 DER SHA-256.
- repo 변수 VM_IMAGE_PREFETCH_ENABLED는 검수 전 미설정/false로 유지합니다.
- Environment에는 main 제한·필수 승인자를 설정한 뒤 사용합니다. 이 보호는 관리자가
  실제로 설정해야 하며 workflow 파일만으로 승인자가 자동 등록되는 것은 아닙니다.

먼저 apply=false로 계획 SHA를 확인합니다. 검수·접속·용량·설치가 확인된 뒤에만
승인 SHA와 apply=true로 실행합니다. 인증서는 실행 전에 fingerprint와 남은 유효기간을
확인합니다. 공개 artifact에는 집계와 암호화된 CMS 결과만 올립니다. 상세 plan/results는
수신 인증서로 AES-256-CBC CMS 암호화하고 checksum을 남기며, 원문·키는 러너에서 삭제합니다.
수신 개인키는 러너나 채팅에 전달하지 않습니다. 실제 실행은 별도 정비 일정에 승인합니다.
첫 실제 실행은 승인된 WEB1개·VM1곳으로 확인하고, 성공한 뒤 전체 정비 범위로 확대합니다.
