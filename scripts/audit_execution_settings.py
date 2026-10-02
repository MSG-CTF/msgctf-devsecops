#!/usr/bin/env python3
"""실행 설정의 이름과 존재 여부만 수집하며 값이나 소스 내용을 출력하지 않습니다."""
import argparse
import json
import os
import re
from pathlib import Path

import yaml


NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
SERVICE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
COMPOSE_NAME = re.compile(r"^(?:docker-compose|compose)(?:\.[A-Za-z0-9_-]+)?\.ya?ml$")
ENV_REFERENCE = re.compile(
    r"(?:getenv|Getenv|environ\.get)\(\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]"
    r"|environ\[\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]\s*\]"
    r"|process\.env\.([A-Za-z_][A-Za-z0-9_]*)"
    r"|process\.env\[\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]\s*\]"
)
EXECUTION_FIELDS = (
    "environment", "env_file", "command", "entrypoint", "volumes", "tmpfs",
    "secrets", "configs", "healthcheck", "depends_on", "networks", "user",
    "working_dir", "read_only", "cap_add", "privileged", "network_mode",
)
SOURCE_SUFFIXES = {".py", ".js", ".ts", ".mjs", ".cjs", ".go", ".c", ".cpp", ".h"}
MAX_FILE_BYTES = 1024 * 1024
MAX_FILES = 5000


def _names(values, pattern=SERVICE_NAME):
    if not isinstance(values, (dict, list)):
        return []
    return sorted({value for value in values if isinstance(value, str) and pattern.fullmatch(value)})


def _read(path):
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("file_too_large")
    return path.read_text(encoding="utf-8")


def _files(challenge):
    # 참가자 파일, exploit, 의존 패키지와 링크는 실행 설정 점검에서 제외합니다.
    ignored = {".git", "exploit", "for_user", "node_modules", "vendor", "__pycache__", ".venv"}
    count = 0
    for directory, folders, files in os.walk(challenge, followlinks=False):
        folders[:] = sorted(name for name in folders if name not in ignored and not (Path(directory) / name).is_symlink())
        for name in sorted(files):
            path = Path(directory) / name
            if path.is_symlink() or not path.is_file():
                continue
            path.resolve().relative_to(challenge)
            count += 1
            if count > MAX_FILES:
                raise ValueError("file_limit")
            yield path


def _compose(path, relative):
    result = {"path": relative, "services": [], "networks": [], "internal_networks": []}
    try:
        raw = yaml.safe_load(_read(path))
        if not isinstance(raw, dict) or not isinstance(raw.get("services"), dict):
            raise ValueError("compose_invalid")
        networks = raw.get("networks", {})
        result["networks"] = _names(networks)
        if isinstance(networks, dict):
            result["internal_networks"] = sorted(name for name in result["networks"] if isinstance(networks[name], dict) and networks[name].get("internal") is True)
        for name in _names(raw["services"]):
            service = raw["services"][name]
            if not isinstance(service, dict):
                raise ValueError("compose_invalid")
            environment = service.get("environment", {})
            if isinstance(environment, dict):
                environment_names = _names(environment, NAME)
            elif isinstance(environment, list):
                environment_names = _names([item.split("=", 1)[0] for item in environment if isinstance(item, str)], NAME)
            else:
                environment_names = []
            result["services"].append({
                "name": name,
                "environment_names": environment_names,
                "execution_fields": [field for field in EXECUTION_FIELDS if field in service],
                "networks": _names(service.get("networks", [])),
                "depends_on": _names(service.get("depends_on", [])),
            })
    except yaml.YAMLError:
        result["error"] = "yaml_unparsed"
    except (OSError, UnicodeError, ValueError, RecursionError):
        result["error"] = "compose_unreadable"
    return result


