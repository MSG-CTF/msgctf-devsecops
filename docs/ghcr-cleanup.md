# GHCR 이미지 버전 정리

## 현재 실행 범위

`scripts/ghcr_cleanup_plan.py`는 package version의 보존 이유와 추가 검토 후보를
출력하는 읽기 전용 도구입니다. package 또는 version을 삭제하는 API를 구현하지
않았으며 `deletion_enabled`는 항상 `false`입니다.

GHCR package는 컨테이너 이름에 해당하는 저장 공간이고 version은 그 안의 digest
이미지입니다. 문제 하나가 여러 컨테이너를 쓰면 package가 여러 개입니다. 오래된
version을 줄여도 package 개수는 그대로일 수 있습니다.

## 기본 보존 정책

- package별 최신 image version 3개 보존. release revision 3개와 같은 의미는 아닙니다.
- 생성 또는 갱신한 지 30일 이내인 version 보존.
- 태그 없는 manifest 보존. digest로 실행 중이거나 OCI index의 하위 manifest일 수 있습니다.
- 실제 KOTH 문제의 모든 version 보존. 별도 릴리스·실행 이력 계약이 필요합니다.
- 이전 플랫폼 이미지와 `web100` 등 `challenges/<slug>/<container>` 밖의 package 보존.
- 추가 보호 digest 목록에 있는 image 보존.
- 나머지도 `REVIEW_ONLY`이며 사용 중이 아니라는 판정이 아닙니다.

`challenges/info-valid/web`, `challenges/info-valid/helper`,
`challenges/koth-template/service`는 정확한 이름으로 자체 테스트 package를
구분합니다. 이름이 비슷한 실제 KOTH를 테스트 package로 분류하지 않습니다.
테스트 package의 후보도 관리자에게 사용 여부 확인이 필요합니다.

## 실행 방법

먼저 GitHub 로그인과 package 읽기 권한을 확인합니다. 토큰 값을 로그에 출력하지
않으며 인증이 실패하면 조회 실패 보고서를 만들고 exit code 1로 종료합니다.
조회 실패를 package가 0개인 정상 결과로 취급하지 않습니다.

조회 실패 보고서에는 요청 종류, HTTP 상태와 정해진 오류 분류만 남깁니다.
API 응답 본문, 인증 헤더와 토큰 원문은 출력하지 않습니다. `403`만으로 권한
문제를 단정하지 않고 호출 제한 오류도 구분합니다. 상태 코드가 없는 CLI 실행
오류나 시간 초과 역시 별도로 기록합니다. 개인 계정 조회 성공은 Actions의
인증과 접근 범위가 동일하다는 뜻이 아닙니다.

```bash
gh auth status
gh auth refresh -h github.com -s read:packages
python3 scripts/ghcr_cleanup_plan.py --output-dir dist/ghcr-cleanup
```

Actions에서는 `ghcr-cleanup-dry-run.yml`을 수동 실행합니다. 자동 삭제나 schedule은
없으며 `contents: read`, `packages: read`만 사용합니다. 기존 package의 Actions
읽기 접근에 이 저장소가 허용되어 있어야 합니다. `GITHUB_TOKEN` 권한만 적는다고
조직 전체의 private package를 읽을 수 있는 것은 아닙니다.

결과:

```text
dist/ghcr-cleanup/
├── inventory.json
├── cleanup-plan.json
└── cleanup-plan.md
```

추가 보호 digest 목록은 JSON 문자열 배열로 전달합니다.

```bash
python3 scripts/ghcr_cleanup_plan.py \
  --protected-images protected-images.json \
  --output-dir dist/ghcr-cleanup
```

JSON 항목은 `ghcr.io/msg-ctf/challenges/<slug>/<container>@sha256:<64자리>`입니다.
단순 배열은 보존 범위를 추가할 뿐 전체 사용 목록 확보를 증명하지 않습니다.

보관한 inventory를 다시 분석할 때는 최근 24시간 자료만 허용합니다.

```bash
python3 scripts/ghcr_cleanup_plan.py \
  --inventory inventory.json \
  --protected-images protected-images.json \
  --output-dir dist/ghcr-cleanup-review
```

## 2026년 10월 5일 실제 조회

