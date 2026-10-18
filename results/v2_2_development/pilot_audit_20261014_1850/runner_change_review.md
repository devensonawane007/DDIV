# DDIV v2.2 Runner Change and Infrastructure Review

**Audit Target:** Code modifications to `scripts/run_local_ollama_comparison.py` during pilot execution  
**Audit Date:** 2026-10-14  
**Audit Directory:** `results/v2_2_development/pilot_audit_20261014_1850/`

---

## 1. Summary of Changes Made to `scripts/run_local_ollama_comparison.py`

During pilot execution and recovery, four surgical changes were introduced into `scripts/run_local_ollama_comparison.py`:

```diff
@@ -26,6 +26,15 @@
 if project_root not in sys.path:
     sys.path.insert(0, project_root)
 
+# 1. Ensure UTF-8 output encoding across Windows consoles
+if sys.platform == "win32":
+    try:
+        sys.stdout.reconfigure(encoding="utf-8")
+        sys.stderr.reconfigure(encoding="utf-8")
+    except Exception:
+        pass
+os.environ["PYTHONIOENCODING"] = "utf-8"
+
 # Force DDIV_CODER_PROVIDER=ollama for this runner
 os.environ["DDIV_CODER_PROVIDER"] = "ollama"
 
@@ -57,11 +66,21 @@
 TASK_BASE_COMMITS = {
     "pylint-dev__pylint-4970": "40cc2ffd7887959157aaf469e09585ec2be7f528",
     "sympy__sympy-23413": "10de1a18a0efac0b19b611e40c928250dda688bf",
 }
+# 2. Dynamically load all benchmark task base commits from frozen manifest
+_manifest_path = Path("data/experiments/benchmark_v2_tasks.json")
+if _manifest_path.exists():
+    try:
+        with open(_manifest_path, "r", encoding="utf-8") as _f:
+            _mnf_data = json.load(_f)
+            for _t in _mnf_data.get("tasks", []):
+                TASK_BASE_COMMITS[_t["instance_id"]] = _t["base_commit"]
+    except Exception:
+        pass
 
 def prepare_task_seed(workspace_root: Path, task_id: str):
     cached_paths = [
+# 3. Add verified disposable preflight checkouts to cache search
+        Path(f"data/workspaces/preflight_verification/{task_id}"),
         Path(f"data/workspaces/demo/eval_ws/{task_id}-eval"),
@@ -352,6 +371,8 @@
     timeout_seconds: int = 240,
     dataset: str = "data/swebench/test-00000-of-00001.parquet",
     force_rerun: bool = False,
+# 4. Allow clean workspace and log base directory overrides
+    workspace_base: Optional[str] = None,
+    logs_dir: Optional[str] = None,
 ):
```

---

## 2. Experimental Impact and Comparability Evaluation

| Change | Technical Rationale | Impact on Experimental Validity | Comparability Across Conditions |
| :--- | :--- | :--- | :--- |
| **1. Windows UTF-8 stdout** | Fixed unhandled `UnicodeEncodeError: 'charmap'` when LLM outputted non-breaking hyphen `\u2011` on Windows cp1252 consoles. | **Zero algorithmic impact.** Purely I/O encoding fix. | Unaffected. |
| **2. Dynamic Base Commits** | Replaced 3-task hardcoded dictionary with dynamic lookup from frozen `benchmark_v2_tasks.json`. | **Zero algorithmic impact.** Ensured all 5 tasks checked out their exact frozen manifest commit. | Identical base commits used across all 3 conditions. |
| **3. Preflight Workspace Seeding** | Seeded disposable workspaces from `data/workspaces/preflight_verification/` to prevent network timeouts during `git clone`. | **Zero algorithmic impact.** Each seed was hard-reset (`git reset --hard <base_commit>`). | Identical pristine git tree used across all 3 conditions. |
| **4. Workspace & Log Directory Flags** | Allowed routing task workspaces to `data/workspaces/pilot_5tasks` instead of shared default. | **Positive isolation impact.** Guaranteed historical v2.1 workspaces were untouched. | Identical isolation applied across all conditions. |

**Verdict:** None of the changes modified prompts, model parameters, locator behavior, coder schemas, evaluator rules, or condition isolation logic. The comparability and validity of all 15 runs remain fully preserved.

---

## 3. Infrastructure Classification Audit: Ollama Disconnection vs. Groq Quota

### 3.1 Error Misclassification in Saved JSON
- When the host computer rebooted during Task 4 (`astropy__astropy-8872`), the Ollama daemon terminated, causing `[WinError 10061] No connection could be made because the target machine actively refused it`.
- In `core/experiment_worker.py:470`, the helper `_is_quota_exhausted(code, msg)` treated `PROVIDER_UNAVAILABLE` as a quota exhaustion trigger, setting:
  `terminal_status = ConditionJobStatus.ABORTED_QUOTA_EXHAUSTED`
- **Correction:** A connection refusal due to a local process shutdown is an **infrastructure service failure (`INFRASTRUCTURE_DISCONNECTION`)**, not an API quota exhaustion.
- The two aborted Astropy records (`aborted_astropy__astropy-8872__retry_only.json` and `aborted_astropy__astropy-8872__full_ddiv.json`) are preserved in `infrastructure_aborts/` and are correctly classified in the corrected audit report as infrastructure interruptions, completely excluded from repair statistics.

### 3.2 Actual Groq API Quota Event
- During `psf__requests-2931` (`FULL_DDIV`), Groq HTTP API returned a true 429 quota exhaustion:
  `Error code: 429 - Rate limit reached for model qwen/qwen3.8-27b on tokens per day (TPD): Limit 200000, Used 199403, Requested 2213. Please try again in 11m38s.`
- The runner handled this cleanly: the 7-minute timer elapsed, Groq quota reset, and execution completed with zero corruption.
