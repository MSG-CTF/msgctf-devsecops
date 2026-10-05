#!/usr/bin/env python3
import argparse
import base64
import hashlib
import json
import re
import stat
import sys
import zipfile
from pathlib import Path, PurePosixPath

from scripts.package_user_files import CHALLENGE_SLUG, COMMIT_SHA, DEFAULT_MAX_FILES, DEFAULT_MAX_TOTAL_BYTES


BUCKET = "2026msg_gcs"
PROJECT = "msg-broker"
PREFIX = "participant-files"
MANIFEST_LIMIT = 1024 * 1024
ARCHIVE_LIMIT = DEFAULT_MAX_TOTAL_BYTES + MANIFEST_LIMIT


def _positive_int(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _regular_file(path, limit):
    if path.is_symlink() or not path.is_file() or not stat.S_ISREG(path.stat().st_mode):
        raise ValueError("bundle must contain regular files without symbolic links")
    if path.stat().st_size > limit:
        raise ValueError("bundle file exceeds the size limit")
    return path.read_bytes()


def _check_zip(data, details):
    import io

    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) != details["file_count"] or len(entries) > DEFAULT_MAX_FILES:
                raise ValueError("ZIP file count does not match the manifest")
            seen = set()
            total = 0
            for entry in entries:
                name = entry.filename
                path = PurePosixPath(name)
                mode = entry.external_attr >> 16
                if (
                    not name or path.as_posix() != name or path.is_absolute() or ".." in path.parts
                    or "\\" in name or ":" in name or "\x00" in name
                    or any(ord(char) < 32 for char in name) or name in seen
                    or entry.is_dir() or entry.flag_bits & 1
                    or (stat.S_IFMT(mode) not in (0, stat.S_IFREG))
                ):
                    raise ValueError("ZIP contains an unsafe entry")
                seen.add(name)
                total += entry.file_size
                if total > DEFAULT_MAX_TOTAL_BYTES:
                    raise ValueError("ZIP uncompressed size exceeds the limit")
            if total != details["uncompressed_size_bytes"]:
                raise ValueError("ZIP uncompressed size does not match the manifest")
            if archive.testzip() is not None:
                raise ValueError("ZIP checksum validation failed")
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError) as error:
        raise ValueError("ZIP validation failed") from error


