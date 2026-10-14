import json
import random
from pathlib import Path
import pandas as pd

SEED = 20261009
DATASET = Path("data/swebench/test-00000-of-00001.parquet")
EXISTING = Path("data/experiments/benchmark_v2_tasks.json")
OUTDIR = Path("data/experiments/benchmark_v2_1_pilot5")
OUTFILE = OUTDIR / "tasks.json"

# Previously used validation tasks.
excluded = {
    "astropy__astropy-12907",
    "astropy__astropy-13033",
    "pytest-dev__pytest-5221",
    "psf__requests-2148",
    "django__django-16429",
    "sympy__sympy-24443",
    "sympy__sympy-24539",
    "sympy__sympy-24661",
    "sympy__sympy-23950",
    "sympy__sympy-22914",
    "sympy__sympy-23262",
    "sympy__sympy-24562",
}

with EXISTING.open(encoding="utf-8") as f:
    old_manifest = json.load(f)

excluded.update(
    task["instance_id"] for task in old_manifest["tasks"]
)

df = pd.read_parquet(DATASET)

required = {"instance_id", "repo", "base_commit",
            "problem_statement"}
missing = required - set(df.columns)
if missing:
    raise RuntimeError(f"Dataset columns missing: {sorted(missing)}")

candidates = df[~df["instance_id"].isin(excluded)].copy()
candidates = candidates.drop_duplicates("instance_id")

if len(candidates) < 5:
    raise RuntimeError("Fewer than five eligible tasks remain.")

# Fixed, reproducible selection.
selected = candidates.sample(
    n=5, random_state=SEED
).sort_values("instance_id")

tasks = []
for _, row in selected.iterrows():
    tasks.append({
        "instance_id": str(row["instance_id"]),
        "repo": str(row["repo"]),
        "base_commit": str(row["base_commit"]),
        "problem_statement": str(row["problem_statement"]),
    })

OUTDIR.mkdir(parents=True, exist_ok=True)
manifest = {
    "pilot_name": "DDIV v2.1 five-task pilot",
    "selection_seed": SEED,
    "dataset": str(DATASET),
    "excluded_existing_manifest": str(EXISTING),
    "tasks": tasks,
}

OUTFILE.write_text(
    json.dumps(manifest, indent=2, ensure_ascii=False),
    encoding="utf-8",
)

print("Selected tasks:")
for t in tasks:
    print(f"- {t['instance_id']} | {t['repo']} | {t['base_commit']}")

print(f"\nTask count: {len(tasks)}")
print(f"Unique IDs: {len({t['instance_id'] for t in tasks})}")
print(f"Manifest: {OUTFILE}")
