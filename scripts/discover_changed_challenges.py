#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path, PurePosixPath


SAFE_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")


def discover_changed_challenges(root, changed_paths):
    root = Path(root).resolve()
    challenges = set()
    for raw_path in changed_paths:
        parts = PurePosixPath(raw_path.strip()).parts
        if not parts:
            continue
        challenge_name = parts[0]
        if not SAFE_NAME.fullmatch(challenge_name):
            continue
        if (root / challenge_name / "info.yaml").is_file():
            challenges.add(challenge_name)
    return sorted(challenges)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--paths-file", type=Path, required=True)
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()

    changed_paths = args.paths_file.read_text(encoding="utf-8").splitlines()
    challenges = discover_changed_challenges(args.root, changed_paths)
    matrix = {
        "include": [
            {"challenge_path": challenge_path}
            for challenge_path in challenges
        ]
    }
    encoded = json.dumps(matrix, ensure_ascii=False, separators=(",", ":"))
    print(encoded)
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as output:
            output.write(f"matrix={encoded}\n")
            output.write(f"count={len(challenges)}\n")


if __name__ == "__main__":
    main()