def prepare_upload(bundle_dir):
    root = Path(bundle_dir).absolute()
    if any(parent.is_symlink() for parent in (root, *root.parents)):
        raise ValueError("bundle path must not contain symbolic links")
    manifest_data = _regular_file(root / "user-files.json", MANIFEST_LIMIT)
    try:
        manifest = json.loads(manifest_data)
    except (ValueError, UnicodeError) as error:
        raise ValueError("manifest JSON is invalid") from error
    if not isinstance(manifest, dict) or manifest.get("schema_version") != "1.0":
        raise ValueError("unsupported user-files schema")
    if set(manifest) != {"schema_version", "challenge_slug", "source_sha", "source_ref", "registry_revision", "user_files"}:
        raise ValueError("manifest contains unsupported fields")
    slug, sha, revision = (manifest.get(key) for key in ("challenge_slug", "source_sha", "registry_revision"))
    if not isinstance(slug, str) or not CHALLENGE_SLUG.fullmatch(slug) or len(slug) > 63:
        raise ValueError("challenge_slug is invalid")
    if not isinstance(sha, str) or not COMMIT_SHA.fullmatch(sha):
        raise ValueError("source_sha is invalid")
    if not _positive_int(revision) or manifest.get("source_ref") != "refs/heads/main":
        raise ValueError("only main bundles with a positive revision can be stored")
    details = manifest.get("user_files")
    if not isinstance(details, dict) or not isinstance(details.get("present"), bool):
        raise ValueError("user_files.present must be a boolean")
    objects = []
    key_root = f"{PREFIX}/{slug}/revisions/{revision}/{sha}"
    if details["present"]:
        if details.get("archive") != "user-files.zip":
            raise ValueError("archive must be user-files.zip")
        if set(details) != {"present", "archive", "sha256", "size_bytes", "file_count", "uncompressed_size_bytes"}:
            raise ValueError("archive metadata contains unsupported fields")
        for key in ("size_bytes", "file_count"):
            if not _positive_int(details.get(key)):
                raise ValueError("archive metadata must use positive integers")
        total_bytes = details.get("uncompressed_size_bytes")
        if isinstance(total_bytes, bool) or not isinstance(total_bytes, int) or total_bytes < 0:
            raise ValueError("uncompressed size must be a non-negative integer")
        if not isinstance(details.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", details["sha256"]):
            raise ValueError("archive SHA-256 is invalid")
        archive_data = _regular_file(root / "user-files.zip", ARCHIVE_LIMIT)
        if len(archive_data) != details["size_bytes"] or hashlib.sha256(archive_data).hexdigest() != details["sha256"]:
            raise ValueError("archive does not match its size or SHA-256")
        _check_zip(archive_data, details)
        objects.append((f"{key_root}/user-files.zip", archive_data, "application/zip"))
    elif details != {"present": False} or (root / "user-files.zip").exists():
        raise ValueError("absent bundle must contain no archive metadata or ZIP")
    # The manifest is the completion marker and must be written after the ZIP.
    objects.append((f"{key_root}/user-files.json", manifest_data, "application/json"))
    return manifest, objects


def upload_bundle(bundle_dir, *, client=None, apply=False):
    manifest, objects = prepare_upload(bundle_dir)
    report = {
        "schema_version": "1.0",
        "challenge_slug": manifest["challenge_slug"],
        "registry_revision": manifest["registry_revision"],
        "source_ref": manifest["source_ref"],
        "source_sha": manifest["source_sha"],
        "user_files": manifest["user_files"],
        "storage": {"provider": "GCS", "project": PROJECT, "bucket": BUCKET, "objects": []},
        "upload_complete": False,
        "mode": "APPLY" if apply else "DRY_RUN",
    }
    bucket = None
    if apply:
        if client is None:
            from google.cloud import storage

            client = storage.Client(project=PROJECT)
        bucket = client.bucket(BUCKET)
    for key, data, content_type in objects:
        digest = hashlib.sha256(data).hexdigest()
        item = {"object_key": key, "sha256": digest, "size_bytes": len(data), "content_type": content_type}
        if bucket is not None:
            blob = bucket.blob(key)
            blob.metadata = {"sha256": digest}
            blob.cache_control = "private, no-store"
            try:
                blob.upload_from_string(
                    data, content_type=content_type, if_generation_match=0,
                    checksum="crc32c", timeout=60,
                )
                item["status"] = "CREATED"
            except Exception as error:
                if getattr(error, "code", None) != 412:
                    raise RuntimeError("GCS upload failed; no completion receipt was issued") from None
                item["status"] = "REUSED"
            blob.reload(timeout=60)
            expected_md5 = base64.b64encode(hashlib.md5(data, usedforsecurity=False).digest()).decode("ascii")
            if (
                blob.size != len(data) or blob.md5_hash != expected_md5
                or (blob.metadata or {}).get("sha256") != digest
                or not str(blob.generation or "").isdigit() or int(blob.generation) <= 0
            ):
                raise ValueError("GCS object content or generation conflicts with this bundle")
            item["generation"] = str(blob.generation)
        report["storage"]["objects"].append(item)
    report["upload_complete"] = apply
    return report


def main():
    parser = argparse.ArgumentParser(description="참가자 파일 GCS 저장 계획 및 승인된 업로드")
    parser.add_argument("--bundle-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--apply", action="store_true", help="승인된 GCS 쓰기 실행")
    args = parser.parse_args()
    args.output.unlink(missing_ok=True)
    try:
        report = upload_bundle(args.bundle_dir, apply=args.apply)
    except Exception:
        print("참가자 파일 검증 또는 GCS 저장 실패: 완료 영수증을 발행하지 않았습니다.", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("참가자 파일 GCS " + ("업로드 완료" if report["upload_complete"] else "저장 계획 생성 완료 (업로드 없음)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
