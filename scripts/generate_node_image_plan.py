#!/usr/bin/env python3
"""발행 bundle에서 노드 사전 다운로드용 목록만 생성합니다. 노드는 변경하지 않습니다."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

if __package__:
    from .generate_publish_bundle import COMMIT_SHA, MSGCTF_GHCR_DIGEST_IMAGE
else:
    from generate_publish_bundle import COMMIT_SHA, MSGCTF_GHCR_DIGEST_IMAGE


NAME = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
MAX_ARTIFACT_BYTES = 1024 * 1024


def generate_plan(artifact, artifact_sha256):
    if not isinstance(artifact, dict):
        raise ValueError("발행 자료는 JSON 객체여야 합니다")
    if artifact.get("schema_version") not in ("2.0", "2.1"):
        raise ValueError("지원하는 발행 자료 버전이 아닙니다")
    if not isinstance(artifact_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", artifact_sha256):
        raise ValueError("원본 발행 자료의 SHA-256이 필요합니다")

    category = artifact.get("category")
    if not isinstance(category, str) or not category:
        raise ValueError("문제 분야가 필요합니다")
    if category.lower() == "koth" or artifact.get("runtime_type") != "KUBERNETES":
        return None

    slug = artifact.get("challenge_slug")
    if not isinstance(slug, str) or not NAME.fullmatch(slug) or slug.startswith("koth-"):
        raise ValueError("일반 문제 식별자가 올바르지 않습니다")
    architecture = artifact.get("architecture")
    if architecture not in ("AMD64", "ARM64"):
        raise ValueError("지원하는 Linux 아키텍처가 아닙니다")
    revision = artifact.get("registry_revision")
    if type(revision) is not int or revision <= 0:
        raise ValueError("registry_revision은 양의 정수여야 합니다")
    if type(artifact.get("revision")) is not int or artifact["revision"] != revision:
        raise ValueError("revision과 registry_revision이 일치해야 합니다")
    if artifact.get("source_ref") != "refs/heads/main":
        raise ValueError("main 발행 자료만 목록으로 만들 수 있습니다")
    source_sha = artifact.get("source_sha")
    if not isinstance(source_sha, str) or not COMMIT_SHA.fullmatch(source_sha):
        raise ValueError("원본 커밋 SHA가 올바르지 않습니다")
    if artifact.get("scan_result") != "PASS":
        raise ValueError("검사를 통과한 발행 자료가 아닙니다")

    workload = artifact.get("workload")
    containers = workload.get("containers") if isinstance(workload, dict) else None
    if not isinstance(containers, list) or not containers:
        raise ValueError("전체 컨테이너 목록이 필요합니다")
    images = {}
    for container in containers:
        if not isinstance(container, dict):
            raise ValueError("컨테이너 정보가 올바르지 않습니다")
        name = container.get("name")
        if not isinstance(name, str) or not NAME.fullmatch(name) or name in images:
            raise ValueError("컨테이너 이름이 올바르지 않거나 중복됩니다")
        image = container.get("image")
        expected = f"ghcr.io/msg-ctf/challenges/{slug}/{name}@sha256:"
        if (not isinstance(image, str) or not MSGCTF_GHCR_DIGEST_IMAGE.fullmatch(image)
                or not image.startswith(expected)):
            raise ValueError("문제와 컨테이너에 해당하는 GHCR digest 이미지가 필요합니다")
        images[name] = image

    evidence = artifact.get("evidence")
    scanned = evidence.get("containers") if isinstance(evidence, dict) else None
    if not isinstance(scanned, list) or len(scanned) != len(images):
        raise ValueError("전체 컨테이너의 검사 증거가 필요합니다")
    seen = set()
    for item in scanned:
        if not isinstance(item, dict):
            raise ValueError("컨테이너 검사 증거가 올바르지 않습니다")
        name = item.get("name")
        if not isinstance(name, str) or name not in images or name in seen:
            raise ValueError("검사 증거의 컨테이너 목록이 일치하지 않습니다")
        if (item.get("published_image") != images[name]
                or item.get("vulnerability_scan") != "PASS"
                or item.get("secret_scan") != "PASS"):
            raise ValueError("발행 이미지와 검사 증거가 일치하지 않습니다")
        seen.add(name)

    ordered = [{"name": name, "image": images[name]} for name in sorted(images)]
    image_list = ("\n".join(item["image"] for item in ordered) + "\n").encode("utf-8")
    plan = {
        "schema_version": "1.0",
        "plan_only": True,
        "challenge_slug": slug,
        "registry_revision": revision,
        "runtime_type": "KUBERNETES",
        "architecture": architecture,
        "source_ref": artifact["source_ref"],
        "source_sha": source_sha,
        "artifact_sha256": artifact_sha256,
        "containers": ordered,
        "image_list": {
            "file": "images.txt",
            "sha256": hashlib.sha256(image_list).hexdigest(),
        },
    }
    return plan, image_list


def write_plan(artifact_path, output_dir):
    artifact_path, output_dir = Path(artifact_path), Path(output_dir)
    if (artifact_path.is_symlink() or not artifact_path.is_file()
            or artifact_path.stat().st_size > MAX_ARTIFACT_BYTES):
        raise ValueError("원본 발행 자료의 경로와 크기를 확인하세요")
    with artifact_path.open("rb") as stream:
        raw = stream.read(MAX_ARTIFACT_BYTES + 1)
    if len(raw) > MAX_ARTIFACT_BYTES:
        raise ValueError("원본 발행 자료 크기가 제한을 넘었습니다")
    result = generate_plan(json.loads(raw), hashlib.sha256(raw).hexdigest())
    if result is None:
        return False
    plan, images = result
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "images.txt").write_bytes(images)
    (output_dir / "plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        generated = write_plan(args.artifact, args.output_dir)
    except (ValueError, OSError, TypeError, RecursionError):
        print("사전 다운로드 목록 생성 실패: 발행 자료와 출력 경로를 확인하세요", file=sys.stderr)
        return 2
    if generated:
        print("사전 다운로드 목록을 생성했습니다. 실제 노드 다운로드와 활성화는 실행하지 않았습니다")
    else:
        print("일반 Linux K3s 문제 범위가 아니므로 사전 다운로드 목록을 생성하지 않았습니다")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
