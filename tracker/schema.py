"""Anonymous current-state snapshot. Never stores names or history."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

R6_FIELDS: dict[str, int | float | str] = {
    "ranked_kills": 0,
    "ranked_deaths": 0,
    "ranked_wins": 0,
    "ranked_kd": 0.0,
    "rank_points": 0,
    "ranked_rank": "Unranked",
    "casual_kills": 0,
    "casual_deaths": 0,
    "casual_wins": 0,
    "casual_kd": 0.0,
    "casual_mmr": 0,
    "casual_rank": "Unranked",
    "overall_kills": 0,
    "overall_deaths": 0,
    "overall_wins": 0,
    "overall_kd": 0.0,
    "level": 0,
    "time_played_hours": 0,
}

FN_FIELDS: dict[str, int | float] = {
    "wins": 0,
    "kills": 0,
    "matches": 0,
    "kd": 0.0,
    "solo_wins": 0,
    "duo_wins": 0,
    "squad_wins": 0,
    "battle_pass_level": 0,
}

R6_KEYS = ("player_1_r6", "player_2_r6", "player_3_r6")
FN_KEYS = ("player_1_fn", "player_2_fn", "player_3_fn")
PLAYER_KEYS = (*R6_KEYS, *FN_KEYS)

R6_LABELS = {
    "ranked_rank": "Ranked Rank",
    "rank_points": "Rank Points",
    "ranked_kills": "Ranked Kills",
    "ranked_deaths": "Ranked Deaths",
    "ranked_wins": "Ranked Wins",
    "ranked_kd": "Ranked K/D",
    "casual_rank": "Casual Rank",
    "casual_mmr": "Casual MMR",
    "casual_kills": "Casual Kills",
    "casual_deaths": "Casual Deaths",
    "casual_wins": "Casual Wins",
    "casual_kd": "Casual K/D",
    "overall_kills": "Overall Kills",
    "overall_deaths": "Overall Deaths",
    "overall_wins": "Overall Wins",
    "overall_kd": "Overall K/D",
    "level": "Level",
    "time_played_hours": "Time Played (hours)",
}

FN_LABELS = {
    "wins": "Victory Royales",
    "kills": "Eliminations",
    "matches": "Matches Played",
    "kd": "K/D",
    "solo_wins": "Solo Wins",
    "duo_wins": "Duo Wins",
    "squad_wins": "Squad Wins",
    "battle_pass_level": "Battle Pass Level",
}


def empty_snapshot() -> dict[str, dict[str, Any]]:
    snapshot: dict[str, dict[str, Any]] = {}
    for key in R6_KEYS:
        snapshot[key] = deepcopy(R6_FIELDS)
    for key in FN_KEYS:
        snapshot[key] = deepcopy(FN_FIELDS)
    return snapshot


def schema_for(player_key: str) -> dict[str, Any]:
    return deepcopy(R6_FIELDS if player_key.endswith("_r6") else FN_FIELDS)


def labels_for(player_key: str) -> dict[str, str]:
    return R6_LABELS if player_key.endswith("_r6") else FN_LABELS