def audit_challenge(challenge_path):
    original = Path(challenge_path)
    if original.is_symlink():
        raise ValueError("문제 폴더 링크는 지원하지 않습니다")
    challenge = original.resolve(strict=True)
    if not challenge.is_dir() or not SERVICE_NAME.fullmatch(challenge.name):
        raise ValueError("문제 폴더 이름을 확인하세요")
    info_path = challenge / "info.yaml"
    if info_path.is_symlink():
        raise ValueError("info.yaml 링크는 지원하지 않습니다")
    report = {
        "challenge_slug": challenge.name,
        "is_server": False,
        "info_healthcheck_present": False,
        "info_container_names": [],
        "compose": [],
        "environment_references": [],
        "review_required": [],
        "incomplete": False,
    }
    try:
        info = yaml.safe_load(_read(info_path))
        if not isinstance(info, dict):
            raise ValueError("info_invalid")
        deployment = info.get("deployment")
        report["is_server"] = deployment is not None
        if isinstance(deployment, dict):
            report["info_healthcheck_present"] = isinstance(deployment.get("healthcheck"), dict)
            containers = deployment.get("containers", [])
            if isinstance(containers, list):
                report["info_container_names"] = _names([item.get("name") for item in containers if isinstance(item, dict)])
    except (OSError, UnicodeError, ValueError, yaml.YAMLError, RecursionError):
        report["info_error"] = "info_unreadable"
        report["incomplete"] = True
    try:
        for path in _files(challenge):
            relative = path.relative_to(challenge).as_posix()
            organizer = relative.startswith("prob/for_organizer/")
            root_file = path.parent == challenge
            if COMPOSE_NAME.fullmatch(path.name) and (organizer or root_file):
                report["compose"].append(_compose(path, relative))
            if not organizer:
                continue
            is_env = path.name == ".env" or path.name.startswith(".env.")
            if path.suffix not in SOURCE_SUFFIXES and not is_env and path.name != "Dockerfile":
                continue
            try:
                content = _read(path)
            except (OSError, UnicodeError, ValueError):
                report["incomplete"] = True
                continue
            names = {next(group for group in match.groups() if group) for match in ENV_REFERENCE.finditer(content)}
            if is_env:
                names.update(re.findall(r"(?m)^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=", content))
            if path.name == "Dockerfile":
                names.update(re.findall(r"(?mi)^\s*ENV\s+([A-Za-z_][A-Za-z0-9_]*)(?:\s|=)", content))
            report["environment_references"].extend({"path": relative, "name": name} for name in sorted(names) if NAME.fullmatch(name))
    except (OSError, ValueError):
        report["incomplete"] = True
    review = set()
    if report["environment_references"]:
        review.add("environment")
    for compose in report["compose"]:
        if "error" in compose:
            report["incomplete"] = True
        if len(compose["networks"]) > 1 or compose["internal_networks"]:
            review.add("network_segmentation")
        for service in compose["services"]:
            review.update(service["execution_fields"])
            if service["name"] not in report["info_container_names"]:
                review.add("container_mapping")
    report["review_required"] = sorted(review)
    return report


def _cell(text):
    return str(text).replace("|", "\\|").replace("`", "").replace("\n", " ").replace("\r", " ")


def render_markdown(reports, source_sha):
    dynamic = sum(report["is_server"] for report in reports)
    lines = [
        "# 문제 실행 설정 점검", "",
        f"기준 source_sha: `{_cell(source_sha)}`", "",
        f"총 {len(reports)}개: 서버 문제 {dynamic}개, 정적 문제 {len(reports) - dynamic}개.", "",
        "설정 이름과 존재 여부만 점검했습니다. 빌드·취약점 검사·배포 성공을 의미하지 않습니다.",
        "환경변수 참조는 후보이며 필수 여부와 Compose 서비스 대응은 출제자 확인이 필요합니다.", "",
        "| 문제 | 구분 | info healthcheck | 환경변수 이름(후보) | 확인 필요한 설정 | 점검 |",
        "|---|---|---|---|---|---|",
    ]
    for report in reports:
        environment = {item["name"] for item in report["environment_references"]}
        for compose in report["compose"]:
            for service in compose["services"]:
                environment.update(service["environment_names"])
        cells = [report["challenge_slug"], "서버" if report["is_server"] else "정적",
                 "있음" if report["info_healthcheck_present"] else "없음",
                 ", ".join(sorted(environment)[:8]) + (f" 외 {len(environment) - 8}개(JSON 참고)" if len(environment) > 8 else "") or "미발견",
                 ", ".join(report["review_required"]) or "미발견",
                 "일부 미점검" if report["incomplete"] else "완료"]
        lines.append("| " + " | ".join(_cell(cell) for cell in cells) + " |")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="문제 실행 설정 이름만 점검합니다")
    parser.add_argument("path", type=Path)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.source_sha):
        parser.error("source-sha는 40자리 commit SHA여야 합니다")
    root = args.path
    paths = [root] if (root / "info.yaml").exists() else sorted(path.parent for path in root.glob("*/info.yaml") if not path.parent.is_symlink())
    if not paths:
        parser.error("info.yaml이 있는 문제를 찾지 못했습니다")
    reports = [audit_challenge(path) for path in paths]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    payload = {"schema_version": "1.0", "source_sha": args.source_sha, "audit_only": True, "challenges": reports}
    (args.output_dir / "execution-settings.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.output_dir / "execution-settings.md").write_text(render_markdown(reports, args.source_sha), encoding="utf-8")
    print(f"{len(reports)}개 문제 실행 설정 점검 자료 생성(값은 포함하지 않음)")


if __name__ == "__main__":
    main()
