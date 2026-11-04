#!/usr/bin/env python3
"""Sample an explicitly approved public WEB endpoint without switching traffic."""

import argparse
from datetime import datetime, timezone
import hashlib
import http.client
import ipaddress
import json
import math
from pathlib import Path
import re
import socket
import ssl
import sys
import time
from urllib.parse import urlsplit

from scripts.prepare_release_transition import plan_hash, require
from scripts.vm_image_prefetch import read_json, save_private


def validate_endpoint(url, *, allow_http=False, resolver=socket.getaddrinfo):
    require(isinstance(url, str) and 1 <= len(url) <= 2048
            and all(33 <= ord(char) <= 126 for char in url), "INVALID_ENDPOINT")
    parsed = urlsplit(url)
    require(parsed.scheme == "https" or (allow_http and parsed.scheme == "http"), "HTTPS_REQUIRED")
    require(parsed.hostname and parsed.username is None and parsed.password is None
            and not parsed.query and not parsed.fragment and "?" not in url and "#" not in url,
            "ENDPOINT_CREDENTIALS_QUERY_OR_FRAGMENT_FORBIDDEN")
    path = parsed.path or "/"
    require(re.fullmatch(r"/[A-Za-z0-9._~/-]*", path) and "//" not in path
            and not {".", ".."}.intersection(path.split("/")), "UNSAFE_ENDPOINT_PATH")
    host = parsed.hostname
    require(not host.endswith((".internal", ".localhost", ".local")) and host != "localhost")
    port = parsed.port if parsed.port is not None else (443 if parsed.scheme == "https" else 80)
    require(1 <= port <= 65535)
    answers = resolver(host, port, type=socket.SOCK_STREAM)
    require(answers, "NO_PUBLIC_ENDPOINT_ADDRESS")
    addresses = []
    for answer in answers:
        address = ipaddress.ip_address(answer[4][0])
        require(address.is_global and not address.is_multicast, "NONPUBLIC_ENDPOINT_FORBIDDEN")
        addresses.append(str(address))
    return {"host": host, "port": port, "address": addresses[0], "path": path,
            "scheme": parsed.scheme}


class PinnedConnection(http.client.HTTPConnection):
    def __init__(self, endpoint, timeout):
        super().__init__(endpoint["host"], endpoint["port"], timeout=timeout)
        self.address = endpoint["address"]
        self.context = ssl.create_default_context() if endpoint["scheme"] == "https" else None

    def connect(self):
        raw = socket.create_connection((self.address, self.port), self.timeout)
        try:
            # Keep the original hostname for Host/SNI and certificate verification.
            self.sock = self.context.wrap_socket(raw, server_hostname=self.host) if self.context else raw
        except BaseException:
            raw.close()
            raise


def probe(endpoint, timeout):
    connection = PinnedConnection(endpoint, timeout)
    try:
        connection.request("GET", endpoint["path"], headers={"Cache-Control": "no-cache",
                           "Connection": "close", "User-Agent": "msgctf-rollout-observer/1"})
        response = connection.getresponse()
        try:
            return {"http_status": response.status, "error_code": None}
        finally:
            response.close()
    except ssl.SSLError:
        return {"http_status": None, "error_code": "TLS_FAILURE"}
    except TimeoutError:
        return {"http_status": None, "error_code": "REQUEST_TIMEOUT"}
    except (OSError, http.client.HTTPException):
        return {"http_status": None, "error_code": "NETWORK_OR_PROTOCOL_FAILURE"}
    finally:
        connection.close()


