"""One-command verification script for the DDIV pylint-6903 demo."""
import os
import subprocess
import sys
from pathlib import Path

repo_root = Path(__file__).parent.parent.resolve()
workspace = repo_root / "data" / "workspaces" / "demo" / "eval_ws" / "pylint-dev__pylint-6903-eval"
test_target = "tests/test_pylint_runners.py"

print("======================================================================")
print(" RUNNING TIER 1 SWE-BENCH VERIFICATION ON DEMO WORKSPACE")
print(f" Workspace: {workspace}")
print(f" Target:    {test_target}")
print("======================================================================")

env = os.environ.copy()
env["PYTHONPATH"] = str(workspace)

res = subprocess.run(
    [sys.executable, "-m", "pytest", "-v", test_target],
    cwd=workspace,
    env=env,
)
sys.exit(res.returncode)
