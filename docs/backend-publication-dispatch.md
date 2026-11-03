# 관리자 대시보드 검증·발행 연동

## 범위와 준비 상태

새 발행은 문제 저장소의 `workflow_dispatch`를 호출합니다. DevSecOps가 별도
HTTP 서버를 운영하거나 Backend DB를 수정하는 방식이 아닙니다. 이 문서와 요청
검사 도구를 포함한 DevSecOps 커밋으로 문제 저장소 caller를 갱신해야 적용됩니다.
기존 caller에 문서의 새 입력만 보내면 적용되지 않습니다.

지원 대상은 `MSG-CTF/2026_MSG_CTF`의 일반 문제입니다. 새 발행은 **dispatch가
선택한 main 커밋과 요청 SHA가 정확히 같을 때만** 허용합니다. 임의 branch나 과거
커밋을 발행하면서 main 출처로 표시하지 않습니다. main이 바뀌어 요청 SHA와
달라졌다면 빌드 전에 실패합니다. Backend는 새 SHA를 사용자에게 확인받고
다시 요청해야 하며, 요청 내용을 몰래 최신 SHA로 바꾸면 안 됩니다.

과거 성공본이 필요하면 해당 run의 기존 bundle을 수집합니다. 이 방식은
Backend의 `bundle.source_sha == workflow_run.head_sha` 검증을 유지합니다.
선택한 과거 SHA를 새로 빌드하는 기능은 이번 계약에 포함하지 않습니다.

검증·발행 성공은 Backend 등록, release 활성화, 노드 사전 다운로드나 실제
Runtime 배포 성공과 별개입니다. 이번 연결에서 이 작업들을 자동 실행하지 않습니다.

## 1. 새 발행 요청

- 저장소: `MSG-CTF/2026_MSG_CTF`로 고정합니다. 사용자 입력 저장소 URL을 그대로 호출하지 않습니다.
- Workflow: `.github/workflows/challenge-validation.yml`
- GitHub API의 workflow 식별자: `challenge-validation.yml`
- `ref`: `main`

```http
POST https://api.github.com/repos/MSG-CTF/2026_MSG_CTF/actions/workflows/challenge-validation.yml/dispatches
Accept: application/vnd.github+json
Authorization: Bearer <서버에서 보관한 GitHub 토큰>
X-GitHub-Api-Version: 2022-11-28
Content-Type: application/json
```

```json
{
  "ref": "main",
  "return_run_details": true,
  "inputs": {
    "challenge_path": "web-open-house",
    "expected_source_sha": "<main의 소문자 40자리 commit SHA>",
    "request_id": "abcdef01-2345-4678-9abc-0123456789ab",
    "source_ref": "",
    "publish_images": true,
    "runtime_smoke": false
  }
}
```

`expected_source_sha`의 예시 문자열은 실제 SHA로 바꿉니다. `challenge_path`는
한 개의 정규 slug이며 상대 경로·하위 경로가 아닙니다. 해당 폴더와 `info.yaml`
존재 여부는 기존 문제 탐색·명세 검사에서 추가 확인합니다. `request_id`는
Backend가 발급·저장한 소문자 canonical UUID이며 비밀값을 넣지 않습니다.
`source_ref`는 비우거나 `expected_source_sha`와 같은 전체 SHA만 허용합니다.

### 요청 SHA와 산출물 SHA의 관계

새 발행 요청의 필수 일치 조건은 다음과 같습니다.

```text
inputs.expected_source_sha
  == workflow_run.head_sha
  == artifact-v2.json.source_sha
```

caller의 사전 검사는 요청 SHA와 `GITHUB_SHA`를 비교해 다르면 빌드 전에
거절합니다. Backend도 최종 수집 시 독립적으로 위 세 값을 확인해야 합니다.
SHA 일치 외에 공식 저장소·workflow·main 출처, 완료·성공 상태, 문제 slug,
미만료 artifact와 GHCR digest 형식 검증도 유지합니다.

