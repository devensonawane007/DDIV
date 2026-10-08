import sys
from pathlib import Path

# Add project root to sys.path for direct CLI invocation
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from evaluation.swebench_loader import SWEBenchLoader

loader = SWEBenchLoader()
records = loader.load_from_file("data/swebench/test-00000-of-00001.parquet")
rec = records[0]
print("Instance ID:", rec.task.instance_id)
print("Repo:", rec.task.repo)
print("Base commit:", rec.task.base_commit)
print("Version:", rec.task.version)
print("Environment setup commit:", rec.task.environment_setup_commit)
print("Problem statement preview:", rec.task.problem_statement[:200])
