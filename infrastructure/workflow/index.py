"""Shared workflow index: ``<store>/index.json`` guarded by IndexLock.

The index maps ``repo_key + pilot_id`` to the workflow that owns that
lineage. It exists so that a repeated or conflicting ``init`` cannot
silently create a parallel lineage: the same key resumes the recorded
workflow, and a different ``base_sha`` under the same key requires an
explicit supersede which keeps the link to the superseded workflow.
"""
import json
import os
from pathlib import Path

from . import state as state_mod

INDEX_SCHEMA_VERSION = 1
ENTRY_STATUSES = ("creating", "active")


def index_path(store_dir):
    return Path(store_dir) / "index.json"


def index_key(repo_key, pilot_id):
    return repo_key + "\x00" + pilot_id


def new_index():
    return {"index_schema_version": INDEX_SCHEMA_VERSION, "entries": {}}


def validate_index(data):
    if not isinstance(data, dict):
        raise state_mod.WorkflowSchemaError("index must be a JSON object")
    if data.get("index_schema_version") != INDEX_SCHEMA_VERSION:
        raise state_mod.WorkflowSchemaError(
            f"unsupported index_schema_version: "
            f"{data.get('index_schema_version')!r}")
    entries = data.get("entries")
    if not isinstance(entries, dict):
        raise state_mod.WorkflowSchemaError("index.entries must be an object")
    for key, entry in entries.items():
        if "\x00" not in key:
            raise state_mod.WorkflowSchemaError(
                f"index key {key!r} is not repo\\x00pilot")
        if not isinstance(entry, dict):
            raise state_mod.WorkflowSchemaError(
                f"index entry {key!r} must be an object")
        if not state_mod.WORKFLOW_ID_RE.fullmatch(
                entry.get("workflow_id") or ""):
            raise state_mod.WorkflowSchemaError(
                f"index entry {key!r} has an invalid workflow_id")
        if entry.get("status") not in ENTRY_STATUSES:
            raise state_mod.WorkflowSchemaError(
                f"index entry {key!r} status unsupported: "
                f"{entry.get('status')!r}")
    return data


def load_index(store_dir):
    path = index_path(store_dir)
    if not path.is_file():
        return new_index()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as error:
        raise state_mod.WorkflowStateCorruptError(
            f"index file is not valid JSON: {path}") from error
    return validate_index(data)


def save_index(store_dir, index):
    """Atomic write with fsync; caller must hold IndexLock."""
    validate_index(index)
    store_dir = Path(store_dir)
    store_dir.mkdir(parents=True, exist_ok=True)
    index["updated_at"] = state_mod.utc_now()
    path = index_path(store_dir)
    temporary = path.with_suffix(".tmp")
    payload = (json.dumps(index, indent=2, ensure_ascii=False) + "\n") \
        .encode("utf-8")
    with open(temporary, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    try:
        dir_fd = os.open(store_dir, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except OSError:
        pass
    return path


def find_entry(index, repo_key, pilot_id):
    return (index.get("entries") or {}).get(index_key(repo_key, pilot_id))


def register(index, repo_key, pilot_id, workflow_id, base_sha, *,
             status="creating", supersedes=None):
    """Insert or replace the lineage record for this repo+pilot key."""
    key = index_key(repo_key, pilot_id)
    previous = (index.get("entries") or {}).get(key)
    entry = {"workflow_id": workflow_id, "base_sha": base_sha.lower(),
             "status": status, "updated_at": state_mod.utc_now()}
    superseded = list((previous or {}).get("superseded") or [])
    if supersedes and supersedes not in superseded:
        superseded.append(supersedes)
    if superseded:
        entry["superseded"] = superseded
    index.setdefault("entries", {})[key] = entry
    return entry


def mark_active(index, repo_key, pilot_id, workflow_id, latest_revision):
    entry = find_entry(index, repo_key, pilot_id)
    if entry is None or entry.get("workflow_id") != workflow_id:
        raise state_mod.WorkflowBlockedError(
            f"index entry for {pilot_id!r} does not point at {workflow_id}")
    entry["status"] = "active"
    entry["latest_revision"] = latest_revision
    entry["updated_at"] = state_mod.utc_now()
    return entry

def acquire(store_dir):
    """Hold the shared index lock for one read-modify-write cycle."""
    from .locks import IndexLock
    return IndexLock(store_dir, operation="index")
