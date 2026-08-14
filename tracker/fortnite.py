from __future__ import annotations

from typing import Any

import fortnite_api

from tracker.config import FNPlayer
from tracker.schema import FN_FIELDS

_ACCOUNT_TYPES = {
    "epic": fortnite_api.AccountType.EPIC,
    "pc": fortnite_api.AccountType.EPIC,
    "psn": fortnite_api.AccountType.PSN,
    "ps": fortnite_api.AccountType.PSN,
    "ps4": fortnite_api.AccountType.PSN,
    "ps5": fortnite_api.AccountType.PSN,
    "playstation": fortnite_api.AccountType.PSN,
    "xbl": fortnite_api.AccountType.XBL,
    "xbox": fortnite_api.AccountType.XBL,
}


def _mode_wins(mode: fortnite_api.BrGameModeStats | None) -> int:
    return int(mode.wins) if mode is not None else 0


def _parse_stats(stats: fortnite_api.BrPlayerStats) -> dict[str, Any]:
    overall = None
    solo = None
    duo = None
    squad = None
    if stats.inputs and stats.inputs.all:
        overall = stats.inputs.all.overall
        solo = stats.inputs.all.solo
        duo = stats.inputs.all.duo
        squad = stats.inputs.all.squad

    parsed = dict(FN_FIELDS)
    if overall is not None:
        parsed.update(
            {
                "wins": int(overall.wins),
                "kills": int(overall.kills),
                "matches": int(overall.matches),
                "kd": round(float(overall.kd), 2),
            }
        )
    parsed["solo_wins"] = _mode_wins(solo)
    parsed["duo_wins"] = _mode_wins(duo)
    parsed["squad_wins"] = _mode_wins(squad)
    if stats.battle_pass is not None:
        parsed["battle_pass_level"] = int(stats.battle_pass.level)
    return parsed


async def fetch_fn_player(
    client: fortnite_api.Client, player: FNPlayer
) -> tuple[dict[str, Any], str]:
    account_type = _ACCOUNT_TYPES.get(player.account_type)
    if account_type is None:
        raise RuntimeError(
            f"Unsupported Fortnite account type for {player.key}: {player.account_type}"
        )

    names = [player.username]
    if player.fallback_username and player.fallback_username not in names:
        names.append(player.fallback_username)

    last_error: Exception | None = None
    for name in names:
        try:
            stats = await client.fetch_br_stats(
                name=name,
                type=account_type,
                time_window=fortnite_api.TimeWindow.LIFETIME,
            )
            return _parse_stats(stats), name
        except (fortnite_api.NotFound, fortnite_api.Forbidden) as exc:
            last_error = exc
            continue

    raise RuntimeError(
        f"Could not fetch Fortnite stats for {player.key} "
        f"after trying {len(names)} name(s): {last_error}"
    )
