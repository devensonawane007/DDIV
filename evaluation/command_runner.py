"""Controlled subprocess execution with timeout and output capture."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel


class CommandResult(BaseModel):
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False

    @property
    def is_success(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


class CommandRunner:
    """Safely executes controlled commands within isolated workspaces."""

    def __init__(self, default_timeout: int = 60):
        self.default_timeout = default_timeout

    def run(
        self,
        cmd: List[str] | str,
        cwd: str | Path,
        timeout: Optional[int] = None,
        env: Optional[dict] = None,
    ) -> CommandResult:
        timeout = timeout or self.default_timeout
        start_time = time.time()
        cmd_str = cmd if isinstance(cmd, str) else " ".join(cmd)

        try:
            process = subprocess.run(
                cmd,
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout,
                shell=isinstance(cmd, str),
                env=env,
            )
            duration = time.time() - start_time
            return CommandResult(
                command=cmd_str,
                exit_code=process.returncode,
                stdout=process.stdout,
                stderr=process.stderr,
                duration_seconds=duration,
                timed_out=False,
            )
        except subprocess.TimeoutExpired as te:
            duration = time.time() - start_time
            stdout = te.stdout if isinstance(te.stdout, str) else (te.stdout.decode() if te.stdout else "")
            stderr = te.stderr if isinstance(te.stderr, str) else (te.stderr.decode() if te.stderr else "")
            return CommandResult(
                command=cmd_str,
                exit_code=-1,
                stdout=stdout,
                stderr=stderr + f"\n[ERROR] Command timed out after {timeout} seconds.",
                duration_seconds=duration,
                timed_out=True,
            )
        except Exception as e:
            duration = time.time() - start_time
            return CommandResult(
                command=cmd_str,
                exit_code=-1,
                stdout="",
                stderr=f"[ERROR] Subprocess execution error: {str(e)}",
                duration_seconds=duration,
                timed_out=False,
            )