def observe(url, plan, *, duration_seconds=60, interval_seconds=1, timeout_seconds=2,
            expected_status=200, allow_http=False, resolver=socket.getaddrinfo,
            request=probe, monotonic=time.monotonic, sleep=time.sleep, on_result=None):
    require(isinstance(plan, dict) and plan.get("scope") == "OFFLINE_WEB_RELEASE_TRANSITION_PREPARATION"
            and plan.get("plan_sha256") == plan_hash(plan), "INVALID_TRANSITION_PLAN")
    require(type(duration_seconds) is int and 1 <= duration_seconds <= 900)
    for value, minimum, maximum in ((interval_seconds, 0.25, 30), (timeout_seconds, 0.25, 10)):
        require(type(value) in (float, int) and math.isfinite(value) and minimum <= value <= maximum)
    require(math.ceil(duration_seconds / interval_seconds) <= 300)
    require(type(expected_status) is int and 200 <= expected_status <= 299)
    endpoint = validate_endpoint(url, allow_http=allow_http, resolver=resolver)
    result = {"schema_version": "1.0", "scope": "SAMPLED_PUBLIC_HTTP_AVAILABILITY_ONLY",
              "plan_sha256": plan["plan_sha256"], "endpoint_sha256": hashlib.sha256(url.encode()).hexdigest(),
              "status": "RUNNING", "samples": [], "expected_http_status": expected_status,
              "duration_seconds": duration_seconds, "interval_seconds": interval_seconds,
              "timeout_seconds": timeout_seconds, "started_at": datetime.now(timezone.utc).isoformat(),
              "https_certificate_verification_enabled": endpoint["scheme"] == "https",
              "http_explicitly_allowed": endpoint["scheme"] == "http" and allow_http,
              "limits": {"authorization_sent": False, "response_body_saved": False,
                         "redirect_followed": False, "proxy_environment_used": False,
                         "activation_requested": False, "instance_created_or_deleted": False,
                         "version_b_verified": False, "existing_tcp_sessions_verified": False,
                         "between_sample_availability_proven": False, "zero_downtime_proven": False}}
    start = monotonic()
    try:
        index = 0
        while monotonic() - start < duration_seconds and index < 300:
            due = start + index * interval_seconds
            if due > monotonic():
                sleep(min(due - monotonic(), max(0, duration_seconds - (monotonic() - start))))
            remaining = duration_seconds - (monotonic() - start)
            if remaining <= 0:
                break
            sampled_at, began = datetime.now(timezone.utc).isoformat(), monotonic()
            reply = request(endpoint, min(timeout_seconds, remaining))
            require(isinstance(reply, dict) and set(reply) == {"http_status", "error_code"})
            status, error = reply["http_status"], reply["error_code"]
            require(status is None or type(status) is int and 100 <= status <= 599)
            require(error in {None, "TLS_FAILURE", "REQUEST_TIMEOUT", "NETWORK_OR_PROTOCOL_FAILURE"})
            require((status is None) == (error is not None))
            result["samples"].append({"sampled_at": sampled_at, "offset_seconds": round(began - start, 6),
                                      "elapsed_seconds": round(monotonic() - began, 6),
                                      "http_status": status, "error_code": error,
                                      "passed": error is None and status == expected_status})
            if on_result:
                on_result(result)
            # Do not issue a catch-up burst after a slow request.
            index = max(index + 1, math.floor((monotonic() - start) / interval_seconds) + 1)
        result["status"] = ("NO_HTTP_FAILURE_OBSERVED" if result["samples"]
                            and all(row["passed"] for row in result["samples"]) else "HTTP_FAILURE_OBSERVED")
    except KeyboardInterrupt:
        result["status"] = "INTERRUPTED"
    except (ValueError, OSError, TypeError, KeyError):
        result["status"] = "OBSERVER_FAILED"
        raise
    finally:
        result["finished_at"] = datetime.now(timezone.utc).isoformat()
        result["elapsed_seconds"] = round(monotonic() - start, 6)
        result["sample_count"] = len(result["samples"])
        result["failure_count"] = sum(not row["passed"] for row in result["samples"])
        if on_result:
            on_result(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--url", required=True)
    parser.add_argument("--duration-seconds", type=int, default=60)
    parser.add_argument("--interval-seconds", type=float, default=1)
    parser.add_argument("--timeout-seconds", type=float, default=2)
    parser.add_argument("--expected-status", type=int, default=200)
    parser.add_argument("--allow-http", action="store_true")
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        plan = read_json(args.plan)
        output = args.output_dir
        output.mkdir(mode=0o700, parents=True, exist_ok=False)
        result = observe(args.url, plan, duration_seconds=args.duration_seconds,
            interval_seconds=args.interval_seconds, timeout_seconds=args.timeout_seconds,
            expected_status=args.expected_status, allow_http=args.allow_http,
            on_result=lambda value: save_private(output / "http-observation.json", value))
    except (ValueError, OSError, TypeError, KeyError, OverflowError, RecursionError):
        print("HTTP observation failed: check approved endpoint, plan and private output path.", file=sys.stderr)
        return 2
    print(json.dumps({"status": result["status"], "sample_count": result["sample_count"],
                      "failure_count": result["failure_count"], "zero_downtime_proven": False}))
    return 0 if result["status"] == "NO_HTTP_FAILURE_OBSERVED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
