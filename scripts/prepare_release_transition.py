#!/usr/bin/env python3
"""Prepare an offline A/B release handoff; never activate or replace workloads."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from uuid import UUID

from scripts.audit_node_image_readiness import audit_readiness, _read_json, _time_ns, _validate_targets
from scripts.execution_settings_contract import validate_env, validate_secret_env
from scripts.generate_node_image_plan import generate_plan
from scripts.healthcheck_contract import validate_healthcheck
from scripts.vm_image_prefetch import read_json, save_private


MAX_SNAPSHOT_AGE_SECONDS = 60
HANDOVER_GAPS = [
    "PARALLEL_SAME_USER_INSTANCE_CONTRACT_REQUIRED",
    "STABLE_ENDPOINT_AND_TRAFFIC_SWITCH_CONTRACT_REQUIRED",
    "STATE_SESSION_AND_OPEN_CONNECTION_POLICY_REQUIRED",
    "FAILED_B_KEEP_A_AND_ROLLBACK_VERIFICATION_REQUIRED",
]


def require(condition, code="INPUT_OR_EVIDENCE_INVALID"):
    if not condition:
        raise ValueError(code)


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def plan_hash(plan):
    return canonical_hash({key: value for key, value in plan.items() if key != "plan_sha256"})


def canonical_uuid(value):
    require(isinstance(value, str) and str(UUID(value)) == value)
    return value


def ports(raw):
    require(isinstance(raw, list) and 1 <= len(raw) <= 32)
    result = {}
    for row in raw:
        require(isinstance(row, dict) and set(row) == {"port", "public"})
        port = row["port"]
        require(type(port) is int and 1 <= port <= 65535 and port not in result)
        require(type(row["public"]) is bool)
        result[port] = row["public"]
    return sorted(result.items())


def checked_release(bundle, checksum, row, challenge_id, *, current, as_of_ns):
    generated = generate_plan(bundle, checksum)
    require(generated is not None, "GENERAL_KUBERNETES_RELEASE_REQUIRED")
    source, _ = generated
    require(bundle.get("isolation_profile") == "WEB" and bundle["category"].lower() != "pwn", "WEB_RELEASE_REQUIRED")
    require(isinstance(row, dict))
    canonical_uuid(row.get("release_id"))
    require(row.get("challenge_id") == challenge_id
            and row.get("challenge_slug") == source["challenge_slug"]
            and type(row.get("registry_revision")) is int
            and row["registry_revision"] == source["registry_revision"]
            and row.get("runtime_type") == source["runtime_type"]
            and row.get("architecture") == source["architecture"]
            and row.get("isolation_profile") == "WEB"
            and row.get("source_ref") == "refs/heads/main"
            and row.get("is_deployable") is True and row.get("is_current") is current,
            "BACKEND_RELEASE_OR_OPERATING_SELECTION_MISMATCH")
    require("derived_from_release_id" in row and row["derived_from_release_id"] is None,
            "DERIVED_RELEASE_REQUIRES_EFFECTIVE_SETTINGS_REVIEW")
    require(row.get("approved_at") is not None
            and _time_ns(row["approved_at"]) <= as_of_ns, "APPROVED_RELEASE_REQUIRED")
    resources = bundle.get("resource_profile")
    require(isinstance(resources, dict) and set(resources) == {
        "cpu_millicores", "memory_mib", "ephemeral_storage_mib"})
    require(all(type(value) is int and value > 0 for value in resources.values()))
    require(resources == row.get("resource_profile"), "RESOURCE_SETTINGS_MISMATCH")
    supplied = row.get("containers")
    require(isinstance(supplied, list) and len(supplied) == len(source["containers"]))
    by_name = {}
    for container in supplied:
        require(isinstance(container, dict) and isinstance(container.get("name"), str)
                and container["name"] not in by_name)
        by_name[container["name"]] = container
    require(set(by_name) == {item["name"] for item in source["containers"]},
            "FULL_CONTAINER_SET_REQUIRED")
    effective, health_containers = [], []
    require(set(bundle["workload"]) <= {"containers", "healthcheck"}, "UNMODELED_WORKLOAD_SETTINGS")
    for container in bundle["workload"]["containers"]:
        require(set(container) <= {"name", "image", "ports", "env", "secret_env"}, "UNMODELED_CONTAINER_SETTINGS")
        saved = by_name[container["name"]]
        declared_ports = ports(container.get("ports"))
        require(saved.get("image_ref") == container["image"]
                and ports(saved.get("ports")) == declared_ports, "CONTAINER_IMAGE_OR_PORT_MISMATCH")
        env = validate_env(container.get("env", {}))
        aliases = validate_secret_env(container.get("secret_env", {}), env)
        require(not (env or aliases) or bundle["schema_version"] == "2.1", "EXECUTION_SCHEMA_21_REQUIRED")
        require(validate_env(saved.get("env", {})) == env, "ENVIRONMENT_SETTINGS_MISMATCH")
        require(not saved.get("env_rules"), "ENV_RULES_REQUIRE_EFFECTIVE_SETTINGS_REVIEW")
        bindings = saved.get("secret_bindings", [])
        require(isinstance(bindings, list) and len(bindings) == len(aliases))
        names, versions = set(), []
        for binding in bindings:
            require(isinstance(binding, dict) and isinstance(binding.get("env_name"), str))
            name = binding["env_name"]
            require(name in aliases and name not in names
                    and binding.get("name") == aliases[name]
                    and binding.get("status") == "registered"
                    and type(binding.get("version")) is int and binding["version"] > 0,
                    "REGISTERED_SECRET_BINDINGS_REQUIRED")
            names.add(name)
            versions.append({"env_name": name, "name": binding["name"], "version": binding["version"]})
        if aliases:
            canonical_uuid(saved.get("secret_ref"))
        else:
            require(not saved.get("secret_ref"), "UNDECLARED_SECRET_BINDING")
        effective.append({"name": container["name"], "ports": declared_ports, "env": env,
                          "secret_bindings": sorted(versions, key=lambda item: item["env_name"])})
        health_containers.append({"name": container["name"], "ports": [port for port, _ in declared_ports]})
    require(any(public for item in effective for _, public in item["ports"]), "PUBLIC_WEB_PORT_REQUIRED")
    healthcheck = validate_healthcheck(bundle["workload"].get("healthcheck"), health_containers)
    require(healthcheck == row.get("healthcheck"), "HEALTHCHECK_SETTINGS_MISMATCH")
    return {"release_id": row["release_id"], "challenge_slug": source["challenge_slug"],
            "registry_revision": source["registry_revision"], "architecture": source["architecture"],
            "artifact_sha256": checksum, "source_sha": source["source_sha"],
            "containers": source["containers"],
            "execution_settings_sha256": canonical_hash({"containers": sorted(effective, key=lambda item: item["name"]),
                                                         "healthcheck": healthcheck, "resource_profile": resources})}


def prepare_transition(current_bundle, current_checksum, candidate_bundle, candidate_checksum,
                       snapshot, *, current_release_id, candidate_release_id, target_ids,
                       backend_observed_at, as_of, candidate_readiness=None, direction="update"):
    now_ns, observed_ns = _time_ns(as_of), _time_ns(backend_observed_at)
    require(0 <= now_ns - observed_ns < MAX_SNAPSHOT_AGE_SECONDS * 10**9, "BACKEND_SNAPSHOT_NOT_FRESH")
    _validate_targets(target_ids)
    canonical_uuid(current_release_id)
    canonical_uuid(candidate_release_id)
    require(current_release_id != candidate_release_id, "DISTINCT_A_AND_B_REQUIRED")
    require(isinstance(snapshot, dict) and {"challenge_id", "current_release_id", "activation", "releases"} <= set(snapshot))
    challenge_id = canonical_uuid(snapshot.get("challenge_id"))
    require(snapshot.get("current_release_id") == current_release_id, "ACTIVE_RELEASE_CHANGED")
    activation = snapshot.get("activation")
    require(activation is None or (isinstance(activation, dict)
            and activation.get("status") in {"ACTIVATED", "SUPERSEDED", "FAILED"}),
            "EXISTING_ACTIVATION_REQUIRES_REVIEW")
    rows = snapshot.get("releases")
    require(isinstance(rows, list) and 2 <= len(rows) <= 1000)
    by_id = {}
    for row in rows:
        require(isinstance(row, dict))
        key = canonical_uuid(row.get("release_id"))
        require(key not in by_id)
        by_id[key] = row
    require(current_release_id in by_id and candidate_release_id in by_id)
    a = checked_release(current_bundle, current_checksum, by_id[current_release_id], challenge_id,
                        current=True, as_of_ns=now_ns)
    b = checked_release(candidate_bundle, candidate_checksum, by_id[candidate_release_id], challenge_id,
                        current=False, as_of_ns=now_ns)
    require(a["challenge_slug"] == b["challenge_slug"] and a["architecture"] == b["architecture"],
            "SAME_PROBLEM_AND_ARCHITECTURE_REQUIRED")
    require(direction in ("update", "rollback"))
    require((direction == "update" and b["registry_revision"] > a["registry_revision"])
            or (direction == "rollback" and b["registry_revision"] < a["registry_revision"]),
            "EXPLICIT_UPDATE_OR_ROLLBACK_DIRECTION_REQUIRED")
    readiness = None
    if candidate_readiness is not None:
        readiness = audit_readiness(candidate_bundle, candidate_checksum, candidate_readiness,
                                    target_ids, as_of=as_of)
    ready = readiness is not None and readiness["all_reported_eligible_nodes_ready"]
    result = {
        "schema_version": "1.0", "scope": "OFFLINE_WEB_RELEASE_TRANSITION_PREPARATION",
        "as_of": as_of, "backend_observed_at_as_attested": backend_observed_at,
        "direction": direction, "status": "READY_FOR_REPRESENTATIVE_QA" if ready else "IMAGE_READINESS_REQUIRED",
        "challenge_id": challenge_id, "current": a, "candidate": b, "target_ids": target_ids,
        "candidate_readiness": readiness,
        "execution_settings_changed": a["execution_settings_sha256"] != b["execution_settings_sha256"],
        "preserve_images": sorted({item["image"] for release in (a, b) for item in release["containers"]}),
        "preparation_handoff": {"method": "POST", "path": f"/api/v1/admin/challenges/{challenge_id}/releases/{candidate_release_id}/image_preparations",
                                "body": {}, "idempotency_key": "OPERATOR_MUST_CHOOSE_AND_RECORD",
                                "call_performed": False, "requires_operator_approval": True},
        "representative_test_handoff": {"method": "POST", "path": f"/api/v1/admin/challenges/{challenge_id}/releases/{candidate_release_id}/deployment_tests",
                                        "body": {"request_id": "OPERATOR_MUST_CHOOSE_AND_RECORD_CANONICAL_UUID"},
                                        "call_performed": False, "requires_operator_approval": True,
                                        "traffic_switch": False},
        "current_platform_behavior": "EXISTING_A_REMAINS_AND_NEW_INSTANCES_USE_SELECTED_RELEASE",
        "live_instance_handover": {"status": "BLOCKED_PENDING_CONSUMER_CONTRACTS", "gaps": HANDOVER_GAPS},
        "limits": {"source_provenance_live_revalidated": False, "backend_live_queried": False,
                   "runtime_live_queried": False, "image_pulled": False, "pod_created": False,
                   "runtime_uid_storage_network_policy_verified": False,
                   "activation_requested": False, "instance_replaced": False,
                   "automatic_switch_allowed": False, "zero_downtime_proven": False},
    }
    result["plan_sha256"] = plan_hash(result)
    return result


def write_plan(current_path, candidate_path, snapshot_path, output_dir, *,
               current_release_id, candidate_release_id, target_ids, backend_observed_at,
               as_of=None, readiness_path=None, direction="update"):
    current_raw, current = _read_json(current_path)
    candidate_raw, candidate = _read_json(candidate_path)
    # Hash the exact immutable bytes used by the parser, not a JSON reserialization.
    current_sha = hashlib.sha256(current_raw).hexdigest()
    candidate_sha = hashlib.sha256(candidate_raw).hexdigest()
    result = prepare_transition(current, current_sha, candidate, candidate_sha, read_json(snapshot_path),
        current_release_id=current_release_id, candidate_release_id=candidate_release_id,
        target_ids=target_ids, backend_observed_at=backend_observed_at,
        as_of=as_of or datetime.now(timezone.utc).isoformat(),
        candidate_readiness=read_json(readiness_path) if readiness_path else None, direction=direction)
    result["time_basis"] = "EXPLICIT_REPLAY_TIME" if as_of else "SYSTEM_UTC_NOW"
    result["plan_sha256"] = plan_hash(result)
    output = Path(output_dir)
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    save_private(output / "transition-plan.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current-artifact", type=Path, required=True)
    parser.add_argument("--candidate-artifact", type=Path, required=True)
    parser.add_argument("--backend-releases", type=Path, required=True)
    parser.add_argument("--current-release-id", required=True)
    parser.add_argument("--candidate-release-id", required=True)
    parser.add_argument("--backend-observed-at", required=True)
    parser.add_argument("--target-id", action="append", required=True)
    parser.add_argument("--candidate-readiness", type=Path)
    parser.add_argument("--direction", choices=("update", "rollback"), default="update")
    parser.add_argument("--as-of", help="Replay only; never an execution authorization")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = write_plan(args.current_artifact, args.candidate_artifact, args.backend_releases,
            args.output_dir, current_release_id=args.current_release_id,
            candidate_release_id=args.candidate_release_id, target_ids=args.target_id,
            backend_observed_at=args.backend_observed_at, as_of=args.as_of,
            readiness_path=args.candidate_readiness, direction=args.direction)
    except (ValueError, OSError, TypeError, KeyError, OverflowError, RecursionError):
        print("Transition preparation failed: check source, release selection, settings and observation time.", file=sys.stderr)
        return 2
    print(json.dumps({"status": result["status"], "plan_sha256": result["plan_sha256"],
                      "automatic_switch_allowed": False, "zero_downtime_proven": False}))
    return 0 if result["status"] == "READY_FOR_REPRESENTATIVE_QA" else 1


if __name__ == "__main__":
    raise SystemExit(main())
