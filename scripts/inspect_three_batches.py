import json
from pathlib import Path

p = Path("results/quixbugs_cloud_assisted_preflight_20261016T092253Z/unresolved_task_manifest.json")
tasks = json.loads(p.read_text(encoding="utf-8"))["tasks"]

b1 = tasks[0:9]
b2 = tasks[9:18]
b3 = tasks[18:27]

print("=== BATCH 1 (Day 1: 9 Tasks) ===")
for i, t in enumerate(b1, 1):
    print(f"{i}. {t['program_name']:<30} ({t['canonical_task_id']}) - {t['final_failure_category']}")

print("\n=== BATCH 2 (Day 2: 9 Tasks) ===")
for i, t in enumerate(b2, 1):
    print(f"{i}. {t['program_name']:<30} ({t['canonical_task_id']}) - {t['final_failure_category']}")

print("\n=== BATCH 3 (Day 3: 9 Tasks) ===")
for i, t in enumerate(b3, 1):
    print(f"{i}. {t['program_name']:<30} ({t['canonical_task_id']}) - {t['final_failure_category']}")
