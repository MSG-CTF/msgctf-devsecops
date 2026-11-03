#!/usr/bin/env python3
"""현재 문제 폴더와 성공한 main 발행 산출물을 읽기 전용으로 대조합니다."""

from __future__ import annotations

import argparse
import base64
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys

import yaml


REPOSITORY = "MSG-CTF/2026_MSG_CTF"
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")
FIRST_PUBLICATION = "2026-10-05T00:00:00Z"


def github(path):
    result = subprocess.run(
        ["gh", "api", f"repos/{REPOSITORY}/{path}"],
        capture_output=True, text=True, timeout=60, check=False,
    )
    if result.returncode:
        # API 오류 본문이나 인증 관련 출력은 보고서에 복사하지 않습니다.
        raise ValueError("GitHub 읽기 실패: 인증·권한·네트워크를 확인하세요")
    return json.loads(result.stdout)


def pages(path, key):
    result = []
    for page in range(1, 101):
        separator = "&" if "?" in path else "?"
        rows = github(f"{path}{separator}per_page=100&page={page}")[key]
        result.extend(rows)
        if len(rows) < 100:
            return result
    raise ValueError("페이지 한도를 초과해 전체 조회를 확인하지 못했습니다")


def artifact_kind(name, slug):
    prefix = f"{slug}-"
    if not name.startswith(prefix):
        return None
    suffix = name[len(prefix):]
    match = re.fullmatch(r"[0-9]+-[0-9]+-[0-9a-f]+-(publish|user-files)-bundle", suffix)
    return match.group(1) if match else None


def compare_problem(slug, runtime_required, tree_sha, candidates, source_trees):
    selected = {}
    rejected = []
    for item in sorted(candidates, key=lambda row: (row["registry_revision"], row["created_at"], row["id"]), reverse=True):
        kind = artifact_kind(item["name"], slug)
        if kind is None:
            continue
        if item["expired"] or item["run_status"] != "completed" or item["run_conclusion"] != "success":
            rejected.append({"artifact_id": item["id"], "run_id": item["run_id"], "expired": item["expired"], "conclusion": item["run_conclusion"]})
            continue
        if kind not in selected:
            source_tree = source_trees.get(item["source_sha"], {}).get(slug)
            selected[kind] = {**item, "problem_tree_matches": source_tree == tree_sha and source_tree is not None}
    required = {"user-files", "publish"} if runtime_required else {"user-files"}
    if not required.issubset(selected):
        status = "MISSING_SUCCESSFUL_ARTIFACT"
    elif any(not selected[kind]["problem_tree_matches"] for kind in required):
        status = "PROBLEM_SOURCE_CHANGED"
    else:
        status = "ARTIFACTS_MATCH_PROBLEM_TREE"
    return {
        "challenge_slug": slug, "runtime_required": runtime_required,
        "current_problem_tree": tree_sha, "status": status,
        "artifacts": selected, "rejected_artifacts": rejected,
    }


