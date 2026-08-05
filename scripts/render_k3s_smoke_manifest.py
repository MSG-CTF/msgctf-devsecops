#!/usr/bin/env python3
"""Render a short-lived K3s smoke-test workload from a publish artifact.

This adapter is intentionally limited to one public TCP container. Production
workload generation remains the Runtime team's responsibility.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


DNS_LABEL = re.compile(r"^[a-z0-9](?:[-a-z0-9]*[a-z0-9])?$")
MAX_DNS_LABEL_LENGTH = 63


def _require_dns_label(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not DNS_LABEL.fullmatch(value) or len(value) > MAX_DNS_LABEL_LENGTH:
        raise ValueError(f"{field_name} must be a Kubernetes DNS label")


def _positive_int(value: Any, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def render_manifest(
    artifact: dict[str, Any],
    namespace: str,
    image_pull_secret: str,
) -> dict[str, Any]:
    """Create an isolated Deployment and ClusterIP Service for CI smoke tests."""
    _require_dns_label(namespace, "namespace")
    _require_dns_label(image_pull_secret, "image pull secret")

    if artifact.get("runtime_type") != "KUBERNETES":
        raise ValueError("K3s smoke deployment requires runtime_type KUBERNETES")
    if artifact.get("architecture") != "AMD64":
        raise ValueError("K3s smoke deployment requires architecture AMD64")

    challenge_slug = artifact.get("challenge_slug")
    _require_dns_label(challenge_slug, "challenge_slug")
    workload = artifact.get("workload")
    if not isinstance(workload, dict):
        raise ValueError("artifact workload must be an object")
    containers = workload.get("containers")
    if not isinstance(containers, list) or len(containers) != 1:
        raise ValueError("K3s smoke deployment supports exactly one container")

    container = containers[0]
    if not isinstance(container, dict):
        raise ValueError("artifact container must be an object")
    container_name = container.get("name")
    _require_dns_label(container_name, "container name")
    image = container.get("image")
    if not isinstance(image, str) or "@sha256:" not in image:
        raise ValueError("container image must be pinned to a sha256 digest")

    public_ports = [
        port for port in container.get("ports", [])
        if isinstance(port, dict) and port.get("public") is True
    ]
    if len(public_ports) != 1:
        raise ValueError("K3s smoke deployment requires exactly one public port")
    port = _positive_int(public_ports[0].get("port"), "public port")
    if port > 65535:
        raise ValueError("public port must be at most 65535")

    resource_profile = artifact.get("resource_profile")
    if not isinstance(resource_profile, dict):
        raise ValueError("artifact resource_profile must be an object")
    cpu = _positive_int(resource_profile.get("cpu_millicores"), "cpu_millicores")
    memory = _positive_int(resource_profile.get("memory_mib"), "memory_mib")
    ephemeral_storage = _positive_int(
        resource_profile.get("ephemeral_storage_mib"), "ephemeral_storage_mib"
    )

    workload_name = f"smoke-{challenge_slug}"
    if len(workload_name) > MAX_DNS_LABEL_LENGTH:
        raise ValueError("challenge_slug is too long for the smoke workload name")
    labels = {
        "app.kubernetes.io/name": workload_name,
        "app.kubernetes.io/part-of": "msgctf",
        "msgctf.devsecops/smoke": "true",
        "msgctf.devsecops/challenge": challenge_slug,
    }
    resources = {
        "requests": {
            "cpu": f"{cpu}m",
            "memory": f"{memory}Mi",
            "ephemeral-storage": f"{ephemeral_storage}Mi",
        },
        "limits": {
            "cpu": f"{cpu}m",
            "memory": f"{memory}Mi",
            "ephemeral-storage": f"{ephemeral_storage}Mi",
        },
    }
    deployment = {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": workload_name, "namespace": namespace, "labels": labels},
        "spec": {
            "replicas": 1,
            "selector": {"matchLabels": labels},
            "template": {
                "metadata": {"labels": labels},
                "spec": {
                    "automountServiceAccountToken": False,
                    "imagePullSecrets": [{"name": image_pull_secret}],
                    "securityContext": {
                        "runAsNonRoot": True,
                        "seccompProfile": {"type": "RuntimeDefault"},
                    },
                    "containers": [
                        {
                            "name": container_name,
                            "image": image,
                            "imagePullPolicy": "IfNotPresent",
                            "ports": [
                                {
                                    "name": f"tcp-{port}",
                                    "containerPort": port,
                                    "protocol": "TCP",
                                }
                            ],
                            "resources": resources,
                            "securityContext": {
                                "allowPrivilegeEscalation": False,
                                "privileged": False,
                                "capabilities": {"drop": ["ALL"]},
                            },
                        }
                    ],
                },
            },
        },
    }
    service = {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {"name": workload_name, "namespace": namespace, "labels": labels},
        "spec": {
            "type": "ClusterIP",
            "selector": labels,
            "ports": [
                {
                    "name": f"tcp-{port}",
                    "port": port,
                    "targetPort": port,
                    "protocol": "TCP",
                }
            ],
        },
    }
    return {"apiVersion": "v1", "kind": "List", "items": [deployment, service]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", required=True, type=Path)
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--image-pull-secret", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    artifact = json.loads(args.artifact.read_text(encoding="utf-8"))
    manifest = render_manifest(artifact, args.namespace, args.image_pull_secret)
    args.output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
