#!/usr/bin/env python3
"""성공한 main 발행본의 출처를 확인하며 네트워크나 Runtime은 호출하지 않습니다."""

import argparse
import json
from pathlib import Path
import re
import sys

if __package__:
    from .runtime_api_smoke_runner import build_create_request
else:
    from runtime_api_smoke_runner import build_create_request


SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
SHA = re.compile(r"^[0-9a-f]{40}$")
MAX_JSON_BYTES = 1024 * 1024
MAX_ARCHIVE_BYTES = 16 * 1024 * 1024


def positive(value):
    return type(value) is int and value > 0


def select_source(run, pages, repository, run_id, slug):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) or not SLUG.fullmatch(slug):
        raise ValueError("저장소 또는 문제 식별자 형식이 잘못됐습니다")
    if not positive(run_id) or not isinstance(run, dict) or run.get("id") != run_id or type(run.get("id")) is not int:
        raise ValueError("발행 run ID가 일치하지 않습니다")
    if run.get("status") != "completed" or run.get("conclusion") != "success":
        raise ValueError("완료·성공한 발행 workflow만 사용할 수 있습니다")
    if run.get("path") != ".github/workflows/challenge-validation.yml" or run.get("head_branch") != "main":
        raise ValueError("공식 main 발행 workflow가 아닙니다")
    if not isinstance(run.get("event"), str) or run["event"] not in {"push", "workflow_dispatch"}:
        raise ValueError("발행 이벤트가 허용되지 않습니다")
    for field in ("repository", "head_repository"):
        full_name = run[field].get("full_name") if isinstance(run.get(field), dict) else None
        if not isinstance(full_name, str) or full_name.lower() != repository.lower():
            raise ValueError("외부 저장소의 발행본은 사용할 수 없습니다")
    if not isinstance(run.get("head_sha"), str) or not SHA.fullmatch(run["head_sha"]):
        raise ValueError("발행 commit SHA가 올바르지 않습니다")
    if not positive(run.get("run_number")) or not positive(run.get("run_attempt")):
        raise ValueError("발행 revision 또는 시도 번호가 올바르지 않습니다")
    if not isinstance(pages, list) or not pages:
        raise ValueError("전체 artifact 페이지가 필요합니다")
    artifacts = []
    total = pages[0].get("total_count") if isinstance(pages[0], dict) else None
    if type(total) is not int or total < 0:
        raise ValueError("artifact 목록 크기가 올바르지 않습니다")
    for page in pages:
        if (not isinstance(page, dict) or type(page.get("total_count")) is not int
                or page["total_count"] != total or not isinstance(page.get("artifacts"), list)):
            raise ValueError("artifact 페이지가 일치하지 않습니다")
        artifacts.extend(page["artifacts"])
    if len(artifacts) != total or any(not isinstance(item, dict) or not positive(item.get("id")) for item in artifacts):
        raise ValueError("artifact 전체 목록을 확인하지 못했습니다")
    if len({item["id"] for item in artifacts}) != len(artifacts):
        raise ValueError("artifact 페이지에 중복이 있습니다")
    name = re.compile(re.escape(f"{slug}-{run_id}-{run['run_attempt']}-") + r"[0-9a-f]+-publish-bundle$")
    matches = [item for item in artifacts if isinstance(item.get("name"), str) and name.fullmatch(item["name"])]
    if len(matches) != 1:
        raise ValueError("선택한 문제·현재 시도의 publish bundle이 정확히 하나여야 합니다")
    artifact = matches[0]
    if artifact.get("expired") is not False or not positive(artifact.get("size_in_bytes")) or artifact["size_in_bytes"] > MAX_ARCHIVE_BYTES:
        raise ValueError("만료되었거나 크기 제한을 넘긴 bundle입니다")
    origin = artifact.get("workflow_run")
    if not isinstance(origin, dict) or type(origin.get("id")) is not int or origin["id"] != run_id or origin.get("head_sha") != run["head_sha"] or origin.get("head_branch") != "main":
        raise ValueError("artifact와 발행 run 출처가 일치하지 않습니다")
    return {"repository": repository, "run_id": run_id, "artifact_id": artifact["id"],
            "artifact_name": artifact["name"], "challenge_slug": slug, "source_sha": run["head_sha"],
            "registry_revision": run["run_number"]}