요청 SHA는 **문제 소스**의 SHA입니다. DevSecOps 도구 SHA인 `devsecops_sha`나
workflow 정의의 SHA인 `workflow_sha`와 같은 값이어야 한다는 뜻이 아닙니다.
dispatch가 선택한 main 소스가 요청과 다르면 임의로 요청을 갱신하지 않습니다.

기존 성공본 수집에는 과거의 요청 UUID나 `expected_source_sha`가 없을 수 있습니다.
이 경로에서는 `bundle.source_sha == workflow_run.head_sha`를 검증하고, 관리자가
특정 SHA를 선택했다면 그 SHA까지 같아야 합니다. 재사용할 예전 성공본을 현재
main SHA와 같게 바꾸거나 새 발행 요청으로 위장하지 않습니다.

검수만 요청할 때는 `publish_images: false`로 기존 `source_ref` 검수 기능을
사용할 수 있습니다. 이 결과는 GHCR·publish bundle 발행 성공으로 표시하지 않습니다.
요청 검사는 발행 요청에만 적용하며 일반 push·PR 검수와 자동 main 발행을 유지합니다.

## 2. 인증과 최소 권한

Backend 서버에서 조직이 승인한 GitHub App installation token 또는 해당 문제
저장소만 선택한 fine-grained PAT을 사용합니다. 토큰을 브라우저·로그·bundle에
넣거나 사용자 채팅으로 전달하지 않습니다.

| 작업 | 저장소 권한 |
|---|---|
| 새 workflow 실행 요청 | Actions: Write |
| 상태·job·로그·artifact 조회 및 다운로드만 수행 | Actions: Read |
| main SHA, 문제 경로·workflow 고정 참조 사전 조회 | Contents: Read |

새 실행용 권한과 기존 Poller의 읽기 전용 권한은 분리할 수 있습니다. 호출용
토큰에 `packages: write`, 이미지 삭제나 Contents 쓰기 권한은 필요하지 않습니다.
Workflow 내부 GHCR 발행은 기존 job별 `GITHUB_TOKEN` 권한으로 수행합니다.

## 3. 요청과 run 연결

`return_run_details: true`의 정상 응답은 HTTP 200과 다음 정보를 제공합니다.

```json
{
  "workflow_run_id": 123456789,
  "run_url": "https://api.github.com/repos/MSG-CTF/2026_MSG_CTF/actions/runs/123456789",
  "html_url": "https://github.com/MSG-CTF/2026_MSG_CTF/actions/runs/123456789"
}
```

Backend는 자기 요청 ID와 GitHub의 `workflow_run_id`를 연결해 저장합니다.
요청 ID는 Actions 실행 제목과 `publication-request-<run_id>-<attempt>` artifact의
`publication-request.json`에도 남습니다. 이 receipt는 **요청 검사 통과 기록**이며
검사·이미지 발행 성공을 뜻하지 않습니다. 기존 Poller 수집 suffix와 다르므로
publish bundle로 수집하지 않습니다. 기존 `artifact-v2.json` 형식은 바꾸지 않습니다.

receipt에는 slug, 요청 SHA, 실제 실행 SHA, 도구 SHA, run ID·attempt와
`request_key`가 포함됩니다. `request_key`는 저장소·slug·SHA·도구 SHA의
정규 JSON 해시이며 중복 판단에 사용할 수 있습니다. 서명이나 인증 수단은 아닙니다.

HTTP 204만 받았거나 응답 시간 초과로 run ID를 못 받았다면 접수 성공·실패를
단정하지 않습니다. 같은 시간대·workflow·main·실행 제목의 정확한 요청 UUID로
기존 실행을 찾고 출처를 대조합니다. 0개면 전파 지연을 고려해 재조회하고,
여러 개면 충돌로 표시합니다. 가장 최신 run을 임의 선택하거나 즉시 재호출하지 않습니다.

### 응답 유실 복구용 요청 ID

