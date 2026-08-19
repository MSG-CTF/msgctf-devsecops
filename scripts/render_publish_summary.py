#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path


DIGEST_IMAGE = re.compile(
    r"^[a-z0-9][a-z0-9._:-]*(?:/[a-z0-9][a-z0-9._-]*)+"
    r"@sha256:[0-9a-f]{64}$"
)


def _required_string(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def render_summary(artifact, bundle_name):
    challenge_slug = _required_string(
        artifact.get("challenge_slug"), "challenge_slug"
    )
    bundle_name = _required_string(bundle_name, "bundle_name")
    revision = artifact.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision <= 0:
        raise ValueError("revision must be a positive integer")
    if artifact.get("scan_result") != "PASS":
        raise ValueError("scan_result must be PASS")

    workload = artifact.get("workload")
    containers = workload.get("containers") if isinstance(workload, dict) else None
    if not isinstance(containers, list) or not containers:
        raise ValueError("workload.containers must be a non-empty list")

    rows = []
    for container in containers:
        if not isinstance(container, dict):
            raise ValueError("each container must be an object")
        name = _required_string(container.get("name"), "container.name")
        image = _required_string(container.get("image"), f"{name}.image")
        if not DIGEST_IMAGE.fullmatch(image):
            raise ValueError(f"{name}.image must be digest-pinned")
        repository, digest = image.rsplit("@", 1)
        rows.append(f"| {name} | `{repository}` | `{digest}` |")

    return "\n".join(
        [
            "# 문제 이미지 발행 결과",
            "",
            f"- 문제: `{challenge_slug}`",
            f"- revision: `{revision}`",
            "- 보안 검사: `PASS`",
            f"- Actions artifact: `{bundle_name}` (90일 보관)",
            "",
            "| 컨테이너 | GHCR image | OCI digest |",
            "|---|---|---|",
            *rows,
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
