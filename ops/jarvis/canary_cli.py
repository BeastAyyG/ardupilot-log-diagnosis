"""Command-line entry point for the JarvisLabs canary."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from pathlib import Path

from ops.jarvis.run_dstack_canary import (
    DEFAULT_TIMEOUT_SECONDS,
    CanaryError,
    run_canary,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-key-env", default="JL_API_KEY")
    parser.add_argument("--dstack", dest="dstack_executable")
    parser.add_argument("--region")
    parser.add_argument("--results-dir", default="artifacts/jarvis-canary")
    parser.add_argument(
        "--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS
    )
    args = parser.parse_args(argv)
    api_key = os.environ.get(args.api_key_env, "")
    try:
        summary = run_canary(
            api_key=api_key,
            repo_root=Path(__file__).resolve().parents[2],
            results_dir=Path(args.results_dir).resolve(),
            dstack_executable=args.dstack_executable,
            region=args.region,
            timeout_seconds=args.timeout_seconds,
        )
    except CanaryError as exc:
        print(
            json.dumps(
                {
                    "schema": "logdiagnosis.jarvislabs-dstack-canary/v1",
                    "status": "failed",
                    "error": str(exc),
                }
            )
        )
        return 1
    print(json.dumps(summary, sort_keys=True))
    return 0
