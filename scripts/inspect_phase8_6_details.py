import sqlite3
import json
from pathlib import Path

src = Path("D:/DDIV/results/quixbugs_benchmark_40tasks_20261016T125500Z")
db_path = src / "quixbugs_40tasks_memory.db"
conn = sqlite3.connect(db_path)
cur = conn.cursor()

print("--- Quicksort in Memory ---")
cur.execute("SELECT task_id, attempt, failure_type, diagnosis, recovery_action FROM memory_records WHERE task_id LIKE '%quicksort%'")
for r in cur.fetchall():
    print(r)

print("\n--- kth in Memory ---")
cur.execute("SELECT task_id, attempt, failure_type, diagnosis, recovery_action FROM memory_records WHERE task_id LIKE '%kth%'")
for r in cur.fetchall():
    print(r)

print("\n--- reverse_linked_list in Memory ---")
cur.execute("SELECT task_id, attempt, failure_type, diagnosis, recovery_action FROM memory_records WHERE task_id LIKE '%reverse_linked_list%'")
for r in cur.fetchall():
    print(r)

print("\n--- All distinct failure types in memory ---")
cur.execute("SELECT failure_type, count(*) FROM memory_records GROUP BY failure_type")
for r in cur.fetchall():
    print(r)

print("\n--- Check trust events table ---")
cur.execute("SELECT count(*) FROM trust_events")
print("Trust events count:", cur.fetchone()[0])

conn.close()
