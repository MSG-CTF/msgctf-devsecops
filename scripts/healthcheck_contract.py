"""Validate the shared HTTP readiness contract without optional dependencies."""

import unicodedata


MAX_PATH_UTF16_UNITS = 1024


def validate_healthcheck(raw, containers):
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("deployment.healthcheck must be an object")
    if any(key not in {"container", "port", "path"} for key in raw):
        raise ValueError("healthcheck contains unsupported fields")

    name = raw.get("container")
    if not isinstance(name, str) or not name:
        raise ValueError("healthcheck.container must be a non-empty string")
    by_name = {container["name"]: container for container in containers}
    if name not in by_name:
        raise ValueError("healthcheck.container must reference a declared container")
    port = raw.get("port")
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("healthcheck.port must be an integer in 1..65535")
    if port not in by_name[name]["ports"]:
        raise ValueError("healthcheck.port must reference a declared container port")

    path = raw.get("path")
    if not isinstance(path, str) or not path.startswith("/"):
        raise ValueError("healthcheck.path must be an absolute HTTP path")
    if any(
        character.isspace() or unicodedata.category(character) in {"Cc", "Cs"}
        for character in path
    ):
        raise ValueError("healthcheck.path must not contain whitespace or control characters")
    # Scheduler counts UTF-16 units; Runtime uses the same length convention.
    if sum(2 if ord(character) > 0xFFFF else 1 for character in path) > MAX_PATH_UTF16_UNITS:
        raise ValueError("healthcheck.path must not exceed 1024 UTF-16 units")
    return {"container": name, "port": port, "path": path}
