"""CLI and utility to aggregate DDIV experiment result records and produce research evaluation reports."""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.metrics import (
    ConditionAggregateMetrics,
    ConfusionMatrixResult,
    aggregate_condition_metrics,
    format_value,
    generate_summary_table,
)


def is_record_file(data: Dict[str, Any]) -> bool:
    """Check if a parsed JSON object has the structure of an ExperimentConditionRecord."""
    required = ("condition", "status")
    return all(k in data for k in required) or ("task_id" in data and "resolved" in data and "condition" in data)


def load_records_from_paths(paths: List[str]) -> List[Dict[str, Any]]:
    """Scan file paths or directories/globs and load all valid ExperimentConditionRecord JSONs."""
    found_files: List[Path] = []

    for p in paths:
        # Check if p is a glob pattern
        expanded = glob.glob(p, recursive=True)
        if expanded:
            for item in expanded:
                path_obj = Path(item)
                if path_obj.is_file() and path_obj.suffix == ".json":
                    if path_obj.name not in ("manifest.json", "summary.json"):
                        found_files.append(path_obj)
                elif path_obj.is_dir():
                    for json_f in path_obj.glob("**/*.json"):
                        if json_f.name not in ("manifest.json", "summary.json"):
                            found_files.append(json_f)
        else:
            path_obj = Path(p)
            if path_obj.is_file() and path_obj.suffix == ".json":
                found_files.append(path_obj)
            elif path_obj.is_dir():
                for json_f in path_obj.glob("**/*.json"):
                    if json_f.name not in ("manifest.json", "summary.json"):
                        found_files.append(json_f)

    # Deduplicate paths
    unique_files = sorted(set(found_files))
    records: List[Dict[str, Any]] = []

    for f in unique_files:
        try:
            with open(f, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            if isinstance(data, dict) and is_record_file(data):
                data["_source_file"] = str(f)
                from core.metrics import compute_task_metrics, compute_task_failure_detection
                if "metrics" not in data or data.get("pass_at_1") is None:
                    tm = compute_task_metrics(data)
                    data["metrics"] = tm.model_dump()
                    data["pass_at_1"] = tm.pass_at_1
                if "failure_detection" not in data:
                    tfd = compute_task_failure_detection(data)
                    if tfd:
                        data["failure_detection"] = tfd.model_dump()
                records.append(data)
        except Exception:
            continue

    return records


def group_records_by_condition(records: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Group result records by standard condition names (BASELINE, RETRY_ONLY, FULL_DDIV)."""
    grouped: Dict[str, List[Dict[str, Any]]] = {
        "BASELINE": [],
        "RETRY_ONLY": [],
        "FULL_DDIV": [],
    }

    for r in records:
        raw_cond = str(r.get("condition", "")).strip().upper()
        if "BASELINE" in raw_cond:
            grouped["BASELINE"].append(r)
        elif "RETRY" in raw_cond:
            grouped["RETRY_ONLY"].append(r)
        elif "DDIV" in raw_cond:
            grouped["FULL_DDIV"].append(r)
        else:
            grouped.setdefault(raw_cond, []).append(r)

    # Filter out empty condition buckets that aren't standard
    return {k: v for k, v in grouped.items() if v}


def generate_confusion_matrix_table(cm: ConfusionMatrixResult) -> str:
    """Format ConfusionMatrixResult into a readable Markdown table."""
    headers = ["Actual \\ Predicted", "F1", "F2", "F3", "F4", "Total Actual"]
    rows = []
    classes = cm.classes

    for c in classes:
        actual_total = sum(cm.matrix.get(c, {}).get(p, 0) for p in classes)
        row = [
            c,
            *(str(cm.matrix.get(c, {}).get(p, 0)) for p in classes),
            str(actual_total),
        ]
        rows.append(row)

    # Predicted totals
    pred_totals = [str(sum(cm.matrix.get(act, {}).get(p, 0) for act in classes)) for p in classes]
    all_total = str(cm.total_samples)
    rows.append(["Total Predicted", *pred_totals, all_total])

    col_widths = [max(len(str(item)) for item in col) for col in zip(headers, *rows)]
    header_line = " | ".join(f"{h:<{w}}" for h, w in zip(headers, col_widths))
    sep_line = "-|-".join("-" * w for w in col_widths)

    out = [f"| {header_line} |", f"| {sep_line} |"]
    for r in rows:
        line = " | ".join(f"{item:<{w}}" for item, w in zip(r, col_widths))
        out.append(f"| {line} |")

    # Add per-class precision / recall / F1
    out.append("")
    out.append("### Per-Class Fault Taxonomy Metrics")
    pc_headers = ["Class", "Description", "TP", "FP", "FN", "Precision", "Recall", "F1"]
    desc_map = {
        "F1": "Localization Failure",
        "F2": "Code / Reasoning Failure",
        "F3": "Tool / Patch Execution Failure",
        "F4": "Coordination / Timeout Failure",
    }
    pc_rows = []
    for c in classes:
        cm_item = cm.per_class.get(c)
        prec_str = format_value(cm_item.precision, is_pct=True) if cm_item else "N/A"
        rec_str = format_value(cm_item.recall, is_pct=True) if cm_item else "N/A"
        f1_str = format_value(cm_item.f1, is_pct=True) if cm_item else "N/A"
        tp_str = str(cm_item.tp) if cm_item else "0"
        fp_str = str(cm_item.fp) if cm_item else "0"
        fn_str = str(cm_item.fn) if cm_item else "0"
        pc_rows.append([c, desc_map.get(c, ""), tp_str, fp_str, fn_str, prec_str, rec_str, f1_str])

    pc_col_widths = [max(len(str(item)) for item in col) for col in zip(pc_headers, *pc_rows)]
    pc_header_line = " | ".join(f"{h:<{w}}" for h, w in zip(pc_headers, pc_col_widths))
    pc_sep_line = "-|-".join("-" * w for w in pc_col_widths)
    out.append(f"| {pc_header_line} |")
    out.append(f"| {pc_sep_line} |")
    for r in pc_rows:
        line = " | ".join(f"{item:<{w}}" for item, w in zip(r, pc_col_widths))
        out.append(f"| {line} |")

    out.append("")
    out.append(f"- **Macro-Precision**: {format_value(cm.macro_precision, is_pct=True)}")
    out.append(f"- **Macro-Recall**: {format_value(cm.macro_recall, is_pct=True)}")
    out.append(f"- **Macro-F1**: {format_value(cm.macro_f1, is_pct=True)}")
    out.append(f"- **Total Evaluated Samples**: {cm.total_samples}")
    out.append(f"- **Unlabeled / Ambiguous Samples**: {cm.unlabeled_samples}")

    return "\n".join(out)


def generate_task_breakdown_table(records: List[Dict[str, Any]]) -> str:
    """Format individual task execution records for research traceability."""
    headers = [
        "Task ID",
        "Condition",
        "Attempts",
        "Resolved",
        "Pass@1",
        "Duration (s)",
        "Tokens",
        "Calls",
        "Pred Fault",
        "Actual Fault",
    ]
    rows = []
    for r in sorted(records, key=lambda x: (x.get("task_id", ""), str(x.get("condition", "")))):
        task_id = str(r.get("task_id", ""))
        cond = str(r.get("condition", "")).upper()
        attempts = str(r.get("attempts", 1))
        resolved = "YES" if r.get("resolved") else "NO"
        pass_at_1 = "YES" if r.get("pass_at_1") else "NO"
        dur = f"{float(r.get('execution_duration_seconds', 0.0) or 0.0):.1f}"

        m = r.get("metrics") or {}
        tokens = str(m.get("total_tokens")) if m.get("total_tokens") is not None else "N/A"
        calls = str(m.get("inference_calls", "N/A"))

        fd = r.get("failure_detection") or {}
        pred_f = str(fd.get("predicted_category") or "-")
        act_f = str(fd.get("actual_category") or "-")

        rows.append([task_id, cond, attempts, resolved, pass_at_1, dur, tokens, calls, pred_f, act_f])

    col_widths = [max(len(str(item)) for item in col) for col in zip(headers, *rows)]
    header_line = " | ".join(f"{h:<{w}}" for h, w in zip(headers, col_widths))
    sep_line = "-|-".join("-" * w for w in col_widths)

    out = [f"| {header_line} |", f"| {sep_line} |"]
    for r in rows:
        line = " | ".join(f"{item:<{w}}" for item, w in zip(r, col_widths))
        out.append(f"| {line} |")

    return "\n".join(out)


def build_full_report(
    records: List[Dict[str, Any]],
    detailed: bool = False,
) -> Tuple[str, Dict[str, ConditionAggregateMetrics]]:
    """Build complete evaluation report including summary table, confusion matrix, and details."""
    grouped = group_records_by_condition(records)
    aggregates: Dict[str, ConditionAggregateMetrics] = {}

    for cond, cond_records in grouped.items():
        aggregates[cond] = aggregate_condition_metrics(cond_records, cond)

    summary_table = generate_summary_table(aggregates)

    sections = [
        "# DDIV Research Experiment Evaluation Report",
        "",
        "## Summary Performance Metrics",
        "",
        summary_table,
    ]

    # Add Confusion Matrix if FULL_DDIV has samples
    full_ddiv_agg = aggregates.get("FULL_DDIV")
    if full_ddiv_agg and full_ddiv_agg.failure_detection:
        sections.extend([
            "",
            "## Failure Detection Confusion Matrix (FULL_DDIV)",
            "",
            generate_confusion_matrix_table(full_ddiv_agg.failure_detection),
        ])

    if detailed and records:
        sections.extend([
            "",
            "## Task-Level Execution Traceability",
            "",
            generate_task_breakdown_table(records),
        ])

    return "\n".join(sections), aggregates


def main():
    parser = argparse.ArgumentParser(
        description="Aggregate DDIV experiment result records and generate evaluation report."
    )
    parser.add_argument(
        "--dir",
        type=str,
        nargs="+",
        default=["data/experiments"],
        help="Directories, result files, or glob patterns to aggregate.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Optional destination path to save the generated report (markdown or json).",
    )
    parser.add_argument(
        "--format",
        choices=["table", "markdown", "json"],
        default="table",
        help="Output format: table (default), markdown, or json.",
    )
    parser.add_argument(
        "--detailed",
        action="store_true",
        help="Include per-task breakdown and complete failure taxonomy matrices.",
    )
    args = parser.parse_args()

    records = load_records_from_paths(args.dir)
    if not records:
        print(f"No experiment condition records found in: {args.dir}", file=sys.stderr)
        sys.exit(1)

    report_text, aggregates = build_full_report(records, detailed=args.detailed)

    if args.format == "json":
        json_output = {
            cond: agg.model_dump()
            for cond, agg in aggregates.items()
        }
        output_str = json.dumps(json_output, indent=2)
    else:
        output_str = report_text

    print(output_str)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output_str, encoding="utf-8")
        print(f"\nReport saved to: {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