[보고서](reports/2026-10-05-ghcr-cleanup/cleanup-plan.md)와
[상세 판정](reports/2026-10-05-ghcr-cleanup/cleanup-plan.json)에 기록했습니다.

- 39개 package, 110개 version, 태그 없는 version 4개.
- 남아 있는 publish bundle metadata 61건의 source SHA와 run ID를 image tag와
  대조해 연결되는 88개 digest를 추가 보존했습니다.
- 이 tag 대조는 보수적으로 더 보존하기 위한 자료입니다. bundle JSON 본문이나
  Backend active release와 Runtime 실행 상태를 대신 검증한 것이 아닙니다.
- 최종 보존 103개, 검토 후보 7개.
- 후보 7개는 모두 오래된 `challenges/koth-template/service` 자체 테스트 version.
- 후보 version ID: `1173829039`, `1170973802`, `1165345465`, `1165326823`,
  `1165282103`, `1165202164`, `1164962537`.
- 실제 삭제 0개. 삭제 인증 권한도 추가하지 않았습니다.

보고서는 위 조회 시점의 snapshot입니다. 새 이미지 발행으로 수량이 바뀔 수
있으며 삭제 직전에 다시 조회해야 합니다.

## 리뷰 후 병합·확인 순서

리뷰에서 확인한 103개 보존·7개 검토 후보는 위 snapshot의 계산 결과이며,
후보 7개의 삭제 승인이 아닙니다. 후보는 실제 사용 확인 전까지 그대로 보존합니다.

1. 읽기 전용 도구와 workflow를 리뷰 승인 후 main에 병합합니다.
2. 아래 수동 Actions를 main에서 실행해 runner의 package 목록 조회 권한을 확인합니다.
3. 보고서와 workflow 결과를 확인하고, 예상 package가 조회 범위에 포함됐는지
   package 담당자의 목록과 대조합니다. 실행 성공만으로 조직 전체 private package
   접근을 증명하지 않습니다.
4. 403/404 또는 조회 누락이 있으면 저장소의 package Actions 읽기 접근을 확인합니다.
   조회 권한 문제를 해결하기 위해 삭제 권한이나 토큰 원문을 추가하지 않습니다.
5. Backend·Runtime·KOTH 사용 digest와 OCI 참조 확인은 별도 후속 작업입니다.

```bash
gh workflow run ghcr-cleanup-dry-run.yml \
  --repo MSG-CTF/msgctf-devsecops \
  --ref main
```

현재 PR 보완에서는 병합과 수동 Actions 권한 검증을 실행하지 않았습니다.
로컬의 개인 계정 조회 성공은 Actions의 GITHUB_TOKEN 권한 검증과 다릅니다.
보고서를 받더라도 이 PR에는 실제 삭제 기능이 없으며 이미지 삭제는 0건입니다.

## 실제 삭제 전에 받을 자료

1. Backend: active release와 rollback 대상의 정확한 GHCR digest 목록.
2. Scheduler/Runtime: 실행 중인 인스턴스와 서버 정책에서 사용하는 digest 목록.
3. KOTH 담당: 공용 배포와 rollback에 사용하는 별도 digest 목록.
4. 자체 테스트 package의 후보 7개가 사용 중이 아닌지 담당자의 확인.
5. OCI index와 하위 manifest 참조 관계 확인.

이후 새로운 inventory로 후보를 재계산하고 관리자 승인을 받아 version 단위로
삭제합니다. package 전체 삭제는 별도 결정입니다. 보호 목록과 최신 확인 없이
삭제 실행 코드를 활성화하지 않습니다. 대회 기간에는 자동 삭제를 중지하는
운영 방침도 정해야 합니다.

GitHub에 따르면 package 관리 권한과 적절한 인증 권한이 필요합니다. 읽기 권한
추가가 삭제 권한을 뜻하지 않으며, 삭제 후 복구 가능 기간에 의존해 먼저
삭제하지 않습니다.

- [GitHub Packages 삭제·복구](https://docs.github.com/en/packages/learn-github-packages/deleting-and-restoring-a-package)
- [Packages REST API](https://docs.github.com/en/rest/packages/packages)

GHCR 저장 이미지, GitHub Actions build cache, K3s/containerd 노드 cache는 서로
다릅니다. 이 도구는 GHCR inventory만 조회하며 노드 cache를 정리하지 않습니다.
