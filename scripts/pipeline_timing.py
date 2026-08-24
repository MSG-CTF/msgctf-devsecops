#!/usr/bin/env python3
import argparse
import json
import sys
import time
from pathlib import Path


PHASES = ("build", "scan", "push")


def _load_state(path):
    path = Path(path)
    if not path.exists():
        return {"phases": {}}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("timing state must be valid JSON") from error
    if not isinstance(state, dict) or not isinstance(state.get("phases"), dict):
        raise ValueError("timing state must contain phases")
    return state


def _write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def start_phase(state_path, phase, now_ns):
    state = _load_state(state_path)
    if phase in state["phases"]:
        raise ValueError(f"{phase} phase already started")
    state["phases"][phase] = {"started_at_ns": now_ns}
    _write_json(state_path, state)


def stop_phase(state_path, phase, now_ns):
    state = _load_state(state_path)
    phase_state = state["phases"].get(phase)
    if not isinstance(phase_state, dict) or "started_at_ns" not in phase_state:
        raise ValueError(f"{phase} phase has not started")
    if "duration_seconds" in phase_state:
        raise ValueError(f"{phase} phase already stopped")
    started_at_ns = phase_state["started_at_ns"]
    if now_ns < started_at_ns:
        raise ValueError("current time is before phase start")
    phase_state["duration_seconds"] = round(
        (now_ns - started_at_ns) / 1_000_000_000,
        3,
    )
    _write_json(state_path, state)


def build_report(state_path):
    state = _load_state(state_path)
    report = {}
    for phase in PHASES:
        phase_state = state["phases"].get(phase)
        if not isinstance(phase_state, dict) or "duration_seconds" not in phase_state:
            raise ValueError(f"{phase} phase has not completed")
        report[f"{phase}_seconds"] = phase_state["duration_seconds"]
    report["total_seconds"] = round(
        sum(report[f"{phase}_seconds"] for phase in PHASES),
        3,
    )
    return report


def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command in ("start", "stop"):
        phase_parser = subparsers.add_parser(command)
        phase_parser.add_argument("--state", required=True, type=Path)
        phase_parser.add_argument("--phase", required=True, choices=PHASES)
        phase_parser.add_argument("--now-ns", type=int)

    report_parser = subparsers.add_parser("report")
    report_parser.add_argument("--state", required=True, type=Path)
    report_parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    try:
        if args.command in {"start", "stop"}:
            now_ns = args.now_ns if args.now_ns is not None else time.monotonic_ns()
            if now_ns < 0:
                raise ValueError("now-ns must not be negative")
            operation = start_phase if args.command == "start" else stop_phase
            operation(args.state, args.phase, now_ns)
        else:
            _write_json(args.output, build_report(args.state))
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
