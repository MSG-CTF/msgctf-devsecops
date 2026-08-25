#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path


DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
DIGEST_IMAGE = re.compile(
    r"^[a-z0-9][a-z0-9._:-]*(?:/[a-z0-9][a-z0-9._-]*)+"
    r"@sha256:[0-9a-f]{64}$"
)
TIMING_FIELDS = (
    "build_seconds",
    "scan_seconds",
    "push_seconds",
    "total_seconds",
)


def _clean_string(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _validate_sbom(evidence_root, relative_path, container_name):
    evidence_root = Path(evidence_root).resolve()
    sbom_path = (evidence_root / relative_path).resolve()
    try:
        sbom_path.relative_to(evidence_root)
    except ValueError as error:
        raise ValueError(f"{container_name}.SBOM must stay inside the bundle") from error
    if not sbom_path.is_file():
        raise ValueError(f"{container_name}.SBOM file does not exist")
    try:
        sbom = json.loads(sbom_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"{container_name}.SBOM must be valid JSON") from error
    if (
        not isinstance(sbom, dict)
        or sbom.get("bomFormat") != "CycloneDX"
        or not isinstance(sbom.get("specVersion"), str)
        or not sbom["specVersion"]
    ):
        raise ValueError(f"{container_name}.SBOM must be a CycloneDX document")


def _validate_timing(raw, container_name):
    if not isinstance(raw, dict):
        raise ValueError(f"{container_name}.timing must be an object")
    timing = {}
    for field in TIMING_FIELDS:
        value = raw.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            raise ValueError(f"{container_name}.timing.{field} must be non-negative")
        timing[field] = float(value)
    expected_total = round(
        timing["build_seconds"]
        + timing["scan_seconds"]
        + timing["push_seconds"],
        3,
    )
    if abs(timing["total_seconds"] - expected_total) > 0.001:
        raise ValueError(
            f"{container_name}.timing.total_seconds must equal phase durations"
        )
    return timing


def _validated_results(metadata, results, evidence_root):
    expected = [container["name"] for container in metadata["containers"]]
    if not isinstance(results, list):
        raise ValueError("container results must be a list")
    by_name = {}
    for result in results:
        if not isinstance(result, dict):
            raise ValueError("each container result must be an object")
        name = _clean_string(result.get("name"), "container result name")
        if name in by_name:
            raise ValueError("container result names must be unique")
        by_name[name] = result
    if set(by_name) != set(expected):
        raise ValueError("container result set must exactly match metadata")

    validated = {}
    for name in expected:
        result = by_name[name]
        image = _clean_string(result.get("image"), f"{name}.image")
        if not DIGEST_IMAGE.fullmatch(image):
            raise ValueError(f"{name}.image must be digest-pinned")
        source_digest = _clean_string(
            result.get("source_digest"),
            f"{name}.source_digest",
        )
        if not DIGEST.fullmatch(source_digest):
            raise ValueError(f"{name}.source_digest must be a sha256 digest")
        if result.get("scan_result") != "PASS":
            raise ValueError(f"{name}.scan_result must be PASS")
        sbom = _clean_string(result.get("sbom"), f"{name}.SBOM")
        sbom_path = Path(sbom)
        if (
            sbom_path.is_absolute()
            or ".." in sbom_path.parts
            or not sbom.endswith(".cdx.json")
        ):
            raise ValueError(f"{name}.SBOM must be a relative CycloneDX JSON path")
        _validate_sbom(evidence_root, sbom, name)
        timing = _validate_timing(result.get("timing"), name)
        validated[name] = {
            "image": image,
            "source_digest": source_digest,
            "sbom": sbom,
            "scan_result": "PASS",
            "timing": timing,
        }
    return validated


def generate_bundle(metadata, results, source_ref, revision, evidence_root):
    if isinstance(revision, bool) or not isinstance(revision, int) or revision <= 0:
        raise ValueError("revision must be a positive integer")
    source_ref = _clean_string(source_ref, "source_ref")
    validated_results = _validated_results(metadata, results, evidence_root)

    workload_containers = []
    evidence_containers = []
    for container in metadata["containers"]:
        result = validated_results[container["name"]]
        workload_containers.append(
            {
                "name": container["name"],
                "image": result["image"],
                "ports": [
                    {"port": port, "public": container["expose"]}
                    for port in container["ports"]
                ],
            }
        )
        evidence_containers.append(
            {
                "name": container["name"],
                "source_digest": result["source_digest"],
                "published_image": result["image"],
                "sbom": result["sbom"],
                "vulnerability_scan": "PASS",
                "secret_scan": "PASS",
                "timing": result["timing"],
            }
        )

    workload = {"containers": workload_containers}
    if "healthcheck" in metadata:
        workload["healthcheck"] = metadata["healthcheck"]

    artifact = {
        "schema_version": "2.0",
        "challenge_slug": metadata["challenge_slug"],
        "revision": revision,
        "name": metadata["name"],
        "category": metadata["category"],
        "runtime_type": metadata["runtime_type"],
        "architecture": metadata["architecture"],
        "workload": workload,
        "resource_profile": metadata["resource_profile"],
        "source_ref": source_ref,
        "scan_result": "PASS",
        "evidence": {"containers": evidence_containers},
    }
    registry_publish = {
        "schema_version": "1.0",
        "operation": "publish_revision",
        "challenge_slug": metadata["challenge_slug"],
        "revision": revision,
        "activate": True,
        "name": metadata["name"],
        "category": metadata["category"],
        "runtime_type": metadata["runtime_type"],
        "architecture": metadata["architecture"],
        "workload": workload,
        "resource_profile": metadata["resource_profile"],
        "source_ref": source_ref,
        "preconditions": {
            "all_images_digest_pinned": True,
            "all_scans_passed": True,
            "all_sboms_present": True,
        },
        "retention": {"protect_running_revisions": True},
    }
    return {"artifact": artifact, "registry_publish": registry_publish}


def _load_results(results_dir):
    result_files = sorted(Path(results_dir).rglob("container-result.json"))
    if not result_files:
        raise ValueError("no container-result.json files were found")
    return [
        json.loads(result_file.read_text(encoding="utf-8"))
        for result_file in result_files
    ]


def _write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--results-dir", required=True, type=Path)
    parser.add_argument("--source-ref", required=True)
    parser.add_argument("--revision", required=True, type=int)
    parser.add_argument("--artifact-output", required=True, type=Path)
    parser.add_argument("--registry-output", required=True, type=Path)
    args = parser.parse_args()

    metadata = json.loads(args.metadata.read_text(encoding="utf-8"))
    bundle = generate_bundle(
        metadata,
        _load_results(args.results_dir),
        args.source_ref,
        args.revision,
        args.artifact_output.parent,
    )
    _write_json(args.artifact_output, bundle["artifact"])
    _write_json(args.registry_output, bundle["registry_publish"])
    print(
        json.dumps(
            {
                "challenge_slug": bundle["artifact"]["challenge_slug"],
                "revision": bundle["artifact"]["revision"],
                "container_count": len(
                    bundle["artifact"]["workload"]["containers"]
                ),
                "scan_result": "PASS",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
