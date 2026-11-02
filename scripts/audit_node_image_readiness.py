#!/usr/bin/env python3
"""Compare a publish bundle with a saved Runtime readiness response, offline."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys

if __package__:
    from .generate_node_image_plan import generate_plan, MAX_ARTIFACT_BYTES
else:
    from generate_node_image_plan import generate_plan, MAX_ARTIFACT_BYTES


MAX_TARGETS = 50
MAX_IMAGES = 32
MAX_COUNT = 2**31 - 1
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
RFC3339 = re.compile(
    r"^([0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2})"
    r"(?:\.([0-9]{1,9}))?(Z|[+-][0-9]{2}:[0-9]{2})$"
)


def _time_ns(value):
    if not isinstance(value, str):
        raise ValueError("timestamp must be RFC3339")
    matched = RFC3339.fullmatch(value)
    if matched is None or matched[3] == "-00:00":
        raise ValueError("timestamp must have a known offset")
    zone = matched[3]
    if zone != "Z" and (int(zone[1:3]) > 23 or int(zone[4:6]) > 59):
        raise ValueError("invalid timestamp offset")
    base = datetime.fromisoformat(matched[1] + ("+00:00" if zone == "Z" else zone))
    delta = base.astimezone(timezone.utc) - EPOCH
    # Keep Runtime RFC3339Nano boundaries instead of truncating to microseconds.
    return ((delta.days * 86400 + delta.seconds) * 10**9
            + int((matched[2] or "").ljust(9, "0")))


def calculate_image_set_id(architecture, images):
    canonical = {
        "schema_version": 1,
        "architecture": architecture,
        "images": sorted(set(images)),
    }
    raw = json.dumps(canonical, separators=(",", ":"), ensure_ascii=True).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _validate_targets(target_ids):
    if not isinstance(target_ids, list) or not 1 <= len(target_ids) <= MAX_TARGETS:
        raise ValueError("expected targets are required")
    seen = set()
    for target in target_ids:
        if (not isinstance(target, str) or not 1 <= len(target) <= 128
                or target.strip() != target
                or any(ord(character) < 32 or ord(character) == 127 for character in target)
                or target in seen):
            raise ValueError("invalid or duplicate expected target")
        seen.add(target)
    return seen


def _observation(entry, now_ns, max_age_seconds):
    result = {
        "target_id": entry["target_id"],
        "state": "UNKNOWN",
        "reason": "NO_OBSERVATION",
        "ready_node_count_as_reported": entry["ready_node_count"],
        "eligible_node_count_as_reported": entry["eligible_node_count"],
        "observed_at": None,
        "valid_until": None,
    }
    observed, until = entry.get("observed_at"), entry.get("valid_until")
    if observed is None or until is None:
        return result
    try:
        observed_ns, until_ns = _time_ns(observed), _time_ns(until)
    except (ValueError, OverflowError):
        result["reason"] = "INVALID_TIMESTAMPS"
        return result
    result.update(observed_at=observed, valid_until=until)
    if until_ns <= observed_ns:
        result["reason"] = "INVALID_TIME_WINDOW"
    elif observed_ns > now_ns:
        result["reason"] = "FUTURE_OBSERVATION"
    elif now_ns >= until_ns:
        result["reason"] = "EXPIRED"
    elif now_ns - observed_ns >= max_age_seconds * 10**9:
        result["reason"] = "OBSERVATION_TOO_OLD"
    elif not entry["ready"]:
        result.update(state="NOT_READY", reason="NO_READY_NODE_AS_REPORTED")
    elif entry["ready_node_count"] < entry["eligible_node_count"]:
        result.update(state="SOME_NODES_READY", reason="PARTIAL_NODE_COVERAGE")
    else:
        result.update(state="ALL_NODES_READY", reason="FRESH_AS_REPORTED")
    return result


def audit_readiness(artifact, artifact_sha256, response, target_ids, *, as_of,
                    max_age_seconds=60):
    expected_targets = _validate_targets(target_ids)
    if type(max_age_seconds) is not int or not 1 <= max_age_seconds <= 86400:
        raise ValueError("invalid maximum observation age")
    now_ns = _time_ns(as_of)
    generated = generate_plan(artifact, artifact_sha256)
    if generated is None:
        raise ValueError("only general Linux Kubernetes bundles are supported")
    plan, _ = generated
    images = [container["image"] for container in plan["containers"]]
    if len(images) > MAX_IMAGES:
        raise ValueError("the Runtime image limit was exceeded")
    identity = calculate_image_set_id(plan["architecture"], images)
    if (not isinstance(response, dict)
            or response.get("architecture") != plan["architecture"]
            or response.get("image_set_id") != identity):
        raise ValueError("response image set or architecture does not match")
    targets = response.get("targets")
    if not isinstance(targets, list) or len(targets) > MAX_TARGETS:
        raise ValueError("a readiness target array is required")
    by_id = {}
    for entry in targets:
        if not isinstance(entry, dict):
            raise ValueError("invalid readiness target")
        target = entry.get("target_id")
        if (not isinstance(target, str) or target not in expected_targets
                or target in by_id):
            raise ValueError("unexpected or duplicate response target")
        ready, count, eligible = (
            entry.get("ready"), entry.get("ready_node_count"),
            entry.get("eligible_node_count"),
        )
        if (type(ready) is not bool or type(count) is not int or type(eligible) is not int
                or not 0 <= count <= eligible <= MAX_COUNT or ready != (count > 0)):
            raise ValueError("invalid readiness counts")
        by_id[target] = entry

    audited = []
    for target in target_ids:
        if target not in by_id:
            audited.append({
                "target_id": target, "state": "UNKNOWN", "reason": "MISSING_TARGET",
                "ready_node_count_as_reported": None,
                "eligible_node_count_as_reported": None,
                "observed_at": None, "valid_until": None,
            })
        else:
            audited.append(_observation(by_id[target], now_ns, max_age_seconds))
    fresh = [entry for entry in audited if entry["state"] != "UNKNOWN"]
    positive = [entry for entry in fresh if entry["state"] != "NOT_READY"]
    all_nodes = all(entry["state"] == "ALL_NODES_READY" for entry in audited)
    if all_nodes:
        status = "ALL_ELIGIBLE_READY"
    elif positive:
        status = "PARTIAL"
    elif len(fresh) != len(audited):
        status = "UNKNOWN"
    else:
        status = "NOT_READY"
    return {
        "schema_version": "1.0",
        "scope": "SUPPLIED_BUNDLE_REQUESTED_TARGETS_ONLY",
        "status": status,
        "as_of": as_of,
        "max_observation_age_seconds": max_age_seconds,
        "bundle": {
            "challenge_slug": plan["challenge_slug"],
            "registry_revision": plan["registry_revision"],
            "architecture": plan["architecture"],
            "artifact_sha256": plan["artifact_sha256"],
            "container_count": len(images),
            "image_set_id": identity,
        },
        "all_requested_targets_have_ready_hint": len(positive) == len(audited),
        "all_reported_eligible_nodes_ready": all_nodes,
        "counts": {
            "requested_targets": len(audited), "fresh_targets": len(fresh),
            "unknown_targets": len(audited) - len(fresh),
            "ready_nodes_in_fresh_reports": sum(
                entry["ready_node_count_as_reported"] for entry in fresh),
            "eligible_nodes_in_fresh_reports": sum(
                entry["eligible_node_count_as_reported"] for entry in fresh),
        },
        "targets": audited,
        "limits": {
            "live_api_queried": False,
            "backend_active_verified": False,
            "node_identity_independently_verified": False,
            "operation_success_proven": False,
            "pod_execution_proven": False,
            "cold_pull_proven": False,
            "rollout_proven": False,
            "all_operating_nodes_verified": False,
        },
    }


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _invalid_constant(_value):
    raise ValueError("nonfinite JSON number")


def _read_json(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_ARTIFACT_BYTES:
        raise ValueError("invalid input file")
    with path.open("rb") as stream:
        raw = stream.read(MAX_ARTIFACT_BYTES + 1)
    if len(raw) > MAX_ARTIFACT_BYTES:
        raise ValueError("input size limit exceeded")
    return raw, json.loads(raw, object_pairs_hook=_unique_object,
                           parse_constant=_invalid_constant)


def write_audit(artifact_path, response_path, target_ids, output_dir, *, as_of=None,
                max_age_seconds=60):
    raw, artifact = _read_json(artifact_path)
    _, response = _read_json(response_path)
    generated_at = datetime.now(timezone.utc).isoformat()
    report = audit_readiness(
        artifact, hashlib.sha256(raw).hexdigest(), response, target_ids,
        as_of=generated_at if as_of is None else as_of,
        max_age_seconds=max_age_seconds,
    )
    report["generated_at"] = generated_at
    report["time_basis"] = "EXPLICIT_AS_OF" if as_of is not None else "SYSTEM_UTC_NOW"
    output_dir = Path(output_dir)
    output_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    descriptor = os.open(output_dir / "readiness-audit.json",
                         os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=True, indent=2, allow_nan=False)
        stream.write("\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", required=True, type=Path)
    parser.add_argument("--readiness-response", required=True, type=Path)
    parser.add_argument("--target-id", required=True, action="append")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--as-of", help="RFC3339 audit time; omitted for current UTC")
    parser.add_argument("--max-observation-age-seconds", type=int, default=60)
    args = parser.parse_args()
    try:
        report = write_audit(
            args.artifact, args.readiness_response, args.target_id, args.output_dir,
            as_of=args.as_of, max_age_seconds=args.max_observation_age_seconds,
        )
    except (ValueError, OSError, TypeError, RecursionError, OverflowError):
        print("Readiness audit failed: check inputs, time and output path.", file=sys.stderr)
        return 2
    print(json.dumps({"status": report["status"], "counts": report["counts"],
                      "live_api_queried": False}))
    return 0 if report["all_reported_eligible_nodes_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
