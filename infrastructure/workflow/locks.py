"""Workflow and index locks built on the proven ExecutionLock mechanism.

``WorkflowLock`` serializes load -> decision -> action -> save inside one
workflow directory. ``IndexLock`` serializes the shared
``artifacts/workflow/index.json`` independently — a unique workflow lock
must never be used to serialize index writes. The lock order is fixed:
index -> workflow -> delegated execution, and the index lock is never held
across delegated subprocesses.
"""
from contextlib import contextmanager
import fcntl

from infrastructure.reporting.testops.lifecycle import (
    ExecutionLock, LockHeldError)


class _DirLock(ExecutionLock):
    """ExecutionLock with an overridable lock/gate file name per directory."""

    LOCK_NAME = "dir.lock"
    GATE_NAME = "dir.lock-gate"

    @contextmanager
    def _gate(self):
        self.state_dir.mkdir(parents=True, exist_ok=True)
        with (self.state_dir / self.GATE_NAME).open("a") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)


class WorkflowLock(_DirLock):
    """One writer per workflow directory."""

    LOCK_NAME = "workflow.lock"
    GATE_NAME = "workflow.lock-gate"


class IndexLock(_DirLock):
    """One writer for the shared workflow index."""

    LOCK_NAME = "index.lock"
    GATE_NAME = "index.lock-gate"


__all__ = ["IndexLock", "LockHeldError", "WorkflowLock"]
