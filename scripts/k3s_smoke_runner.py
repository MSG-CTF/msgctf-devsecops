#!/usr/bin/env python3
"""Run a temporary K3s smoke deployment on an SSM-managed node."""

from __future__ import annotations

import argparse
import base64
import json
import socket
import subprocess
import time
from pathlib import Path


def run(*command: str, capture_output: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=True, text=True, capture_output=capture_output)


def secret_value(secret_arn: str) -> dict[str, str]:
    result = run(
        "aws", "secretsmanager", "get-secret-value", "--secret-id", secret_arn,
        "--query", "SecretString", "--output", "text", capture_output=True,
    )
    value = json.loads(result.stdout)
    if not isinstance(value.get("username"), str) or not isinstance(value.get("token"), str):
        raise ValueError("GHCR secret must contain username and token")
    return value


def create_pull_secret(namespace: str, secret_name: str, secret_arn: str) -> None:
    credential = secret_value(secret_arn)
    auth = base64.b64encode(f"{credential['username']}:{credential['token']}".encode()).decode()
    docker_config = json.dumps({"auths": {"ghcr.io": {"auth": auth}}})
    run("kubectl", "-n", namespace, "create", "secret", "generic", secret_name,
        "--type=kubernetes.io/dockerconfigjson", f"--from-literal=.dockerconfigjson={docker_config}")


def probe_tcp(namespace: str, service: str, port: int, timeout: int) -> None:
    forward = subprocess.Popen(
        ["kubectl", "-n", namespace, "port-forward", f"service/{service}", f"18080:{port}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", 18080), timeout=2):
                    return
            except OSError:
                time.sleep(2)
        raise TimeoutError("TCP smoke probe timed out")
    finally:
        forward.terminate()
        forward.wait(timeout=10)


def deploy_probe_cleanup(args: argparse.Namespace) -> None:
    try:
        run("kubectl", "create", "namespace", args.namespace)
        create_pull_secret(args.namespace, args.image_pull_secret, args.ghcr_secret_arn)
        run("kubectl", "apply", "-f", str(args.manifest))
        run("kubectl", "-n", args.namespace, "rollout", "status", f"deployment/{args.workload}", f"--timeout={args.rollout_timeout}s")
        probe_tcp(args.namespace, args.workload, args.port, args.probe_timeout)
        print("K3s smoke deployment passed")
    finally:
        run("kubectl", "delete", "namespace", args.namespace, "--wait=true", "--ignore-not-found=true", f"--timeout={args.cleanup_timeout}s")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--workload", required=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--image-pull-secret", default="ghcr-pull")
    parser.add_argument("--ghcr-secret-arn", required=True)
    parser.add_argument("--rollout-timeout", default=180, type=int)
    parser.add_argument("--probe-timeout", default=60, type=int)
    parser.add_argument("--cleanup-timeout", default=180, type=int)
    deploy_probe_cleanup(parser.parse_args())


if __name__ == "__main__":
    main()
