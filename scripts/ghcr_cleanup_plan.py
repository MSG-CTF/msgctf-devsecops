#!/usr/bin/env python3
"""GHCR 이미지 버전의 보존 이유와 검토 후보를 출력합니다. 삭제하지 않습니다."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote


ORGANIZATION = "MSG-CTF"
DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
PACKAGE = re.compile(r"[a-z0-9][a-z0-9._-]*(?:/[a-z0-9][a-z0-9._-]*)*\Z")
IMAGE = re.compile(r"ghcr\.io/msg-ctf/([a-z0-9][a-z0-9._/-]*)@(sha256:[0-9a-f]{64})\Z")
TEST_PACKAGES = {
    "challenges/info-valid/web", "challenges/info-valid/helper",
    "challenges/koth-template/service",
}


class InventoryRequestError(RuntimeError):
    def __init__(self, endpoint, *, http_status=None, reason="REQUEST_FAILED"):
        super().__init__("GHCR_INVENTORY_REQUEST_FAILED")
        self.http_status = http_status
        self.request_kind = "PACKAGE_VERSIONS" if "/versions?" in endpoint else "ORGANIZATION_PACKAGES"
        self.reason = reason


def safe_api_failure(endpoint, stderr):
    text = stderr.decode(errors="replace") if isinstance(stderr, bytes) else str(stderr or "")
    status = re.search(r"\bHTTP\s+([1-5][0-9]{2})\b", text)
    reason = "REQUEST_FAILED"
    for marker, code in (
        ("rate limit exceeded", "API_RATE_LIMIT_EXCEEDED"),
        ("bad credentials", "BAD_CREDENTIALS"),
        ("resource not accessible by integration", "RESOURCE_NOT_ACCESSIBLE_BY_INTEGRATION"),
        ("read:packages", "READ_PACKAGES_SCOPE_REQUIRED"),
        ("unknown flag", "CLI_UNSUPPORTED_OPTION"),
    ):
        if marker in text.lower():
            reason = code
            break
    return InventoryRequestError(endpoint, http_status=int(status.group(1)) if status else None, reason=reason)


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError("시각은 timezone을 포함한 문자열이어야 합니다")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("시각 형식이 잘못됐습니다") from error
    if result.tzinfo is None:
        raise ValueError("시각에 timezone이 필요합니다")
    return result.astimezone(timezone.utc)


def positive_int(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name}은 양의 정수여야 합니다")
    return value


def github_get_pages(endpoint):
    # gh가 keyring 또는 GH_TOKEN을 사용합니다. 인증 원문·오류 본문은 출력하지 않습니다.
    try:
        response = subprocess.run(
            ["gh", "api", endpoint, "--method", "GET", "--paginate", "--slurp"],
            capture_output=True, check=True, timeout=90,
        )
        pages = json.loads(response.stdout)
    except subprocess.CalledProcessError as error:
        raise safe_api_failure(endpoint, error.stderr) from error
    except subprocess.TimeoutExpired as error:
        raise InventoryRequestError(endpoint, reason="REQUEST_TIMED_OUT") from error
    except OSError as error:
        raise InventoryRequestError(endpoint, reason="CLI_UNAVAILABLE") from error
    except subprocess.SubprocessError as error:
        raise InventoryRequestError(endpoint, reason="CLI_REQUEST_FAILED") from error
    except ValueError as error:
        raise InventoryRequestError(endpoint, reason="INVALID_RESPONSE_JSON") from error
    if not isinstance(pages, list) or any(not isinstance(page, list) for page in pages):
        raise InventoryRequestError(endpoint, reason="INVALID_RESPONSE_SHAPE")
    return pages


def collect_inventory(*, api=github_get_pages, now=None):
    now = now or datetime.now(timezone.utc)
    pages = api(f"orgs/{ORGANIZATION}/packages?package_type=container&per_page=100")
    packages = []
    for page in pages:
        for package in page:
            name = package.get("name") if isinstance(package, dict) else None
            if not isinstance(name, str) or not PACKAGE.fullmatch(name):
                raise ValueError("GHCR package 이름이 잘못됐습니다")
            version_pages = api(
                f"orgs/{ORGANIZATION}/packages/container/{quote(name, safe='')}/versions?per_page=100"
            )
            versions = []
            for versions_page in version_pages:
                for version in versions_page:
                    if not isinstance(version, dict):
                        raise ValueError("GHCR version 형식이 잘못됐습니다")
                    versions.append({key: version.get(key) for key in (
                        "id", "name", "created_at", "updated_at", "metadata",
                    )})
            packages.append({"name": name, "versions": versions})
    return {
        "schema_version": "1.0", "organization": ORGANIZATION,
        "collected_at": now.isoformat(), "packages": packages,
    }


def build_plan(inventory, *, protected_images=(), now=None, keep_latest=3, retain_days=30):
    now = now or datetime.now(timezone.utc)
    positive_int(keep_latest, "keep_latest")
    positive_int(retain_days, "retain_days")
    if not isinstance(inventory, dict) or inventory.get("schema_version") != "1.0":
        raise ValueError("inventory schema_version은 1.0이어야 합니다")
    if inventory.get("organization") != ORGANIZATION:
        raise ValueError("MSG-CTF GHCR inventory만 허용합니다")
    collected_at = timestamp(inventory.get("collected_at"))
    if collected_at > now or now - collected_at > timedelta(hours=24):
        raise ValueError("inventory는 최근 24시간 이내 조회한 자료여야 합니다")
    packages = inventory.get("packages")
    if not isinstance(packages, list):
        raise ValueError("inventory packages는 배열이어야 합니다")
    protected = set()
    for image in protected_images:
        match = IMAGE.fullmatch(image) if isinstance(image, str) else None
        if match is None or not PACKAGE.fullmatch(match.group(1)):
            raise ValueError("보호 이미지는 MSG-CTF GHCR digest 참조여야 합니다")
        protected.add(image)

    cutoff = now - timedelta(days=retain_days)
    result = []
    seen_packages = set()
    for package in packages:
        name = package.get("name") if isinstance(package, dict) else None
        if not isinstance(name, str) or not PACKAGE.fullmatch(name) or name in seen_packages:
            raise ValueError("package 이름이 잘못됐거나 중복됐습니다")
        seen_packages.add(name)
        versions = package.get("versions")
        if not isinstance(versions, list):
            raise ValueError("package versions는 배열이어야 합니다")
        normalized = []
        seen_versions = set()
        seen_digests = set()
        for version in versions:
            if not isinstance(version, dict):
                raise ValueError("version은 객체여야 합니다")
            version_id = positive_int(version.get("id"), "version id")
            digest = version.get("name")
            if not isinstance(digest, str) or not DIGEST.fullmatch(digest):
                raise ValueError("version name은 sha256 digest여야 합니다")
            if version_id in seen_versions or digest in seen_digests:
                raise ValueError("version id 또는 digest가 중복됐습니다")
            seen_versions.add(version_id)
            seen_digests.add(digest)
            created = timestamp(version.get("created_at"))
            updated = timestamp(version.get("updated_at"))
            if created > now or updated > now or updated < created:
                raise ValueError("version 시각이 미래이거나 순서가 잘못됐습니다")
            metadata = version.get("metadata")
            container = metadata.get("container") if isinstance(metadata, dict) else None
            tags = container.get("tags") if isinstance(container, dict) else None
            if not isinstance(tags, list) or any(not isinstance(tag, str) or not tag for tag in tags):
                raise ValueError("version tags는 문자열 배열이어야 합니다")
            normalized.append((created, updated, version_id, digest, tags))
        newest = {item[2] for item in sorted(normalized, reverse=True)[:keep_latest]}
        is_test = name in TEST_PACKAGES
        is_koth = name.startswith("challenges/koth-") and not is_test
        in_scope = name.startswith("challenges/") and len(name.split("/")) == 3
        package_class = "SELF_TEST" if is_test else "KOTH" if is_koth else "CHALLENGE" if in_scope else "LEGACY_OR_PLATFORM"
        for created, updated, version_id, digest, tags in sorted(normalized, reverse=True):
            image = f"ghcr.io/msg-ctf/{name}@{digest}"
            reasons = []
            if not in_scope:
                reasons.append("OUTSIDE_CHALLENGE_SCOPE")
            if is_koth:
                reasons.append("KOTH_USAGE_UNCONFIRMED")
            if version_id in newest:
                reasons.append("LATEST_IMAGE_VERSIONS")
            if max(created, updated) >= cutoff:
                reasons.append("RECENT_ACTIVITY")
            if not tags:
                reasons.append("UNTAGGED_MANIFEST")
            if image in protected:
                reasons.append("EXPLICIT_PROTECTED_DIGEST")
            result.append({
                "package": name, "package_class": package_class,
                "version_id": version_id, "image": image, "tags": tags,
                "created_at": created.isoformat(), "updated_at": updated.isoformat(),
                "decision": "RETAIN" if reasons else "REVIEW_ONLY",
                "reasons": reasons or ["OLD_VERSION_REQUIRES_USAGE_CONFIRMATION"],
                "deletion_authorized": False,
            })
    candidates = sum(item["decision"] == "REVIEW_ONLY" for item in result)
    return {
        "schema_version": "1.0", "organization": ORGANIZATION,
        "generated_at": now.isoformat(), "inventory_collected_at": inventory["collected_at"],
        "status": "BLOCKED_PENDING_USAGE_CONFIRMATION", "deletion_enabled": False,
        "policy": {"keep_latest_image_versions": keep_latest, "retain_days": retain_days},
        "counts": {"packages": len(packages), "versions": len(result),
                   "retained_versions": len(result) - candidates, "review_candidates": candidates},
        "required_before_deletion": [
            "Backend active release·rollback digest의 최신 전체 목록",
            "Scheduler/Runtime 실행 중 인스턴스 digest의 최신 전체 목록",
            "KOTH 별도 사용·rollback digest 목록",
            "OCI index/manifest 참조 관계 확인과 관리자 승인",
        ],
        "versions": result,
    }


def render_markdown(plan):
    lines = ["# GHCR 이미지 버전 정리 검토", "", f"기준: `{plan['generated_at']}`", "",
             "실제 삭제는 수행하지 않았습니다. 후보는 사용 중이 아니라는 뜻이 아닙니다.", ""]
    if plan["status"] == "INVENTORY_FAILED":
        if "error_reason" in plan:
            lines += [f"- 요청 종류: `{plan['request_kind']}`",
                      f"- HTTP 상태: `{plan['http_status'] if plan['http_status'] is not None else '미확인'}`",
                      f"- 오류 분류: `{plan['error_reason']}`", ""]
        return "\n".join(lines + ["목록 조회 실패. 인증·package 읽기 권한을 확인한 뒤 다시 실행하세요.", ""])
    counts = plan["counts"]
    lines += [f"- 패키지 {counts['packages']}개 / 버전 {counts['versions']}개",
              f"- 보존 {counts['retained_versions']}개 / 추가 검토 {counts['review_candidates']}개",
              f"- 최신 {plan['policy']['keep_latest_image_versions']}개는 image version 기준이며 release revision 수와 같지 않습니다.", "",
              "## 검토 후보", "", "| 패키지 | version ID | digest | tag |", "|---|---:|---|---|"]
    candidates = [entry for entry in plan["versions"] if entry["decision"] == "REVIEW_ONLY"]
    for entry in candidates:
        safe_tags = ", ".join(entry["tags"]).replace("|", "\\|").replace("\n", " ").replace("\r", " ")
        lines.append(f"| {entry['package']} | {entry['version_id']} | `{entry['image'].split('@')[1]}` | {safe_tags} |")
    if not candidates:
        lines.append("| 없음 | | | |")
    lines += ["", "## 실제 삭제 전에 필요한 자료", ""]
    lines += [f"- {requirement}" for requirement in plan["required_before_deletion"]]
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, help="최근 조회한 inventory JSON. 생략하면 gh API GET으로 수집")
    parser.add_argument("--protected-images", type=Path, help="추가 보존할 digest 참조 문자열의 JSON 배열")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    try:
        inventory = json.loads(args.inventory.read_text()) if args.inventory else collect_inventory(now=now)
        protected = json.loads(args.protected_images.read_text()) if args.protected_images else []
        if not isinstance(protected, list):
            raise ValueError("보호 이미지는 JSON 배열이어야 합니다")
        plan = build_plan(inventory, protected_images=protected, now=now)
        (args.output_dir / "inventory.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n")
        exit_code = 0
    except (OSError, ValueError, RuntimeError) as error:
        # API 오류 본문이나 입력 원문을 출력하지 않습니다.
        plan = {"schema_version": "1.0", "status": "INVENTORY_FAILED",
                "generated_at": now.isoformat(), "deletion_enabled": False,
                "error_code": "GHCR_PLAN_FAILED"}
        if isinstance(error, InventoryRequestError):
            plan.update(error_code="GHCR_INVENTORY_REQUEST_FAILED", http_status=error.http_status,
                        request_kind=error.request_kind, error_reason=error.reason)
        print("GHCR 조회·입력 검증 실패: 인증, read:packages와 입력 파일을 확인하세요.", file=sys.stderr)
        exit_code = 1
    (args.output_dir / "cleanup-plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n")
    (args.output_dir / "cleanup-plan.md").write_text(render_markdown(plan))
    summary = {"status": plan["status"], "deletion_enabled": False, "counts": plan.get("counts")}
    summary.update({key: plan[key] for key in ("error_code", "http_status", "request_kind", "error_reason") if key in plan})
    print(json.dumps(summary, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
