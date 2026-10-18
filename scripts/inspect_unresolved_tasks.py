import json
from pathlib import Path

src = Path("D:/DDIV/results/quixbugs_benchmark_40tasks_20261016T125500Z")
tasks = sorted([p.name for p in src.iterdir() if p.is_dir() and not p.name.startswith(".")])

unres = []
for t in tasks:
    f_res = json.loads((src / t / "full_ddiv" / "condition_result.json").read_text(encoding="utf-8"))
    if not f_res.get("resolved", False):
        last_hist = f_res.get("history", [])[-1]
        unres.append({
            "task_id": f_res.get("task_id"),
            "program_name": t,
            "attempts": f_res.get("attempts_used"),
            "failure_category": last_hist.get("failure_category", "UNKNOWN"),
            "verdict": last_hist.get("evaluation_verdict", "UNKNOWN"),
            "patch_applied": last_hist.get("candidate_patch_applied", False),
            "patch_diff_len": len(last_hist.get("patch_diff", "")),
        })

print(f"Total unresolved tasks: {len(unres)}")
for u in unres:
    pname = u['program_name']
    fcat = u['failure_category']
    verd = u['verdict']
    appl = u['patch_applied']
    print(f"{pname:<30} - {fcat:<25} - {verd:<30} - applied={appl}")