def verify_bundle(artifact, selection, config):
    if not isinstance(artifact, dict) or not isinstance(selection, dict) or not isinstance(config, dict):
        raise ValueError("bundle·출처·설정은 JSON 객체여야 합니다")
    if artifact.get("schema_version") != "2.0" or artifact.get("source_ref") != "refs/heads/main":
        raise ValueError("지원하는 main 발행 bundle이 아닙니다")
    if not isinstance(selection.get("challenge_slug"), str) or not SLUG.fullmatch(selection["challenge_slug"]) or not isinstance(selection.get("source_sha"), str) or not SHA.fullmatch(selection["source_sha"]) or not positive(selection.get("registry_revision")):
        raise ValueError("검증된 출처 정보가 올바르지 않습니다")
    for field in ("challenge_slug", "source_sha", "registry_revision"):
        if artifact.get(field) != selection.get(field) or field not in selection:
            raise ValueError("bundle과 검증된 출처가 일치하지 않습니다")
    category = artifact.get("category")
    if not isinstance(category, str) or category.lower() == "koth" or artifact.get("isolation_profile") != "WEB":
        raise ValueError("이 시험은 승인된 일반 WEB 문제만 지원합니다")
    containers = artifact.get("workload", {}).get("containers") if isinstance(artifact.get("workload"), dict) else None
    if not isinstance(containers, list) or len(containers) != 1 or not isinstance(containers[0], dict):
        raise ValueError("이 시험은 승인된 단일 컨테이너만 지원합니다")
    container = containers[0]
    name = container.get("name")
    if not isinstance(name, str) or not SLUG.fullmatch(name):
        raise ValueError("컨테이너 이름이 올바르지 않습니다")
    expected = f"ghcr.io/msg-ctf/challenges/{selection['challenge_slug']}/{name}@sha256:"
    if not isinstance(container.get("image"), str) or not re.fullmatch(re.escape(expected) + r"[0-9a-f]{64}", container["image"]):
        raise ValueError("문제·컨테이너의 GHCR digest 고정 이미지가 아닙니다")
    # 기존 계약 변환기를 재사용해 PASS·revision·포트·자원·healthcheck도 확인합니다.
    build_create_request(artifact, target_id=config.get("target_id"), instance_id=config.get("instance_id"), team_id=config.get("team_id"))


def read_json(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_JSON_BYTES:
        raise ValueError("JSON 파일 경로나 크기를 확인하세요")
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    select = sub.add_parser("select")
    select.add_argument("--run", required=True, type=Path)
    select.add_argument("--pages", required=True, type=Path)
    select.add_argument("--repository", required=True)
    select.add_argument("--run-id", required=True, type=int)
    select.add_argument("--challenge-slug", required=True)
    select.add_argument("--output", required=True, type=Path)
    select.add_argument("--github-output", type=Path)
    verify = sub.add_parser("verify")
    verify.add_argument("--artifact", required=True, type=Path)
    verify.add_argument("--selection", required=True, type=Path)
    verify.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.command == "select":
            selection = select_source(read_json(args.run), read_json(args.pages), args.repository, args.run_id, args.challenge_slug)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(selection, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            if args.github_output:
                with args.github_output.open("a", encoding="utf-8") as stream:
                    stream.write(f"artifact_id={selection['artifact_id']}\n")
            print("성공한 main publish bundle의 출처를 확인했습니다")
        else:
            verify_bundle(read_json(args.artifact), read_json(args.selection), read_json(args.config))
            print("발행 bundle 출처·digest·기존 Runtime 요청 계약을 확인했습니다")
    except (ValueError, OSError, TypeError, KeyError, RecursionError):
        print("Runtime 시험 입력 검증 실패: 성공한 main 발행본·출처·지원 범위를 확인하세요", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
