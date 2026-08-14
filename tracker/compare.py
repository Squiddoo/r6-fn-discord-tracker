from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StatChange:
    field: str
    label: str
    old: Any
    new: Any


def is_uninitialized(stats: dict[str, Any]) -> bool:
    for value in stats.values():
        if isinstance(value, str):
            if value.strip().lower() not in {"", "unranked", "-"}:
                return False
        elif isinstance(value, (int, float)) and value != 0:
            return False
    return True


def diff_stats(
    old: dict[str, Any],
    new: dict[str, Any],
    labels: dict[str, str],
) -> list[StatChange]:
    changes: list[StatChange] = []
    for field, label in labels.items():
        previous = old.get(field)
        current = new.get(field)
        if previous != current:
            changes.append(StatChange(field=field, label=label, old=previous, new=current))
    return changes


def numeric_delta(old: Any, new: Any) -> float | None:
    if isinstance(old, bool) or isinstance(new, bool):
        return None
    if isinstance(old, (int, float)) and isinstance(new, (int, float)):
        return float(new) - float(old)
    return None
