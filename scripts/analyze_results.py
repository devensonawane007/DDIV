"""CLI tool to analyze execution trace logs and compute comparative research tables."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


def main():
    parser = argparse.ArgumentParser(description="Analyze DDIV experiment trace logs.")
    parser.add_argument("--logs-dir", type=str, default="logs/runs", help="Directory containing .jsonl run traces")
    args = parser.parse_args()

    log_path = Path(args.logs_dir)
    if not log_path.exists():
        print(f"Log directory not found: {log_path}")
        return

    files = list(log_path.glob("*.jsonl"))
    if not files:
        print(f"No JSONL trace files found in {log_path}")
        return

    total_runs = 0
    resolved_runs = 0
    failure_counts = {"F1": 0, "F2": 0, "F3": 0, "F4": 0}

    for f in files:
        total_runs += 1
        with open(f, "r", encoding="utf-8") as fp:
            for line in fp:
                try:
                    data = json.loads(line.strip())
                    if data.get("final_result") == "SUCCESS":
                        resolved_runs += 1
                    ftype = data.get("failure")
                    if ftype in failure_counts:
                        failure_counts[ftype] += 1
                except Exception:
                    pass

    print("\n" + "=" * 60)
    print(f" EXPERIMENT ANALYSIS REPORT ({len(files)} runs analyzed)")
    print("=" * 60)
    print(f" Total Runs Analyzed:     {total_runs}")
    print(f" Success / Resolved:      {resolved_runs}")
    print(f" Resolved Rate:           {(resolved_runs / total_runs * 100):.1f}%" if total_runs else "N/A")
    print("\n Detected Failure Frequency:")
    for ftype, count in failure_counts.items():
        print(f"   - {ftype}: {count}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
