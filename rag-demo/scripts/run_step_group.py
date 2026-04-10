#!/usr/bin/env python3
"""Run predefined RAG pipeline step groups sequentially."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


STEP_GROUPS: dict[str, list[list[str]]] = {
    "upload": [
        ["steps/01-extract-metadata/run_step_01_extract_metadata.py"],
        ["steps/02-build-vector-store/run_step_02_build_vector_store.py"],
    ],
    "query": [
        ["scripts/run_query_pipeline.py"],
    ],
    "full": [
        ["steps/01-extract-metadata/run_step_01_extract_metadata.py"],
        ["steps/02-build-vector-store/run_step_02_build_vector_store.py"],
        ["scripts/run_query_pipeline.py"],
    ],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--group", choices=sorted(STEP_GROUPS), required=True)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without running them.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]

    for index, step_args in enumerate(STEP_GROUPS[args.group], start=1):
        command = [sys.executable, *step_args]
        print(f"[{index}/{len(STEP_GROUPS[args.group])}] {' '.join(command)}")
        if args.dry_run:
            continue
        subprocess.run(command, cwd=repo_root, check=True)

    print(f"Completed group: {args.group}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
