#!/usr/bin/env python3
"""성공한 일반 문제 발행본을 취합합니다. 노드·Registry·release는 변경하지 않습니다."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zipfile

if __package__:
    from . import audit_publication_state as publication
    from .generate_node_image_plan import generate_plan, NAME, MAX_ARTIFACT_BYTES
    from .generate_publish_bundle import COMMIT_SHA, MSGCTF_GHCR_DIGEST_IMAGE
else:
    import audit_publication_state as publication
    from generate_node_image_plan import generate_plan, NAME, MAX_ARTIFACT_BYTES
    from generate_publish_bundle import COMMIT_SHA, MSGCTF_GHCR_DIGEST_IMAGE


SCOPE = "GENERAL_LINUX_KUBERNETES"
MAX_ARCHIVE_BYTES = 16 * 1024 * 1024
EXCLUDED = {"pwn-msgdriver"}


class CollectionFailure(ValueError):
    def __init__(self, failures):
        super().__init__("전체 목록 취합을 완료하지 못했습니다")
        self.failures = failures


class UnsupportedWorkload(ValueError):
    def __init__(self, runtime_type):
        super().__init__("K3s 취합 범위 밖의 실행 방식입니다")
        self.runtime_type = runtime_type if runtime_type in ("KUBERNETES", "DOCKER", "VM") else "UNSUPPORTED"


def positive(value):
    return type(value) is int and value > 0


def download_json(artifact_id, filename):
    if not positive(artifact_id):
        raise ValueError("artifact 식별자가 올바르지 않습니다")
    # ZIP은 추출하지 않고 제한된 JSON 하나만 읽습니다. 인증 원문은 gh가 관리합니다.
    with tempfile.TemporaryFile() as stream:
        result = subprocess.run(
            ["gh", "api", f"repos/{publication.REPOSITORY}/actions/artifacts/{artifact_id}/zip"],
            stdout=stream, stderr=subprocess.PIPE, timeout=180,
        )
        if result.returncode or stream.tell() > MAX_ARCHIVE_BYTES:
            raise ValueError("artifact 다운로드를 확인하지 못했습니다")
        stream.seek(0)
        with zipfile.ZipFile(stream) as archive:
            if archive.namelist().count(filename) != 1:
                raise ValueError("artifact에 필요한 JSON이 정확히 하나 있어야 합니다")
            item = archive.getinfo(filename)
            if item.file_size > MAX_ARTIFACT_BYTES or item.flag_bits & 1:
                raise ValueError("JSON 크기 또는 ZIP 형식을 확인하세요")
            raw = archive.read(item)
    return json.loads(raw), raw


def checked_origin(meta, run):
    origin = meta.get("workflow_run")
    if (not positive(meta.get("id")) or meta.get("expired") is not False
            or not positive(meta.get("size_in_bytes")) or meta["size_in_bytes"] > MAX_ARCHIVE_BYTES
            or not isinstance(origin, dict) or not positive(run.get("id"))
            or origin.get("id") != run["id"] or origin.get("head_sha") != run.get("head_sha")
            or origin.get("head_branch") != "main" or run.get("head_branch") != "main"
            or run.get("status") != "completed" or run.get("conclusion") != "success"
            or run.get("event") not in ("push", "workflow_dispatch")):
        raise ValueError("성공한 공식 main artifact가 아닙니다")
    sha = run.get("head_sha")
    if not isinstance(sha, str) or not COMMIT_SHA.fullmatch(sha):
        raise ValueError("발행 커밋이 올바르지 않습니다")
    for key in ("repository", "head_repository"):
        if not isinstance(run.get(key), dict) or run[key].get("full_name") != publication.REPOSITORY:
            raise ValueError("공식 문제 저장소의 실행이 아닙니다")


def fetch_plan(slug, selected, *, api=publication.github, download=download_json):
    if not isinstance(selected, dict) or not positive(selected.get("id")) or not positive(selected.get("run_id")):
        raise ValueError("발행 bundle이 누락됐습니다")
    meta = api(f"actions/artifacts/{selected['id']}")
    run = api(f"actions/runs/{selected['run_id']}")
    checked_origin(meta, run)
    if (meta["id"] != selected["id"] or meta.get("name") != selected.get("name")
            or run.get("path") != ".github/workflows/challenge-validation.yml"
            or not positive(run.get("run_number")) or run["run_number"] != selected.get("registry_revision")
            or run["head_sha"] != selected.get("source_sha")
            or not isinstance(meta.get("name"), str)
            or not re.fullmatch(re.escape(f"{slug}-{run['id']}-") + r"[1-9][0-9]*-[0-9a-f]+-publish-bundle", meta["name"])):
        raise ValueError("문제·run·revision과 artifact가 일치하지 않습니다")
    artifact, raw = download(selected["id"], "artifact-v2.json")
    if (not isinstance(artifact, dict) or artifact.get("challenge_slug") != slug
            or artifact.get("registry_revision") != run["run_number"] or artifact.get("source_sha") != run["head_sha"]):
        raise ValueError("발행 JSON 출처가 일치하지 않습니다")
    result = generate_plan(artifact, hashlib.sha256(raw).hexdigest())
    if result is None:
        raise UnsupportedWorkload(artifact.get("runtime_type"))
    plan, _ = result
    return {**plan, "publish_run_id": run["id"], "publish_artifact_id": meta["id"]}


def flatten(report):
    if (not isinstance(report, dict) or report.get("schema_version") != "1.0"
            or report.get("scope") != SCOPE or report.get("repository") != publication.REPOSITORY
            or report.get("complete") is not True or report.get("plan_only") is not True
            or report.get("source_ref") != "refs/heads/main"
            or not isinstance(report.get("source_sha"), str) or not COMMIT_SHA.fullmatch(report["source_sha"])
            or not isinstance(report.get("plans"), list) or not report["plans"]):
        raise ValueError("완료된 동일 범위의 취합 목록이 필요합니다")
    indexed, slugs = {}, set()
    for plan in report["plans"]:
        if not isinstance(plan, dict):
            raise ValueError("문제별 목록 형식이 올바르지 않습니다")
        slug, arch = plan.get("challenge_slug"), plan.get("architecture")
        if (not isinstance(slug, str) or not NAME.fullmatch(slug) or slug in slugs
                or slug.startswith("koth-") or slug in EXCLUDED or arch not in ("AMD64", "ARM64")
                or plan.get("schema_version") != "1.0" or plan.get("plan_only") is not True
                or plan.get("runtime_type") != "KUBERNETES" or plan.get("source_ref") != "refs/heads/main"
                or not positive(plan.get("registry_revision")) or not positive(plan.get("publish_run_id"))
                or not positive(plan.get("publish_artifact_id"))
                or not isinstance(plan.get("source_sha"), str) or not COMMIT_SHA.fullmatch(plan["source_sha"])
                or not isinstance(plan.get("artifact_sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", plan["artifact_sha256"])
                or not isinstance(plan.get("containers"), list) or not plan["containers"]):
            raise ValueError("문제별 목록의 출처·범위가 올바르지 않습니다")
        slugs.add(slug)
        names = set()
        for item in plan["containers"]:
            if not isinstance(item, dict) or set(item) != {"name", "image"}:
                raise ValueError("컨테이너 목록에는 이름과 이미지만 허용합니다")
            name, image = item["name"], item["image"]
            if (not isinstance(name, str) or not NAME.fullmatch(name) or name in names
                    or not isinstance(image, str) or not MSGCTF_GHCR_DIGEST_IMAGE.fullmatch(image)
                    or not image.startswith(f"ghcr.io/msg-ctf/challenges/{slug}/{name}@sha256:")):
                raise ValueError("컨테이너 digest 경로가 일치하지 않습니다")
            names.add(name)
            indexed[(slug, name)] = {"challenge_slug": slug, "name": name, "architecture": arch, "image": image}
        raw = ("\n".join(item["image"] for item in sorted(plan["containers"], key=lambda item: item["name"])) + "\n").encode()
        if plan.get("image_list") != {"file": "images.txt", "sha256": hashlib.sha256(raw).hexdigest()}:
            raise ValueError("문제별 이미지 목록 checksum이 일치하지 않습니다")
    return indexed


def compare(current, previous=None):
    new = flatten(current)
    old = flatten(previous) if previous is not None else {}
    added, changed, unchanged = [], [], []
    for key, row in sorted(new.items()):
        if key not in old:
            added.append(row)
        elif old[key] == row:
            unchanged.append(row)
        else:
            changed.append({**row, "previous_image": old[key]["image"], "previous_architecture": old[key]["architecture"]})
    return {"baseline_present": previous is not None, "added": added, "changed": changed,
            "unchanged": unchanged, "no_longer_listed": [old[key] for key in sorted(old.keys() - new.keys())],
            "deletion_authorized": False}


def collect(catalog=None, previous=None, *, fetch=fetch_plan, expected_sha=None, head=None):
    catalog = publication.collect() if catalog is None else catalog
    if (not isinstance(catalog, dict) or catalog.get("repository") != publication.REPOSITORY
            or catalog.get("source_ref") != "refs/heads/main" or not isinstance(catalog.get("source_sha"), str)
            or not COMMIT_SHA.fullmatch(catalog["source_sha"]) or not isinstance(catalog.get("problems"), list)
            or not catalog["problems"]):
        raise ValueError("공식 main 문제 전체 목록이 필요합니다")
    if expected_sha is not None and catalog["source_sha"] != expected_sha:
        raise ValueError("실행 커밋과 현재 문제 main이 다릅니다")
    counts = catalog.get("counts")
    if not isinstance(counts, dict) or type(counts.get("total")) is not int or counts["total"] != len(catalog["problems"]):
        raise ValueError("전체 문제 개수가 일치하지 않습니다")
    plans, excluded, seen, failures = [], [], set(), []
    general_problems, general_dynamic = 0, 0
    for item in catalog["problems"]:
        slug = item.get("challenge_slug") if isinstance(item, dict) else None
        if not isinstance(slug, str) or not NAME.fullmatch(slug) or slug in seen:
            raise ValueError("문제 목록에 잘못된 이름이나 중복이 있습니다")
        seen.add(slug)
        if slug.startswith("koth-") or slug in EXCLUDED:
            excluded.append({"challenge_slug": slug, "reason": "OUTSIDE_GENERAL_SCOPE"})
            continue
        if type(item.get("runtime_required")) is not bool:
            raise ValueError("정적·동적 분류가 올바르지 않습니다")
        general_problems += 1
        if not item["runtime_required"]:
            excluded.append({"challenge_slug": slug, "reason": "STATIC_PROBLEM"})
            continue
        general_dynamic += 1
        if item.get("status") != "ARTIFACTS_MATCH_PROBLEM_TREE":
            failures.append({"challenge_slug": slug, "error_code": "PUBLISH_NOT_CURRENT"})
            continue
        selected = item.get("artifacts", {}).get("publish")
        if not isinstance(selected, dict) or selected.get("problem_tree_matches") is not True:
            failures.append({"challenge_slug": slug, "error_code": "PUBLISH_TREE_UNCONFIRMED"})
            continue
        try:
            plan = fetch(slug, selected)
        except UnsupportedWorkload as error:
            excluded.append({"challenge_slug": slug, "reason": "UNSUPPORTED_WORKLOAD_SCOPE", "runtime_type": error.runtime_type})
            continue
        except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError, zipfile.BadZipFile):
            failures.append({"challenge_slug": slug, "error_code": "PUBLISH_FETCH_OR_VALIDATION_FAILED"})
            continue
        if plan is None:
            excluded.append({"challenge_slug": slug, "reason": "UNSUPPORTED_WORKLOAD_SCOPE"})
        else:
            if plan.get("challenge_slug") != slug:
                raise ValueError("선택한 문제와 목록이 일치하지 않습니다")
            plans.append(plan)
    if failures:
        raise CollectionFailure(failures)
    report = {"schema_version": "1.0", "plan_only": True, "complete": True, "scope": SCOPE,
              "repository": publication.REPOSITORY, "source_ref": "refs/heads/main", "source_sha": catalog["source_sha"],
              "generated_at": datetime.now(timezone.utc).isoformat(), "plans": sorted(plans, key=lambda row: row["challenge_slug"]),
              "excluded": sorted(excluded, key=lambda row: row["challenge_slug"])}
    indexed = flatten(report)
    changes = compare(report, previous)
    report["counts"] = {"general_problems": general_problems, "general_dynamic": general_dynamic,
                        "unsupported_dynamic": general_dynamic - len(plans),
                        "selected_problems": len(plans), "images": len(indexed), "excluded_problems": len(excluded),
                        **{key: len(changes[key]) for key in ("added", "changed", "unchanged", "no_longer_listed")}}
    files = {}
    for arch in ("AMD64", "ARM64"):
        images = sorted({row["image"] for row in indexed.values() if row["architecture"] == arch})
        if images:
            files[f"images-{arch.lower()}.txt"] = ("\n".join(images) + "\n").encode()
    report["image_lists"] = {name: {"sha256": hashlib.sha256(raw).hexdigest(), "image_count": len(raw.splitlines())}
                             for name, raw in files.items()}
    if head is not None and head() != catalog["source_sha"]:
        raise ValueError("조회 도중 문제 main이 변경됐습니다")
    return report, changes, files


def fetch_previous(artifact_id, *, api=publication.github, download=download_json):
    meta = api(f"actions/artifacts/{artifact_id}")
    origin = meta.get("workflow_run")
    if not isinstance(origin, dict) or not positive(origin.get("id")):
        raise ValueError("이전 목록 출처가 없습니다")
    run = api(f"actions/runs/{origin['id']}")
    checked_origin(meta, run)
    if (meta["id"] != artifact_id or run.get("path") != ".github/workflows/node-image-prefetch.yml"
            or not isinstance(meta.get("name"), str)
            or not re.fullmatch(re.escape(f"node-image-prefetch-{run['id']}-") + r"[1-9][0-9]*", meta["name"])):
        raise ValueError("공식 취합 workflow의 이전 목록이 아닙니다")
    report, _ = download(artifact_id, "prefetch-inventory.json")
    flatten(report)
    if report["source_sha"] != run["head_sha"]:
        raise ValueError("이전 목록의 커밋이 일치하지 않습니다")
    return report


def summary(report, changes):
    counts = report["counts"]
    lines = ["# 노드 이미지 사전 다운로드 준비", "", "목록 생성 완료이며 노드 다운로드·실행 승인이 아닙니다.", "",
             f"- 일반 문제 {counts['general_problems']}개 / 동적 {counts['general_dynamic']}개 / 이 중 지원 범위 밖 {counts['unsupported_dynamic']}개",
             f"- 문제: {counts['selected_problems']}개 / 컨테이너 이미지: {counts['images']}개",
             f"- 비교 기준: {'이전 완료 목록' if changes['baseline_present'] else '최초 목록 (비교 기준 없음)'}",
             f"- 신규 {counts['added']} / 변경 {counts['changed']} / 유지 {counts['unchanged']} / 현재 목록 제외 {counts['no_longer_listed']}",
             "- 현재 목록에서 제외된 이미지도 자동 삭제하지 않습니다.", "",
             "| 문제 | 아키텍처 | revision | 이미지 수 |", "|---|---|---:|---:|"]
    for plan in report["plans"]:
        lines.append(f"| {plan['challenge_slug']} | {plan['architecture']} | {plan['registry_revision']} | {len(plan['containers'])} |")
    unsupported = [item for item in report["excluded"] if item["reason"] == "UNSUPPORTED_WORKLOAD_SCOPE"]
    if unsupported:
        lines += ["", "## 별도 실행 계약이 필요한 동적 문제", "", "| 문제 | 현재 실행 방식 |", "|---|---|"]
        lines += [f"| {item['challenge_slug']} | {item.get('runtime_type', '미확인')} |" for item in unsupported]
    lines += ["", "실제 노드 캐시·pull·HTTP 응답·Runtime 정책·Backend 등록은 별도 확인이 필요합니다.", ""]
    return "\n".join(lines)


def write_result(output, report, changes, files):
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise FileExistsError("기존 출력 경로는 덮어쓰지 않습니다")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".node-prefetch-", dir=output.parent) as temporary:
        staging = Path(temporary) / "result"
        staging.mkdir()
        for name, raw in files.items():
            (staging / name).write_bytes(raw)
        for name, value in (("prefetch-inventory.json", report), ("changes.json", changes)):
            (staging / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (staging / "summary.md").write_text(summary(report, changes), encoding="utf-8")
        staging.rename(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    baseline = parser.add_mutually_exclusive_group()
    baseline.add_argument("--previous-plan", type=Path)
    baseline.add_argument("--previous-artifact-id", type=int)
    parser.add_argument("--expected-source-sha")
    args = parser.parse_args()
    if args.output_dir.exists() or args.output_dir.is_symlink():
        print("기존 출력 경로는 덮어쓰지 않습니다", file=sys.stderr)
        return 2
    try:
        previous = None
        if args.previous_plan:
            if args.previous_plan.is_symlink() or args.previous_plan.stat().st_size > MAX_ARTIFACT_BYTES:
                raise ValueError("이전 목록 경로·크기를 확인하세요")
            previous = json.loads(args.previous_plan.read_text(encoding="utf-8"))
        elif args.previous_artifact_id is not None:
            if not positive(args.previous_artifact_id):
                raise ValueError("이전 artifact 식별자를 확인하세요")
            previous = fetch_previous(args.previous_artifact_id)
        report, changes, files = collect(previous=previous, expected_sha=args.expected_source_sha,
                                         head=lambda: publication.github("git/ref/heads/main")["object"]["sha"])
        write_result(args.output_dir, report, changes, files)
        print(json.dumps({"complete": True, "plan_only": True, "counts": report["counts"]}))
        return 0
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, RecursionError, subprocess.SubprocessError, zipfile.BadZipFile) as error:
        # 인증·입력·API 본문과 환경변수는 실패 보고서에 복사하지 않습니다.
        args.output_dir.mkdir(parents=True, exist_ok=False)
        failures = error.failures if isinstance(error, CollectionFailure) else [{"error_code": "SOURCE_OR_INPUT_INVALID"}]
        (args.output_dir / "failure-report.json").write_text(
            json.dumps({"complete": False, "plan_only": True, "status": "BLOCKED",
                        "error_code": "PREFETCH_COLLECTION_FAILED", "failures": failures}) + "\n")
        (args.output_dir / "summary.md").write_text(
            "# 사전 다운로드 목록 취합 실패\n\n완료 이미지 목록은 발행하지 않습니다.\n\n"
            + "\n".join(f"- {item.get('challenge_slug', '전체 조회')}: `{item['error_code']}`" for item in failures)
            + "\n", encoding="utf-8")
        print("목록 취합 실패: 인증·전체 발행본·비교 기준을 확인하세요", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
