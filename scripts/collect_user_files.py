#!/usr/bin/env python3
import argparse
import json
import subprocess
from pathlib import Path

from scripts.package_user_files import CHALLENGE_SLUG, COMMIT_SHA, package_user_files
from scripts.upload_user_files_gcs import upload_bundle
from scripts.validate_info_spec import validate_spec


def collect_user_files(source_root, output_dir, source_sha, revision):
    source_root, output_dir = Path(source_root), Path(output_dir)
    if source_root.is_symlink() or not source_root.is_dir():
        raise ValueError("problem source must be a directory without a symbolic link")
    source_root = source_root.resolve()
    if not isinstance(source_sha, str) or not COMMIT_SHA.fullmatch(source_sha):
        raise ValueError("source SHA must be an exact commit")
    commit = subprocess.run(
        ["git", "-C", str(source_root), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "-C", str(source_root), "status", "--porcelain", "--untracked-files=all", "--ignored=matching"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    if commit != source_sha or dirty:
        raise ValueError("collection requires a clean source checkout matching source_sha")
    main_sha = subprocess.run(
        ["git", "-C", str(source_root), "rev-parse", "refs/remotes/origin/main"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    if main_sha != source_sha:
        raise ValueError("collection source must match the fetched origin/main snapshot")
    output_dir = output_dir.resolve()
    if output_dir.is_relative_to(source_root):
        raise ValueError("collection output must be outside the problem repository")
    rows = []
    for challenge in sorted(source_root.iterdir()):
        if not challenge.is_dir() or not (challenge / "info.yaml").exists():
            continue
        if challenge.is_symlink() or not CHALLENGE_SLUG.fullmatch(challenge.name):
            raise ValueError("problem directory must be a safe name without a symbolic link")
        if (challenge / "info.yaml").is_symlink():
            raise ValueError("info.yaml must not be a symbolic link")
        metadata = validate_spec(challenge)
        destination = output_dir / challenge.name
        manifest = package_user_files(challenge, destination, challenge.name, "refs/heads/main", source_sha, revision)
        plan = upload_bundle(destination)
        (destination / "gcs-plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        rows.append({
            "challenge_slug": challenge.name,
            "is_server": metadata["is_server"],
            "present": manifest["user_files"]["present"],
            "file_count": manifest["user_files"].get("file_count", 0),
            "uncompressed_size_bytes": manifest["user_files"].get("uncompressed_size_bytes", 0),
            "upload_complete": False,
        })
    if not rows:
        raise ValueError("no problem info.yaml files were found")
    report = {
        "source_sha": source_sha, "source_ref": "refs/heads/main",
        "registry_revision": revision, "mode": "DRY_RUN",
        "upload_complete": False, "problem_count": len(rows),
        "with_files": sum(row["present"] for row in rows),
        "without_files": sum(not row["present"] for row in rows),
        "problems": rows,
        "limitations": ["No Docker build or image scan was executed.", "No GCS object or Backend record was created.", "Revision is a collection plan only and is not a registered release."]
    }
    (output_dir / "collection-plan.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description="main 문제 전체 참가자 파일 검사와 GCS 저장 계획")
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--revision", required=True, type=int)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "collection-plan.json").unlink(missing_ok=True)
    try:
        report = collect_user_files(args.source_root, args.output_dir, args.source_sha, args.revision)
    except Exception:
        print("전체 문제 참가자 파일 검사 실패: 완료된 수집 보고서를 발행하지 않았습니다.")
        return 1
    print(f"문제 {report['problem_count']}개: 파일 있음 {report['with_files']}개 / 없음 {report['without_files']}개 (GCS 업로드 없음)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
