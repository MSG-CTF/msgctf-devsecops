#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import re
import stat
import zipfile
from pathlib import Path


COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
CHALLENGE_SLUG = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")
DEFAULT_MAX_FILES = 1000
DEFAULT_MAX_TOTAL_BYTES = 100 * 1024 * 1024


def _write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _resolve_inside_challenge(path, challenge_root):
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(challenge_root)
    except (OSError, ValueError) as error:
        raise ValueError(
            "for_user file must stay inside challenge root"
        ) from error
    return resolved


def _collect_files(for_user, challenge_root, max_files, max_total_bytes):
    files = []
    total_bytes = 0
    for directory, dirnames, filenames in os.walk(for_user, followlinks=False):
        directory = Path(directory)
        for name in sorted(dirnames):
            if (directory / name).is_symlink():
                raise ValueError("for_user must not contain a symbolic link")
        for name in sorted(filenames):
            path = directory / name
            _resolve_inside_challenge(path, challenge_root)
            if path.is_symlink():
                raise ValueError("for_user must not contain a symbolic link")
            mode = path.stat().st_mode
            if not stat.S_ISREG(mode):
                raise ValueError("for_user must contain regular files only")
            relative_path = path.relative_to(for_user)
            if relative_path.is_absolute() or ".." in relative_path.parts:
                raise ValueError("for_user file path must stay inside its directory")
            files.append((relative_path, path))
            if len(files) > max_files:
                raise ValueError("for_user file count exceeds the configured limit")
            total_bytes += path.stat().st_size
            if total_bytes > max_total_bytes:
                raise ValueError("for_user total size exceeds the configured limit")
    return sorted(files, key=lambda item: item[0].as_posix()), total_bytes


def _write_archive(archive_path, files):
    with zipfile.ZipFile(
        archive_path,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for relative_path, source_path in files:
            info = zipfile.ZipInfo(relative_path.as_posix(), (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, source_path.read_bytes())


def package_user_files(
    challenge_root,
    output_dir,
    challenge_slug,
    source_ref,
    source_sha,
    revision,
    max_files=DEFAULT_MAX_FILES,
    max_total_bytes=DEFAULT_MAX_TOTAL_BYTES,
):
    challenge_root = Path(challenge_root)
    output_dir = Path(output_dir)
    if challenge_root.is_symlink():
        raise ValueError("challenge root must not be a symbolic link")
    if not challenge_root.is_dir():
        raise ValueError("challenge root must be an existing directory")
    challenge_root = challenge_root.resolve(strict=True)
    if not CHALLENGE_SLUG.fullmatch(challenge_slug):
        raise ValueError("challenge_slug has an invalid format")
    if not isinstance(source_ref, str) or not source_ref.strip():
        raise ValueError("source_ref must be a non-empty string")
    if not COMMIT_SHA.fullmatch(source_sha):
        raise ValueError("source_sha must be a 40-character lowercase commit SHA")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision <= 0:
        raise ValueError("revision must be a positive integer")
    if max_files <= 0 or max_total_bytes <= 0:
        raise ValueError("for_user limits must be positive integers")

    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = output_dir / "user-files.zip"
    manifest_path = output_dir / "user-files.json"
    prob = challenge_root / "prob"
    if prob.is_symlink():
        raise ValueError("prob must not be a symbolic link")
    for_user = prob / "for_user"

    if for_user.is_symlink():
        raise ValueError("for_user must not be a symbolic link")
    if not for_user.exists():
        manifest = {
            "schema_version": "1.0",
            "challenge_slug": challenge_slug,
            "source_ref": source_ref.strip(),
            "source_sha": source_sha,
            "registry_revision": revision,
            "user_files": {"present": False},
        }
        archive_path.unlink(missing_ok=True)
        _write_json(manifest_path, manifest)
        return manifest
    if not for_user.is_dir():
        raise ValueError("prob/for_user must be a directory")

    files, uncompressed_size = _collect_files(
        for_user,
        challenge_root,
        max_files,
        max_total_bytes,
    )
    if not files:
        manifest = {
            "schema_version": "1.0",
            "challenge_slug": challenge_slug,
            "source_ref": source_ref.strip(),
            "source_sha": source_sha,
            "registry_revision": revision,
            "user_files": {"present": False},
        }
        archive_path.unlink(missing_ok=True)
        _write_json(manifest_path, manifest)
        return manifest

    _write_archive(archive_path, files)
    manifest = {
        "schema_version": "1.0",
        "challenge_slug": challenge_slug,
        "source_ref": source_ref.strip(),
        "source_sha": source_sha,
        "registry_revision": revision,
        "user_files": {
            "present": True,
            "archive": archive_path.name,
            "sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest(),
            "size_bytes": archive_path.stat().st_size,
            "file_count": len(files),
            "uncompressed_size_bytes": uncompressed_size,
        },
    }
    _write_json(manifest_path, manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--challenge-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--challenge-slug", required=True)
    parser.add_argument("--source-ref", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--revision", required=True, type=int)
    parser.add_argument("--max-files", type=int, default=DEFAULT_MAX_FILES)
    parser.add_argument(
        "--max-total-bytes",
        type=int,
        default=DEFAULT_MAX_TOTAL_BYTES,
    )
    args = parser.parse_args()
    manifest = package_user_files(
        args.challenge_root,
        args.output_dir,
        args.challenge_slug,
        args.source_ref,
        args.source_sha,
        args.revision,
        max_files=args.max_files,
        max_total_bytes=args.max_total_bytes,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