Backend는 dispatch **전에** 요청 UUID와 원래 요청 내용, 요청 시각을 저장합니다.
입력 `request_id`는 [문제 저장소 PR #99](https://github.com/MSG-CTF/2026_MSG_CTF/pull/99)의
caller에서 다음 실행 제목으로 전달됩니다.

```text
문제 요청 <challenge_slug> / <request_id>
```

API 응답을 잃으면 공식 workflow의 `workflow_dispatch` 실행 목록을 모든 필요한
페이지에서 조회합니다. main·요청 SHA·기준 시간대와 위 **전체 실행 제목**을
대조해 원래 요청을 찾습니다. UUID 부분 문자열이나 가장 최근 실행만으로 연결하지
않습니다. 요청 ID가 들어간 JSON receipt는 요청 검사 성공 후에만 생깁니다.
검사가 실패했거나 아직 시작 전이면 receipt가 없을 수 있으며, receipt가 현재
attempt에 없다는 이유만으로 새로운 dispatch를 보내지 않습니다.

정확한 run이 하나 확인되면 기존 요청에 연결하고 상태를 조회합니다. 0개인 경우
전파 지연·조회 범위 부족 가능성을 포함해 접수 여부 미확인으로 보관합니다.
여러 개가 일치하면 중복 실행 충돌로 보관하고 자동 선택·재발행하지 않습니다.
run을 찾았다는 것은 요청 추적 복구이지 발행 성공 확인이 아닙니다.
시간 제한·수동 재시도 정책과 이 영속 상태 처리는 Backend 구현 범위이며,
GitHub dispatch에 서버측 Idempotency-Key가 구현됐다는 의미가 아닙니다.

## 4. 진행 상태와 오류

```http
GET /repos/MSG-CTF/2026_MSG_CTF/actions/runs/{run_id}
GET /repos/MSG-CTF/2026_MSG_CTF/actions/runs/{run_id}/jobs
GET /repos/MSG-CTF/2026_MSG_CTF/actions/runs/{run_id}/logs
```

- `queued`, `requested`, `waiting`, `pending`: 대기
- `in_progress`: 실행 중
- `completed`와 `conclusion: success`: workflow 성공
- `failure`, `cancelled`, `timed_out`, `action_required` 등: 실패·취소·별도 조치로 구분

상태와 결론을 함께 보며 `completed`만으로 성공 처리하지 않습니다. 검수 전용
실행이나 문제 탐색만 성공한 실행도 있으므로 **성공한 run에 원하는 문제의
유효 publish bundle이 존재해야 발행 완료**로 처리합니다. 상태 조회 실패는
실행 실패가 아니라 조회 불가로 구분하고, 제한된 간격과 API rate limit을 지킵니다.

오류는 실패한 job·step 이름, Actions URL, 안전한 검사 오류 코드로 안내합니다.
원문 로그·응답·secret·FLAG를 대시보드에 무조건 복사하지 않습니다. 새 요청 검사의
대표 오류는 `SOURCE_SHA_MISMATCH`, `EXPECTED_SHA_REQUIRED`, `REQUEST_ID_REQUIRED`,
`REF_NOT_ALLOWED`, `SOURCE_REF_NOT_ALLOWED`입니다. 이 경우 빌드·GHCR 발행 전에 끝납니다.

## 5. 발행 결과와 기존 성공본 수집

```http
GET /repos/MSG-CTF/2026_MSG_CTF/actions/runs/{run_id}/artifacts?per_page=100
GET /repos/MSG-CTF/2026_MSG_CTF/actions/artifacts/{artifact_id}/zip
```

artifact 목록은 모든 페이지를 확인합니다. `*-publish-bundle`의 JSON에서
slug를 다시 검증하고 해당 문제 bundle 하나만 선택합니다. 이름의 attempt가
현재 `run_attempt`와 같다고 단정하지 않습니다. 실패 job만 재실행한 경우
이전 attempt에서 성공한 artifact가 남을 수 있습니다.

### 같은 run 재실행과 artifact 식별

| 값 | 같은 run 재실행 시 처리 |
|---|---|
| `run_id` | 원래 run ID 유지 |
| `run_number` | 유지되며 현재 caller의 `registry_revision`과 연결 |
| `head_sha` | 원래 소스 SHA 유지 |
| `run_attempt` | 재실행마다 증가. revision이나 artifact ID로 쓰지 않음 |
| `artifact_id` | 산출물 자체의 식별자. 보존된 기존 artifact는 같은 ID 유지, 새 업로드는 새 ID |

추적용으로 저장소·`run_id`·조회한 `run_attempt`·`artifact_id`·artifact 이름을
함께 기록합니다. 재수집 중복 방지는 artifact ID, 릴리스 중복 방지는
`challenge_id + registry_revision`으로 구분합니다.

```text
<slug>-<run_id>-<scope_attempt>-<nonce>-publish-bundle
```

이 이름의 `scope_attempt`는 중앙 validate job이 scope를 만들 때의 attempt입니다.
artifact가 실제로 업로드된 attempt와 같다고 보장하지 않습니다. 예를 들어
validate가 attempt 1에서 성공하고 build만 attempt 2에서 재실행되면, 뒤에서
생성된 bundle 이름에도 scope attempt 1이 남을 수 있습니다. 현재 `run_attempt`
숫자로 artifact 이름을 새로 만들어 조회하거나 이전 scope의 artifact를 일괄
거절하면 안 됩니다. receipt에도 같은 원칙을 적용합니다.

수집 시 해당 run의 artifact 모든 페이지에서 요청 slug의 후보를 찾고 artifact
메타데이터의 run ID·SHA와 bundle 안의 slug·source SHA·revision을 대조합니다.
재실행별 job 진단은 아래 API로 구분할 수 있습니다.

```http
GET /repos/MSG-CTF/2026_MSG_CTF/actions/runs/{run_id}/attempts/{attempt_number}
GET /repos/MSG-CTF/2026_MSG_CTF/actions/runs/{run_id}/attempts/{attempt_number}/jobs
```

관리자 수집·결과 조회는 검증한 bundle 후보가 하나면 그 artifact ID를 저장합니다.
여러 개면 임의 최신 선택을 하지 않고 명시적인 artifact ID 선택 또는 충돌 확인을
요구합니다. 같은 revision이 이미 등록됐다면 기존 digest·파일을 덮어쓰지 않습니다.
기존 등록본과 내용이 다르면 단순 성공으로 숨기지 않고 충돌로 분리해야 합니다.
새 내용을 정식 등록하려면 새 dispatch·새 revision을 사용합니다.

`artifact-v2.json`의 주요 값은 다음과 같습니다.

- `schema_version: 2.0`, `challenge_slug`, `registry_revision`
- `source_ref: refs/heads/main`, `source_sha`
- `workload.containers[].image`: 컨테이너별 GHCR digest 고정 참조
- `runtime_type`, `architecture`, `isolation_profile`, `resource_profile`, 선택적 healthcheck
- `scan_result: PASS`와 컨테이너별 SBOM·검사 증거

run이 공식 저장소·공식 workflow·main에서 성공했고 SHA·revision·artifact 출처가
일치하는지 확인합니다. 만료된 artifact, 태그 기반 이미지, 실패·실행 중 run의
부분 산출물은 성공본으로 수집하지 않습니다. Actions artifact의 `digest`는
artifact ZIP의 체크섬이며 컨테이너 이미지 digest가 아닙니다.

기존 성공본 수집은 이 GET 경로만 사용하며 dispatch·빌드·GHCR push를 하지 않습니다.
원하는 SHA와 같은 성공본이 없다면 임의의 최신 성공본으로 대체하지 않습니다.
원본 SHA가 달라도 문제 Git tree가 같아 재사용하려면 별도 승인 기준이 필요합니다.
만료되어 수집할 수 없을 때도 자동 재빌드하지 않고 별도 복구·발행 요청으로 구분합니다.

참가자 파일은 별도 `*-user-files-bundle`의 manifest·ZIP을 기존 Backend Poller가
수집하고 Backend가 저장합니다. 이 연결에서 CI 직접 GCS 업로드는 켜지 않습니다.
정적 문제는 이미지 publish bundle이 없을 수 있으므로 참가자 파일 발행 성공과 구분합니다.

## 6. 중복·재시도와 버전 적용

GitHub dispatch 자체에는 이 요청을 한 번만 실행하는 DB 트랜잭션이 없습니다.
`request_id`나 concurrency를 넣었다고 exactly-once 발행이 완성되는 것은 아닙니다.
Backend는 다음을 구현·확인해야 합니다.

1. 요청 ID에 유일성 제약을 두고 같은 ID·같은 내용은 기존 run을 반환합니다. 같은 ID·다른 내용은 거절합니다.
2. 저장소·slug·SHA·도구 버전이 같은 진행 요청은 재사용하고 중복 dispatch를 하지 않습니다.
3. 응답 유실 시 재조회로 접수 여부를 확인한 뒤 재시도 여부를 결정합니다. 미확인 상태를 실패로 단정하지 않습니다.
4. 이미 성공한 bundle이 있으면 수집만 합니다. 재검사 정책상 새 발행이 필요하면 사용자에게 명시합니다.
5. 실패 원인이 수정되어 새로 발행할 때는 새 요청 UUID·새 run을 사용합니다. 새 run의 `run_number`가 새 revision입니다.
6. 동일 run 재실행은 revision이 같습니다. 이미 등록된 revision에 다른 digest나 파일을 덮어쓰지 않습니다.

문제 저장소의 새 수동 발행 concurrency는 문제·요청 UUID로 분리하고 실행 중
취소를 끕니다. 다른 문제 요청이 기존 발행을 취소하지 않습니다. GitHub
concurrency는 영속 FIFO 큐가 아니므로 동일 문제의 여러 갱신을 순서대로
접수할 필요가 있다면 Backend 큐·잠금으로 관리합니다.

Backend의 같은 `challenge_id + registry_revision` 중복 처리와 artifact ID 기반
재수집 방지도 유지합니다. workflow 발행 완료와 release 등록, 관리자 active
전환을 대시보드에서 분리합니다. 발행 성공만으로 기존 인스턴스를 교체하지 않습니다.

## 적용과 검증 순서

1. DevSecOps의 요청 검사 도구·테스트·문서를 리뷰합니다.
2. 문제 저장소 caller의 고정 SHA와 `devsecops_ref`를 같은 승인 커밋으로 갱신합니다.
3. caller의 실제 shell·요청 검사 회귀 테스트와 중앙 CI를 확인하고 PR 리뷰 후 병합합니다.
4. Backend가 인증·요청 DB·상태 조회를 연결한 뒤 승인된 문제 한 개로 새 발행과 기존 성공본 수집을 구분해 검증합니다.
5. 요청 SHA 불일치·중복 클릭·응답 유실·실패 후 재시도·정확한 artifact 선택을 함께 확인합니다.

운영용 관리자 새 발행 요청은 [문제 저장소 PR #99](https://github.com/MSG-CTF/2026_MSG_CTF/pull/99)
caller 적용과 Backend 연결 검증 전까지
비활성으로 유지합니다. 기존 성공본 GET 수집과 기존 main push CI의 동작을
끈다는 뜻은 아닙니다. 이 문서 보완은 입력·검사 코드 변경이 아니므로 #99의
승인된 도구 SHA 참조 7곳을 다시 바꾸지 않습니다.

이번 코드 검증은 실제 관리자 버튼 호출, 운영 토큰 권한, 새 GHCR 발행이나
노드 다운로드의 완료 증거가 아닙니다. 이 검증을 위해 전체 문제를 재발행하지 않습니다.

## 공식 API 근거

- [Workflow dispatch와 권한](https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event)
- [Dispatch 응답의 run ID](https://github.blog/changelog/2026-02-19-workflow-dispatch-api-now-returns-run-ids/)
- [Workflow 상태·job·로그](https://docs.github.com/en/rest/actions/workflow-runs)
- [Actions artifact 조회·다운로드](https://docs.github.com/en/rest/actions/artifacts)
- [재실행의 원래 SHA·ref 유지](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/re-run-workflows-and-jobs)
- [run ID·number·attempt 정의](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts)
