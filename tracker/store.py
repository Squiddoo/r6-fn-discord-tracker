"""Overwrite-only stats.json. Current snapshot for 6 anonymous keys. No history."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from tracker.schema import PLAYER_KEYS, empty_snapshot, schema_for


def load_snapshot(path: Path) -> dict[str, dict[str, Any]]:
    snapshot = empty_snapshot()
    if not path.exists():
        return snapshot

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return snapshot

    if not isinstance(raw, dict):
        return snapshot

    for key in PLAYER_KEYS:
        incoming = raw.get(key)
        if not isinstance(incoming, dict):
            continue
        fields = schema_for(key)
        for field in fields:
            if field in incoming:
                fields[field] = incoming[field]
        snapshot[key] = fields
    return snapshot


def write_snapshot(path: Path, snapshot: dict[str, dict[str, Any]]) -> None:
    """Replace the entire file with the current 6-player snapshot. Never append."""
    clean = empty_snapshot()
    for key in PLAYER_KEYS:
        incoming = snapshot.get(key, {})
        for field in clean[key]:
            if field in incoming:
                clean[key][field] = incoming[field]

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix="stats.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(clean, handle, indent=2, ensure_ascii=True)
            handle.write("\n")
        os.replace(tmp_name, path)
    except Exception:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)
        raise
