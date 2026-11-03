#!/usr/bin/env python3
"""관리자 발행 요청을 실행 SHA와 대조합니다. 빌드나 API 호출은 하지 않습니다."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path


REPOSITORY = "MSG-CTF/2026_MSG_CTF"
SHA = re.compile(r"[0-9a-f]{40}")
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
POSITIVE_INTEGER = re.compile(r"[1-9][0-9]*")


class RequestValidationError(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise RequestValidationError(code)


def validate_request(context, tools_sha):
    require(context.get("GITHUB_EVENT_NAME") == "workflow_dispatch", "EVENT_NOT_ALLOWED")
    require(context.get("GITHUB_REPOSITORY") == REPOSITORY, "REPOSITORY_NOT_ALLOWED")
    require(context.get("GITHUB_REF") == "refs/heads/main", "REF_NOT_ALLOWED")
    slug = context.get("CHALLENGE_PATH", "")
    require(isinstance(slug, str) and SLUG.fullmatch(slug), "CHALLENGE_SLUG_INVALID")
    expected = context.get("EXPECTED_SOURCE_SHA", "")
    actual = context.get("GITHUB_SHA", "")
    workflow_sha = context.get("GITHUB_WORKFLOW_SHA", "")
    require(isinstance(expected, str) and SHA.fullmatch(expected), "EXPECTED_SHA_REQUIRED")
    require(isinstance(actual, str) and SHA.fullmatch(actual), "RUN_SHA_INVALID")
    require(expected == actual, "SOURCE_SHA_MISMATCH")
    require(isinstance(workflow_sha, str) and SHA.fullmatch(workflow_sha), "WORKFLOW_SHA_INVALID")
    require(isinstance(tools_sha, str) and SHA.fullmatch(tools_sha), "TOOLS_SHA_INVALID")
    require(context.get("SOURCE_REF", "") in ("", expected), "SOURCE_REF_NOT_ALLOWED")
    request_id = context.get("PUBLICATION_REQUEST_ID", "")
    try:
        parsed_id = uuid.UUID(request_id)
    except (ValueError, TypeError, AttributeError):
        raise RequestValidationError("REQUEST_ID_REQUIRED") from None
    require(str(parsed_id) == request_id and parsed_id.int != 0, "REQUEST_ID_INVALID")
    run_id = context.get("GITHUB_RUN_ID", "")
    attempt = context.get("GITHUB_RUN_ATTEMPT", "")
    require(isinstance(run_id, str) and POSITIVE_INTEGER.fullmatch(run_id), "RUN_ID_INVALID")
    require(isinstance(attempt, str) and POSITIVE_INTEGER.fullmatch(attempt), "RUN_ATTEMPT_INVALID")
    identity = {
        "repository": REPOSITORY,
        "challenge_slug": slug,
        "source_sha": expected,
        "devsecops_sha": tools_sha,
    }
    request_key = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": "1.0",
        **identity,
        "request_id": request_id,
        "request_key": request_key,
        "source_ref": "refs/heads/main",
        "workflow_sha": workflow_sha,
        "run_id": int(run_id),
        "run_attempt": int(attempt),
        "run_url": f"https://github.com/{REPOSITORY}/actions/runs/{run_id}",
        "request_validation": "PASS",
        "publication_status": "NOT_YET_VERIFIED",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        tools_sha = subprocess.run(
            ["git", "-C", str(Path(__file__).resolve().parents[1]), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True, timeout=10,
        ).stdout.strip()
        result = validate_request(os.environ, tools_sha)
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    except RequestValidationError as error:
        print(f"PUBLICATION_REQUEST_REJECTED: {error}", file=sys.stderr)
        return 1
    except (OSError, subprocess.SubprocessError):
        print("PUBLICATION_REQUEST_REJECTED: REQUEST_RECORD_FAILED", file=sys.stderr)
        return 1
    print("발행 요청의 문제·실행 SHA·요청 ID 확인 완료. 검사·발행 성공은 별도 확인이 필요합니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
