#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path


MSGCTF_GHCR_DIGEST_IMAGE = re.compile(
    r"^ghcr\.io/msg-ctf/challenges/"
    r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?/"
    r"[a-z0-9](?:[a-z0-9._-]*[a-z0-9])?"
    r"@sha256:[0-9a-f]{64}$"
)


def _required_string(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _timing_by_container(artifact, container_names):
    evidence = artifact.get("evidence")
    containers = evidence.get("containers") if isinstance(evidence, dict) else None
    if not isinstance(containers, list):
        raise ValueError("evidence.containers must be a list")
    by_name = {}
    for container in containers:
        if not isinstance(container, dict):
            raise ValueError("each evidence container must be an object")
        name = _required_string(container.get("name"), "evidence container name")
        timing = container.get("timing")
        if not isinstance(timing, dict):
            raise ValueError(f"{name}.timing must be an object")
        values = []
        for field in ("build_seconds", "scan_seconds", "push_seconds", "total_seconds"):
            value = timing.get(field)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                raise ValueError(f"{name}.timing.{field} must be non-negative")
            values.append(float(value))
        by_name[name] = values
    if set(by_name) != set(container_names):
        raise ValueError("timing evidence must match workload containers")
    return by_name


def render_summary(artifact, bundle_name):
    challenge_slug = _required_string(
        artifact.get("challenge_slug"), "challenge_slug"
    )
    bundle_name = _required_string(bundle_name, "bundle_name")
    revision = artifact.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision <= 0:
        raise ValueError("revision must be a positive integer")
    registry_revision = artifact.get("registry_revision")
    if (
        isinstance(registry_revision, bool)
        or not isinstance(registry_revision, int)
        or registry_revision <= 0
    ):
        raise ValueError("registry_revision must be a positive integer")
    if registry_revision != revision:
        raise ValueError("registry_revision must equal revision")
    category = _required_string(artifact.get("category"), "category").lower()
    expected_profile = "PWN" if category == "pwn" else "WEB"
    isolation_profile = artifact.get("isolation_profile")
    if isolation_profile != expected_profile:
        raise ValueError("isolation_profile must match the challenge category")
    if artifact.get("scan_result") != "PASS":
        raise ValueError("scan_result must be PASS")

    workload = artifact.get("workload")
    containers = workload.get("containers") if isinstance(workload, dict) else None
    if not isinstance(containers, list) or not containers:
        raise ValueError("workload.containers must be a non-empty list")

    rows = []
    container_names = []
    for container in containers:
        if not isinstance(container, dict):
            raise ValueError("each container must be an object")
        name = _required_string(container.get("name"), "container.name")
        image = _required_string(container.get("image"), f"{name}.image")
        if not MSGCTF_GHCR_DIGEST_IMAGE.fullmatch(image):
            raise ValueError(
                f"{name}.image must be a digest-pinned MSG-CTF GHCR image"
            )
        expected_repository = f"ghcr.io/msg-ctf/challenges/{challenge_slug}/{name}"
        if not image.startswith(f"{expected_repository}@sha256:"):
            raise ValueError(
                f"{name}.image must use expected GHCR repository {expected_repository}"
            )
        repository, digest = image.rsplit("@", 1)
        container_names.append(name)
        rows.append(f"| {name} | `{repository}` | `{digest}` |")

    timing_rows = []
    for name, values in _timing_by_container(artifact, container_names).items():
        formatted = " | ".join(f"`{value:.2f}s`" for value in values)
        timing_rows.append(f"| {name} | {formatted} |")

    return "\n".join(
        [
            "# 문제 이미지 발행 결과",
            "",
            f"- 문제: `{challenge_slug}`",
            f"- revision: `{revision}`",
            f"- registry revision: `{registry_revision}`",
            f"- 격리 프로파일: `{isolation_profile}`",
            "- 보안 검사: `PASS`",
            f"- Actions artifact: `{bundle_name}` (90일 보관)",
            "",
            "| 컨테이너 | GHCR image | OCI digest |",
            "|---|---|---|",
            *rows,
            "",
            "## GHCR 공급망 소요 시간",
            "",
            "| 컨테이너 | Build/Pull | Scan | GHCR Push | Total |",
            "|---|---:|---:|---:|---:|",
            *timing_rows,
            "",
            "Runtime은 GHCR tag가 아니라 위 digest가 포함된 image reference를 사용합니다.",
            "Challenge Registry 등록 전까지 이 publish bundle은 배포 가능 사양의 전달 자료입니다.",
            "",
        ]
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", required=True, type=Path)
    parser.add_argument("--bundle-name", required=True)
    args = parser.parse_args()
    artifact = json.loads(args.artifact.read_text(encoding="utf-8"))
    print(render_summary(artifact, args.bundle_name))


if __name__ == "__main__":
    main()
