#!/usr/bin/env python3
"""Create and remove a temporary workload through Secure Provisioner."""

from __future__ import annotations

import argparse
import http.client
import json
import re
import time
import uuid
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DIGEST_IMAGE = re.compile(r"^.+@sha256:[0-9a-f]{64}$")
SERVICE_TOKEN = re.compile(r"^[A-Za-z0-9_-]{43,128}$")
FINAL_OPERATION_STATES = {"SUCCEEDED", "FAILED"}


class RetryableRuntimeError(RuntimeError):
    """The request may have reached Runtime, so the idempotent call is retried."""


class IncompleteOperationResult(RuntimeError):
    """A final operation response omitted fields required for safe cleanup."""


def _require_uuid(value: str, field_name: str) -> str:
    try:
        parsed = uuid.UUID(value)
    except (TypeError, ValueError, AttributeError) as error:
        raise ValueError(f"{field_name} must be a UUID") from error
    return str(parsed)


def _positive_int(value: Any, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def _isolation_profile(category: Any) -> str:
    if not isinstance(category, str) or not category:
        raise ValueError("artifact category must be a non-empty string")
    return "PWN" if category.lower() == "pwn" else "WEB"


def build_create_request(
    artifact: dict[str, Any],
    *,
    target_id: str,
    instance_id: str,
    team_id: str,
) -> dict[str, Any]:
    """Translate a publish artifact into the Runtime team's create contract."""
    if artifact.get("runtime_type") != "KUBERNETES":
        raise ValueError("Runtime smoke deployment requires runtime_type KUBERNETES")
    if artifact.get("architecture") != "AMD64":
        raise ValueError("Runtime smoke deployment currently requires architecture AMD64")
    if not isinstance(target_id, str) or not target_id.strip():
        raise ValueError("target_id must be a non-empty string")

    workload = artifact.get("workload")
    if not isinstance(workload, dict):
        raise ValueError("artifact workload must be an object")
    artifact_containers = workload.get("containers")
    if not isinstance(artifact_containers, list) or not artifact_containers:
        raise ValueError("artifact workload must contain at least one container")

    runtime_containers = []
    exposed = False
    for container in artifact_containers:
        if not isinstance(container, dict):
            raise ValueError("artifact container must be an object")
        name = container.get("name")
        image = container.get("image")
        if not isinstance(name, str) or not name:
            raise ValueError("container name must be a non-empty string")
        if not isinstance(image, str) or not DIGEST_IMAGE.fullmatch(image):
            raise ValueError("container image must be pinned to a lowercase sha256 digest")

        artifact_ports = container.get("ports")
        if not isinstance(artifact_ports, list) or not artifact_ports:
            raise ValueError("container ports must be a non-empty list")
        ports = []
        public_values = set()
        for port_spec in artifact_ports:
            if not isinstance(port_spec, dict):
                raise ValueError("container port must be an object")
            port = _positive_int(port_spec.get("port"), "container port")
            if port > 65535:
                raise ValueError("container port must be at most 65535")
            public = port_spec.get("public")
            if not isinstance(public, bool):
                raise ValueError("container port public must be a boolean")
            ports.append(port)
            public_values.add(public)

        if len(public_values) != 1:
            raise ValueError(
                "Runtime contract exposes ports by container, so one container cannot mix public and private ports"
            )
        expose = public_values == {True}
        exposed = exposed or expose
        runtime_containers.append(
            {
                "name": name,
                "image": image,
                "ports": ports,
                "expose": expose,
                "run_as_user": _positive_int(container.get("run_as_user", 10001), "run_as_user"),
            }
        )

    if not exposed:
        raise ValueError("Runtime smoke deployment requires at least one exposed container")

    runtime_workload = {"containers": runtime_containers}
    internal_connections = workload.get("internal_connections")
    if internal_connections is not None:
        if not isinstance(internal_connections, list):
            raise ValueError("workload.internal_connections must be a list")
        ports_by_container = {
            container["name"]: set(container["ports"])
            for container in runtime_containers
        }
        normalized_connections = []
        seen_connections = set()
        for connection in internal_connections:
            if not isinstance(connection, dict):
                raise ValueError("each internal connection must be an object")
            source = connection.get("source_container")
            destination = connection.get("destination_container")
            protocol = connection.get("protocol")
            port = _positive_int(connection.get("port"), "internal connection port")
            if source not in ports_by_container or destination not in ports_by_container:
                raise ValueError("internal connection must reference declared containers")
            if source == destination:
                raise ValueError("internal connection containers must be different")
            if protocol != "TCP":
                raise ValueError("internal connection protocol must be TCP")
            if port not in ports_by_container[destination]:
                raise ValueError("internal connection port must be declared by destination")
            key = (source, destination, protocol, port)
            if key in seen_connections:
                raise ValueError("internal connections must be unique")
            seen_connections.add(key)
            normalized_connections.append(
                {
                    "source_container": source,
                    "destination_container": destination,
                    "protocol": protocol,
                    "port": port,
                }
            )
        runtime_workload["internal_connections"] = normalized_connections

    resource_profile = artifact.get("resource_profile")
    if not isinstance(resource_profile, dict):
        raise ValueError("artifact resource_profile must be an object")
    resource_limits = {
        "cpu_millicores": _positive_int(resource_profile.get("cpu_millicores"), "cpu_millicores"),
        "memory_mib": _positive_int(resource_profile.get("memory_mib"), "memory_mib"),
        "ephemeral_storage_mib": _positive_int(
            resource_profile.get("ephemeral_storage_mib"), "ephemeral_storage_mib"
        ),
    }

    normalized_instance_id = _require_uuid(instance_id, "instance_id")
    normalized_team_id = _require_uuid(team_id, "team_id")
    return {
        "request_id": f"ci-smoke-create-{normalized_instance_id}",
        "instance_id": normalized_instance_id,
        "team_id": normalized_team_id,
        "isolation_profile": _isolation_profile(artifact.get("category")),
        "target": {"runtime_type": "KUBERNETES", "target_id": target_id.strip()},
        "workload": {**runtime_workload, "resource_limits": resource_limits},
    }


class RuntimeClient:
    def __init__(self, api_url: str, token: str, timeout: float) -> None:
        if not api_url.startswith(("http://127.0.0.1:", "http://localhost:")):
            raise ValueError("Runtime smoke API URL must be a loopback HTTP URL")
        if not SERVICE_TOKEN.fullmatch(token):
            raise ValueError("Runtime service token has an invalid format")
        self.api_url = api_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        encoded = None if body is None else json.dumps(body).encode("utf-8")
        request = Request(
            f"{self.api_url}{path}",
            data=encoded,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = response.read().decode("utf-8")
        except HTTPError as error:
            try:
                detail = error.read().decode("utf-8", errors="replace")
            finally:
                error.close()
            detail = detail.replace(self.token, "[REDACTED]")[:500]
            if error.code >= 500:
                raise RetryableRuntimeError(
                    f"Runtime API {method} {path} returned HTTP {error.code}: {detail}"
                ) from error
            raise RuntimeError(f"Runtime API {method} {path} failed: HTTP {error.code}: {detail}") from error
        except (URLError, TimeoutError, ConnectionError, OSError, http.client.HTTPException) as error:
            raise RetryableRuntimeError(
                f"Runtime API {method} {path} response is ambiguous: {error}"
            ) from error
        try:
            result = json.loads(payload)
        except json.JSONDecodeError as error:
            raise RetryableRuntimeError(
                f"Runtime API {method} {path} returned malformed JSON"
            ) from error
        if not isinstance(result, dict):
            raise RetryableRuntimeError("Runtime API response must be a JSON object")
        return result


def _submit_with_retry(
    client: RuntimeClient,
    method: str,
    path: str,
    body: dict[str, Any],
    *,
    poll_interval: float,
    deadline: float,
) -> dict[str, Any]:
    while True:
        try:
            response = client.request(method, path, body)
        except RetryableRuntimeError as error:
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Runtime API {method} {path} submission timed out") from error
            time.sleep(poll_interval)
            continue
        operation_id = response.get("operation_id")
        if isinstance(operation_id, str) and operation_id:
            return response
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Runtime API {method} {path} did not return operation_id")
        time.sleep(poll_interval)


def _poll_operation(
    client: RuntimeClient,
    operation_id: Any,
    *,
    poll_interval: float,
    deadline: float,
    require_create_result: bool = False,
) -> dict[str, Any]:
    if not isinstance(operation_id, str) or not operation_id:
        raise RuntimeError("Runtime API response did not include operation_id")
    incomplete_result = False
    while time.monotonic() < deadline:
        try:
            snapshot = client.request("GET", f"/internal/v1/operations/{operation_id}")
        except RetryableRuntimeError:
            time.sleep(poll_interval)
            continue
        status = snapshot.get("status")
        if status in FINAL_OPERATION_STATES:
            if status == "FAILED":
                raise RuntimeError(
                    f"Runtime operation {operation_id} failed: {snapshot.get('last_error_code', 'UNKNOWN')}"
                )
            if require_create_result:
                result = snapshot.get("result")
                workload_id = result.get("runtime_workload_id") if isinstance(result, dict) else None
                if not isinstance(workload_id, str) or not workload_id.strip():
                    incomplete_result = True
                    time.sleep(poll_interval)
                    continue
            return snapshot
        time.sleep(poll_interval)
    if incomplete_result:
        raise IncompleteOperationResult("Runtime create operation did not return a result")
    raise TimeoutError(f"Runtime operation {operation_id} timed out")


def run_smoke(
    artifact: dict[str, Any],
    *,
    api_url: str,
    token_file: Path,
    target_id: str,
    instance_id: str,
    team_id: str,
    poll_interval: float = 2,
    timeout: float = 300,
    cleanup_timeout: float = 300,
    evidence_clock: Callable[[], float] | None = None,
) -> dict[str, Any]:
    if evidence_clock is None:
        evidence_clock = time.monotonic
    token = token_file.read_text(encoding="utf-8").strip()
    client = RuntimeClient(api_url, token, timeout=min(max(timeout, cleanup_timeout, 1), 30))
    create_request = build_create_request(
        artifact,
        target_id=target_id,
        instance_id=instance_id,
        team_id=team_id,
    )
    create_started = evidence_clock()
    deadline = time.monotonic() + timeout
    recovered_after_timeout = False
    try:
        accepted = _submit_with_retry(
            client,
            "POST",
            "/internal/v1/instances",
            create_request,
            poll_interval=poll_interval,
            deadline=deadline,
        )
        create_poll_deadline = deadline
    except TimeoutError:
        recovered_after_timeout = True
        create_poll_deadline = time.monotonic() + cleanup_timeout
        accepted = _submit_with_retry(
            client,
            "POST",
            "/internal/v1/instances",
            create_request,
            poll_interval=poll_interval,
            deadline=create_poll_deadline,
        )
    try:
        created = _poll_operation(
            client,
            accepted.get("operation_id"),
            poll_interval=poll_interval,
            deadline=create_poll_deadline,
            require_create_result=True,
        )
    except (TimeoutError, IncompleteOperationResult):
        if recovered_after_timeout:
            raise
        recovered_after_timeout = True
        created = _poll_operation(
            client,
            accepted.get("operation_id"),
            poll_interval=poll_interval,
            deadline=time.monotonic() + cleanup_timeout,
            require_create_result=True,
        )
    create_result = created.get("result")
    if not isinstance(create_result, dict):
        raise RuntimeError("Runtime create operation did not return a result")
    runtime_workload_id = create_result.get("runtime_workload_id")
    if not isinstance(runtime_workload_id, str) or not runtime_workload_id.strip():
        raise RuntimeError("Runtime create operation returned an invalid runtime_workload_id")
    endpoints = create_result.get("endpoints")
    endpoints_valid = isinstance(endpoints, list) and bool(endpoints)
    create_elapsed_seconds = round(evidence_clock() - create_started, 3)

    delete_request = {
        "request_id": f"ci-smoke-delete-{create_request['instance_id']}",
        "instance_id": create_request["instance_id"],
        "team_id": create_request["team_id"],
        "target": create_request["target"],
        "runtime_workload_id": runtime_workload_id,
        "delete_reason": "ADMIN_FORCED",
    }
    delete_started = evidence_clock()
    cleanup_deadline = time.monotonic() + cleanup_timeout
    deleted = _submit_with_retry(
        client,
        "DELETE",
        f"/internal/v1/instances/{create_request['instance_id']}",
        delete_request,
        poll_interval=poll_interval,
        deadline=cleanup_deadline,
    )
    delete_snapshot = _poll_operation(
        client,
        deleted.get("operation_id"),
        poll_interval=poll_interval,
        deadline=cleanup_deadline,
    )
    delete_elapsed_seconds = round(evidence_clock() - delete_started, 3)
    if not endpoints_valid:
        raise RuntimeError("Runtime create operation did not return public endpoints")
    return {
        "challenge_slug": artifact.get("challenge_slug"),
        "revision": artifact.get("revision"),
        "target_id": target_id,
        "instance_id": create_request["instance_id"],
        "runtime_workload_id": runtime_workload_id,
        "images": [
            {"name": container["name"], "image": container["image"]}
            for container in create_request["workload"]["containers"]
        ],
        "service_url": create_result.get("service_url"),
        "endpoints": endpoints,
        "create_status": created["status"],
        "create_elapsed_seconds": create_elapsed_seconds,
        "delete_status": delete_snapshot["status"],
        "delete_elapsed_seconds": delete_elapsed_seconds,
        "recovered_after_timeout": recovered_after_timeout,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--api-url", default="http://127.0.0.1:8080")
    parser.add_argument("--token-file", default=Path("/etc/secure-provisioner/service-token"), type=Path)
    parser.add_argument("--poll-interval", default=2, type=float)
    parser.add_argument("--timeout", default=300, type=float)
    parser.add_argument("--cleanup-timeout", default=300, type=float)
    args = parser.parse_args()

    artifact = json.loads(args.artifact.read_text(encoding="utf-8"))
    config = json.loads(args.config.read_text(encoding="utf-8"))
    result = run_smoke(
        artifact,
        api_url=args.api_url,
        token_file=args.token_file,
        target_id=config["target_id"],
        instance_id=config["instance_id"],
        team_id=config["team_id"],
        poll_interval=args.poll_interval,
        timeout=args.timeout,
        cleanup_timeout=args.cleanup_timeout,
    )
    print(f"MSGCTF_RUNTIME_SMOKE_RESULT={json.dumps(result, separators=(',', ':'))}")


if __name__ == "__main__":
    main()
