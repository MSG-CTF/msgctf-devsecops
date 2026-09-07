#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path

import yaml


SAFE_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
CATEGORY = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
IMAGE_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/@:-]{0,254}$")
IMAGE_DIGEST = re.compile(r"^.+@sha256:[0-9a-f]{64}$")
RUNTIME_TYPES = {"KUBERNETES", "DOCKER", "VM"}
ARCHITECTURES = {"AMD64", "ARM64"}
RESOURCE_FIELDS = (
    "cpu_millicores",
    "memory_mib",
    "ephemeral_storage_mib",
)


def _required_string(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _positive_int(value, field):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _resolve_build_path(challenge_path, raw_path):
    build = _required_string(raw_path, "container.build")
    resolved = (challenge_path / build).resolve()
    try:
        relative = resolved.relative_to(challenge_path)
    except ValueError as error:
        raise ValueError(
            "container.build must stay inside the challenge directory"
        ) from error
    if not resolved.is_dir():
        raise ValueError(f"container.build directory does not exist: {relative}")
    if not (resolved / "Dockerfile").is_file():
        raise ValueError(f"container.build must contain a Dockerfile: {relative}")
    return relative.as_posix()


def _validate_ports(raw_ports, container_name):
    if not isinstance(raw_ports, list) or not raw_ports:
        raise ValueError(f"{container_name}.ports must be a non-empty list")
    ports = []
    for port in raw_ports:
        if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
            raise ValueError(f"{container_name}.ports entries must be in 1..65535")
        if port in ports:
            raise ValueError(f"{container_name}.ports must not contain duplicates")
        ports.append(port)
    return ports


def _validate_container(challenge_path, raw):
    if not isinstance(raw, dict):
        raise ValueError("each deployment container must be an object")
    name = _required_string(raw.get("name"), "container.name")
    if not SAFE_NAME.fullmatch(name):
        raise ValueError("container name must be a safe lowercase identifier")

    has_build = "build" in raw
    has_image = "image" in raw
    if has_build == has_image:
        raise ValueError(f"container {name} must define exactly one of build or image")

    container = {
        "name": name,
        "ports": _validate_ports(raw.get("ports"), name),
    }
    expose = raw.get("expose")
    if not isinstance(expose, bool):
        raise ValueError(f"{name}.expose must be a boolean")
    container["expose"] = expose

    if has_build:
        container["build"] = _resolve_build_path(challenge_path, raw["build"])
    else:
        image = _required_string(raw["image"], f"{name}.image")
        if not IMAGE_REF.fullmatch(image):
            raise ValueError(f"{name}.image is not a valid OCI image reference")
        if "@" in image:
            if not IMAGE_DIGEST.fullmatch(image):
                raise ValueError(f"{name}.image digest must use sha256")
        else:
            image_name = image.rsplit("/", 1)[-1]
            if ":" not in image_name:
                raise ValueError(f"{name}.image must include an explicit tag or digest")
            if image_name.rsplit(":", 1)[-1].lower() == "latest":
                raise ValueError(f"{name}.image must not use the latest tag")
        container["image"] = image
    return container


def _validate_healthcheck(raw, containers):
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("deployment.healthcheck must be an object")
    container_name = _required_string(
        raw.get("container"),
        "healthcheck.container",
    )
    by_name = {container["name"]: container for container in containers}
    if container_name not in by_name:
        raise ValueError("healthcheck.container must reference a declared container")
    port = _positive_int(raw.get("port"), "healthcheck.port")
    if port > 65535 or port not in by_name[container_name]["ports"]:
        raise ValueError("healthcheck.port must reference a declared container port")
    path = _required_string(raw.get("path"), "healthcheck.path")
    if not path.startswith("/") or any(ord(character) < 32 for character in path):
        raise ValueError("healthcheck.path must be an absolute HTTP path")
    return {"container": container_name, "port": port, "path": path}


def _validate_internal_connections(raw, containers):
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("deployment.internal_connections must be a list")

    by_name = {container["name"]: container for container in containers}
    connections = []
    seen = set()
    for entry in raw:
        if not isinstance(entry, dict):
            raise ValueError("each internal connection must be an object")
        source = _required_string(
            entry.get("source_container"),
            "internal_connections.source_container",
        )
        destination = _required_string(
            entry.get("destination_container"),
            "internal_connections.destination_container",
        )
        if source not in by_name or destination not in by_name:
            raise ValueError("internal connection must reference declared containers")
        if source == destination:
            raise ValueError("internal connection containers must be different")
        if entry.get("protocol") != "TCP":
            raise ValueError("internal connection protocol must be TCP")
        port = _positive_int(entry.get("port"), "internal_connections.port")
        if port > 65535 or port not in by_name[destination]["ports"]:
            raise ValueError(
                "internal connection port must reference a destination container port"
            )
        key = (source, destination, "TCP", port)
        if key in seen:
            raise ValueError("internal connections must not contain duplicates")
        seen.add(key)
        connections.append(
            {
                "source_container": source,
                "destination_container": destination,
                "protocol": "TCP",
                "port": port,
            }
        )
    return connections


def validate_spec(challenge_path):
    challenge_path = Path(challenge_path).resolve()
    if not challenge_path.is_dir():
        raise ValueError("challenge path must be a directory")
    if not SAFE_NAME.fullmatch(challenge_path.name):
        raise ValueError("challenge directory name must be a safe lowercase slug")

    info_path = challenge_path / "info.yaml"
    if not info_path.is_file():
        raise ValueError("info.yaml must exist directly under the challenge directory")
    raw = yaml.safe_load(info_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("info.yaml root must be an object")

    name = _required_string(raw.get("name"), "name")
    category = _required_string(raw.get("category"), "category")
    if not CATEGORY.fullmatch(category):
        raise ValueError("category must be a lowercase identifier")
    _required_string(raw.get("description"), "description")
    _required_string(raw.get("flag"), "flag")

    deployment = raw.get("deployment")
    metadata = {
        "schema_version": "2.0",
        "challenge_slug": challenge_path.name,
        "name": name,
        "category": category,
        "is_server": deployment is not None,
    }
    if deployment is None:
        return metadata
    if not isinstance(deployment, dict):
        raise ValueError("deployment must be an object")
    allowed_deployment_fields = {
        "runtime_type",
        "architecture",
        "containers",
        "resource_profile",
        "healthcheck",
        "internal_connections",
    }
    unsupported_fields = sorted(set(deployment) - allowed_deployment_fields)
    if "network_policy" in deployment:
        raise ValueError(
            "raw Kubernetes NetworkPolicy is Runtime-owned and must not be declared"
        )
    if unsupported_fields:
        raise ValueError(
            "deployment contains unsupported fields: " + ", ".join(unsupported_fields)
        )
    runtime_type = deployment.get("runtime_type")
    if runtime_type not in RUNTIME_TYPES:
        raise ValueError("deployment.runtime_type is not supported")
    architecture = deployment.get("architecture")
    if architecture not in ARCHITECTURES:
        raise ValueError("deployment.architecture is not supported")

    raw_containers = deployment.get("containers")
    if not isinstance(raw_containers, list) or not raw_containers:
        raise ValueError("deployment.containers must be a non-empty list")
    containers = [
        _validate_container(challenge_path, raw_container)
        for raw_container in raw_containers
    ]
    names = [container["name"] for container in containers]
    if len(names) != len(set(names)):
        raise ValueError("container name values must be unique")

    raw_profile = deployment.get("resource_profile")
    if not isinstance(raw_profile, dict):
        raise ValueError("deployment.resource_profile must be an object")
    resource_profile = {
        field: _positive_int(raw_profile.get(field), f"resource_profile.{field}")
        for field in RESOURCE_FIELDS
    }

    metadata.update({
        "runtime_type": runtime_type,
        "architecture": architecture,
        "isolation_profile": "PWN" if category == "pwn" else "WEB",
        "containers": containers,
        "resource_profile": resource_profile,
    })
    internal_connections = _validate_internal_connections(
        deployment.get("internal_connections"),
        containers,
    )
    if internal_connections:
        metadata["internal_connections"] = internal_connections
    healthcheck = _validate_healthcheck(deployment.get("healthcheck"), containers)
    if healthcheck:
        metadata["healthcheck"] = healthcheck
    return metadata


def container_matrix(metadata):
    include = []
    for container in metadata.get("containers", []):
        source_type = "build" if "build" in container else "image"
        include.append(
            {
                "name": container["name"],
                "source_type": source_type,
                "source": container[source_type],
            }
        )
    return {"include": include}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("challenge_path", type=Path)
    parser.add_argument("--metadata-output", type=Path)
    parser.add_argument("--matrix-output", type=Path)
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()

    metadata = validate_spec(args.challenge_path)
    matrix = container_matrix(metadata)
    if args.metadata_output:
        args.metadata_output.parent.mkdir(parents=True, exist_ok=True)
        args.metadata_output.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if args.matrix_output:
        args.matrix_output.parent.mkdir(parents=True, exist_ok=True)
        args.matrix_output.write_text(
            json.dumps(matrix, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as output:
            output.write(f"challenge_slug={metadata['challenge_slug']}\n")
            output.write(f"is_server={str(metadata['is_server']).lower()}\n")
            output.write(
                "matrix="
                + json.dumps(matrix, ensure_ascii=True, separators=(",", ":"))
                + "\n"
            )
    print(
        json.dumps(
            {
                "challenge_slug": metadata["challenge_slug"],
                "is_server": metadata["is_server"],
                "container_count": len(metadata.get("containers", [])),
                "runtime_type": metadata.get("runtime_type"),
                "architecture": metadata.get("architecture"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
