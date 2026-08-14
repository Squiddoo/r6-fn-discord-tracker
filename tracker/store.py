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


def _atomic_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=True)
            handle.write("\n")
        os.replace(tmp_name, path)
    except Exception:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)
        raise


def _clean_message_ids(raw: Any) -> list[str]:
    if isinstance(raw, int) and raw > 0:
        return [str(raw)]
    if isinstance(raw, str) and raw.isdigit():
        return [raw]
    if not isinstance(raw, list):
        return []
    cleaned: list[str] = []
    for item in raw:
        if isinstance(item, int) and item > 0:
            cleaned.append(str(item))
        elif isinstance(item, str) and item.isdigit():
            cleaned.append(item)
    return cleaned


def load_message_ids(path: Path) -> dict[str, list[str]]:
    ids = {"r6": [], "fn": []}
    if not path.exists():
        return ids
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ids
    if not isinstance(raw, dict):
        return ids
    ids["r6"] = _clean_message_ids(raw.get("r6"))
    ids["fn"] = _clean_message_ids(raw.get("fn"))
    return ids


def write_message_ids(path: Path, message_ids: dict[str, list[str]]) -> None:
    _atomic_write(
        path,
        {
            "r6": _clean_message_ids(message_ids.get("r6")),
            "fn": _clean_message_ids(message_ids.get("fn")),
        },
    )
