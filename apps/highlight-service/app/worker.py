from __future__ import annotations

import argparse
import json
import time

from .db import init_db
from .pipeline import run_next_pipeline_job


def main() -> None:
    parser = argparse.ArgumentParser(description="Run highlight-service pipeline jobs.")
    parser.add_argument("--once", action="store_true", help="Run at most one pending job and exit.")
    parser.add_argument("--interval", type=float, default=2.0, help="Polling interval in seconds.")
    parser.add_argument("--worker-id", default="", help="Optional worker identifier.")
    args = parser.parse_args()

    init_db()
    while True:
        result = run_next_pipeline_job(worker_id=args.worker_id or None)
        print(json.dumps(result, ensure_ascii=False, default=str), flush=True)
        if args.once:
            return
        if result.get("status") == "idle":
            time.sleep(max(0.2, args.interval))


if __name__ == "__main__":
    main()