def collect():
    source_sha = github("git/ref/heads/main")["object"]["sha"]
    tree = github(f"git/trees/{source_sha}?recursive=1")
    if tree.get("truncated"):
        raise ValueError("문제 트리 조회가 잘려 전체 목록을 확인하지 못했습니다")
    info_entries = [item for item in tree["tree"] if re.fullmatch(r"[^/]+/info\.yaml", item["path"])]
    if not info_entries:
        raise ValueError("검사할 문제 info.yaml을 찾지 못했습니다")
    root = github(f"git/trees/{source_sha}")
    current = {item["path"]: item["sha"] for item in root["tree"] if item["type"] == "tree"}
    catalog = []
    for item in info_entries:
        slug = item["path"].split("/")[0]
        if not SLUG.fullmatch(slug):
            raise ValueError("지원하지 않는 문제 폴더 이름입니다")
        blob = github(f"git/blobs/{item['sha']}")
        if blob.get("size", 0) > 1024 * 1024:
            raise ValueError("info.yaml 조회 크기를 초과했습니다")
        spec = yaml.safe_load(base64.b64decode(blob["content"], validate=False))
        if not isinstance(spec, dict):
            raise ValueError("info.yaml이 객체 형식이 아닙니다")
        # FLAG·지문·환경변수·문제 소스는 출력하거나 저장하지 않습니다.
        catalog.append((slug, "deployment" in spec, current[slug]))
    runs = pages("actions/workflows/challenge-validation.yml/runs?branch=main", "workflow_runs")
    candidates = []
    for run in runs:
        if run["created_at"] < FIRST_PUBLICATION:
            continue
        if run["head_branch"] != "main":
            raise ValueError("main 이외 실행이 조회됐습니다")
        for item in pages(f"actions/runs/{run['id']}/artifacts", "artifacts"):
            if not item["name"].endswith(("-publish-bundle", "-user-files-bundle")):
                continue
            origin = item.get("workflow_run", {})
            if origin.get("id", run["id"]) != run["id"] or origin.get("head_sha", run["head_sha"]) != run["head_sha"]:
                raise ValueError("artifact와 실행의 출처가 일치하지 않습니다")
            candidates.append({
                "id": item["id"], "name": item["name"], "expired": item["expired"],
                "created_at": item["created_at"], "run_id": run["id"],
                "registry_revision": run["run_number"], "source_sha": run["head_sha"],
                "run_status": run["status"], "run_conclusion": run["conclusion"],
            })
    source_trees = {source_sha: current}
    for sha in sorted({item["source_sha"] for item in candidates}):
        if sha not in source_trees:
            source_trees[sha] = {item["path"]: item["sha"] for item in github(f"git/trees/{sha}")["tree"] if item["type"] == "tree"}
    problems = [compare_problem(slug, dynamic, sha, candidates, source_trees) for slug, dynamic, sha in sorted(catalog)]
    return {
        "checked_at": datetime.now(timezone.utc).isoformat(), "repository": REPOSITORY,
        "source_sha": source_sha, "source_ref": "refs/heads/main",
        "first_publication_included": FIRST_PUBLICATION,
        "counts": {"total": len(problems), "dynamic": sum(item["runtime_required"] for item in problems), "static": sum(not item["runtime_required"] for item in problems), "statuses": dict(Counter(item["status"] for item in problems))},
        "limitations": ["지정된 기준일 이전 전체 이력은 조회 범위가 아님", "문제 폴더 밖 공통 설정 변경은 별도 확인 필요", "ZIP 본문·bundle 내용·GHCR 실체·현재 취약점 DB는 미검사", "Backend 등록·Runtime 배포 완료를 의미하지 않음"],
        "problems": problems,
    }


def markdown(report):
    labels = {"MISSING_SUCCESSFUL_ARTIFACT": "성공 산출물 누락", "PROBLEM_SOURCE_CHANGED": "발행 후 문제 폴더 변경", "ARTIFACTS_MATCH_PROBLEM_TREE": "문제 폴더 일치"}
    lines = ["# 문제별 발행 대조", "", f"기준 main: `{report['source_sha']}`", "", "문제 폴더 일치는 현재 취약점 검사·이미지 pull·Backend 등록·배포 성공을 뜻하지 않습니다.", "", "| 문제 | 구분 | 대조 결과 | publish run | 참가자 파일 run |", "|---|---|---|---:|---:|"]
    for item in report["problems"]:
        artifacts = item["artifacts"]
        lines.append(f"| {item['challenge_slug']} | {'동적' if item['runtime_required'] else '정적'} | {labels[item['status']]} | {artifacts.get('publish', {}).get('run_id', '-')} | {artifacts.get('user-files', {}).get('run_id', '-')} |")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        report = collect()
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "publication-state.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (args.output_dir / "publication-table.md").write_text(markdown(report), encoding="utf-8")
    except (ValueError, KeyError, subprocess.TimeoutExpired, OSError, yaml.YAMLError):
        print("발행 이력 조회 실패: 전체 조회·입력·인증 상태를 확인하세요", file=sys.stderr)
        return 2
    print(json.dumps(report["counts"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
