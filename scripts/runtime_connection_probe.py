#!/usr/bin/env python3
"""토큰 없이 HTTPS 연결과 인증 차단만 점검합니다. workload를 생성하지 않습니다."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request

from scripts.runtime_api_smoke_runner import build_runtime_opener, normalize_api_origin


def probe_connection(api_url):
    origin = normalize_api_origin(api_url)
    if not origin.startswith("https://"):
        raise ValueError("연결 사전 점검은 HTTPS API만 허용합니다")
    opener, _context = build_runtime_opener()
    request = Request(
        origin + "/internal/v1/instances/00000000-0000-4000-8000-000000000000/runtime-status",
        method="GET",
    )
    status_code = None
    error_code = None
    started = time.monotonic()
    try:
        with opener.open(request, timeout=15) as response:
            status_code = response.status
    except HTTPError as error:
        status_code = error.code
        error.close()
    except (URLError, TimeoutError, ConnectionError, OSError):
        error_code = "TLS_OR_NETWORK_FAILURE"
    expected = status_code == 401 and error_code is None
    return {
        "status": "TRANSPORT_AND_UNAUTHENTICATED_GATE_CONFIRMED" if expected else "FAILED",
        "api_origin": origin,
        "http_status": status_code,
        "error_code": error_code or (None if expected else "UNEXPECTED_HTTP_STATUS"),
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "certificate_verification_enabled": True,
        "authorization_header_sent": False,
        "authenticated_smoke_executed": False,
        "workload_created": False,
        "limitations": ["Runtime 배포 커밋 확인 아님", "인증·이미지 pull·생성·응답·삭제 확인 아님"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = probe_connection(args.api_url)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["http_status"] == 401 and result["error_code"] is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
