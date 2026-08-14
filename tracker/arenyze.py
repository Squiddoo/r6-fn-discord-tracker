"""Arenyze R6 fallback client. Credentials stay in env; names stay in memory."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
from siegeapi.rank_profile import FullProfile

from tracker.config import R6Player
from tracker.r6 import _PLATFORM_MAP, _kd
from tracker.schema import R6_FIELDS

ARENYZE_BASE = "https://public-api.arenyze.com/r6/api"
ARENYZE_FULLSTATS = f"{ARENYZE_BASE}/v2/fullstats"
ARENYZE_PROFILE = f"{ARENYZE_BASE}/v2/profile"
RETRY_STATUSES = {429, 502, 503, 504}
RETRY_DELAYS = (0, 2, 6)


def _stat_value(stats: dict[str, Any] | None, key: str) -> int:
    if not stats:
        return 0
    raw = stats.get(key)
    if isinstance(raw, dict):
        return int(raw.get("value") or 0)
    if isinstance(raw, (int, float)):
        return int(raw)
    return 0


def _latest_board(tree: list[Any] | None, board_id: str) -> dict[str, Any] | None:
    if not tree:
        return None
    found: list[dict[str, Any]] = []
    for family in tree:
        if not isinstance(family, dict):
            continue
        for board in family.get("board_ids_full_profiles") or []:
            if not isinstance(board, dict):
                continue
            if str(board.get("board_id") or "").lower() != board_id:
                continue
            for entry in board.get("full_profiles") or []:
                if isinstance(entry, dict):
                    found.append(entry)
    if not found:
        return None
    return max(found, key=lambda item: int(item.get("season_id") or 0))


def _board_stats(entry: dict[str, Any] | None) -> dict[str, Any]:
    empty = {
        "kills": 0,
        "deaths": 0,
        "wins": 0,
        "kd": 0.0,
        "rank": "Unranked",
        "points": 0,
    }
    if not entry:
        return empty
    payload = dict(entry)
    profile = dict(payload.get("profile") or {})
    if "season_id" not in profile:
        profile["season_id"] = payload.get("season_id") or 0
    payload["profile"] = profile
    parsed = FullProfile(payload)
    kills = int(parsed.kills or 0)
    deaths = int(parsed.deaths or 0)
    rank = (parsed.rank or "").strip() or "Unranked"
    return {
        "kills": kills,
        "deaths": deaths,
        "wins": int(parsed.wins or 0),
        "kd": _kd(kills, deaths),
        "rank": rank,
        "points": int(parsed.rank_points or 0),
    }


def _overall_from_operators(operators: list[Any] | None) -> tuple[int, int, int]:
    kills = deaths = wins = 0
    for operator in operators or []:
        if not isinstance(operator, dict):
            continue
        kills += int(operator.get("kills") or 0)
        deaths += int(operator.get("deaths") or 0)
        wins += int(operator.get("matchesWon") or operator.get("wins") or 0)
    return kills, deaths, wins


def _overall_from_segments(segments: list[Any] | None) -> tuple[int, int, int] | None:
    if not segments:
        return None
    seasons = [
        int((seg.get("attributes") or {}).get("season") or 0)
        for seg in segments
        if isinstance(seg, dict)
    ]
    if not seasons:
        return None
    latest = max(seasons)
    seen_modes: set[str] = set()
    kills = deaths = wins = 0
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        attrs = seg.get("attributes") or {}
        if int(attrs.get("season") or 0) != latest:
            continue
        mode = str(attrs.get("sessionType") or attrs.get("gamemode") or "")
        if mode in seen_modes:
            continue
        seen_modes.add(mode)
        stats = seg.get("stats") or {}
        kills += _stat_value(stats, "kills")
        deaths += _stat_value(stats, "deaths")
        wins += _stat_value(stats, "matchesWon")
    if kills == 0 and deaths == 0 and wins == 0:
        return None
    return kills, deaths, wins


def _normalize_payload(data: dict[str, Any]) -> dict[str, Any]:
    if isinstance(data.get("fullStats"), dict):
        return data
    seasons = (data.get("seasons") or {}).get("data") or {}
    return {
        "player": data.get("player") or {},
        "fullStats": {
            "platform_families_full_profiles": (data.get("stats") or {}).get(
                "platform_families_full_profiles"
            ),
            "operators": [],
            "data": seasons,
            "totalsHoursPlayed": {"hours": 0},
        },
        "account": data.get("account") or {},
    }


def _parse_fullstats(data: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_payload(data)
    full = normalized.get("fullStats") if isinstance(normalized.get("fullStats"), dict) else normalized
    boards = full.get("platform_families_full_profiles")
    ranked = _board_stats(_latest_board(boards, "ranked"))
    casual = _board_stats(_latest_board(boards, "casual"))
    overall = _overall_from_segments((full.get("data") or {}).get("segments"))
    if overall is None:
        overall = _overall_from_operators(full.get("operators"))
    overall_kills, overall_deaths, overall_wins = overall
    hours = int(((full.get("totalsHoursPlayed") or {}).get("hours")) or 0)
    level = int(((full.get("data") or {}).get("metadata") or {}).get("clearanceLevel") or 0)
    if not level:
        level = int((normalized.get("account") or {}).get("level") or 0)

    parsed = dict(R6_FIELDS)
    parsed.update(
        {
            "ranked_kills": ranked["kills"],
            "ranked_deaths": ranked["deaths"],
            "ranked_wins": ranked["wins"],
            "ranked_kd": ranked["kd"],
            "rank_points": ranked["points"],
            "ranked_rank": ranked["rank"],
            "casual_kills": casual["kills"],
            "casual_deaths": casual["deaths"],
            "casual_wins": casual["wins"],
            "casual_kd": casual["kd"],
            "casual_mmr": casual["points"],
            "casual_rank": casual["rank"],
            "overall_kills": overall_kills,
            "overall_deaths": overall_deaths,
            "overall_wins": overall_wins,
            "overall_kd": _kd(overall_kills, overall_deaths),
            "level": level,
            "time_played_hours": hours,
        }
    )
    return parsed


async def _get_with_retry(
    client: httpx.AsyncClient, url: str, params: dict[str, str]
) -> httpx.Response:
    response: httpx.Response | None = None
    for delay in RETRY_DELAYS:
        if delay:
            await asyncio.sleep(delay)
        response = await client.get(url, params=params)
        if response.status_code not in RETRY_STATUSES:
            return response
    assert response is not None
    return response


async def fetch_r6_player_arenyze(api_key: str, player: R6Player) -> tuple[dict[str, Any], str]:
    preferred = _PLATFORM_MAP.get(player.platform, "uplay")
    platforms = [preferred, *[item for item in ("uplay", "psn", "xbl") if item != preferred]]
    headers = {"api-key": api_key, "Accept": "application/json"}
    last_status = 0
    async with httpx.AsyncClient(timeout=45.0, headers=headers) as client:
        for platform in platforms:
            lookup = {
                "nameOnPlatform": player.username,
                "platformType": platform,
            }
            response = await _get_with_retry(
                client, ARENYZE_FULLSTATS, {**lookup, "modes": "all"}
            )
            if response.status_code >= 400:
                response = await _get_with_retry(client, ARENYZE_PROFILE, lookup)
            last_status = response.status_code
            if response.status_code == 404:
                continue
            if response.status_code == 429:
                raise RuntimeError(f"Arenyze rate-limited {player.key}")
            if response.status_code >= 400:
                raise RuntimeError(
                    f"Arenyze {player.key} failed with HTTP {response.status_code}"
                )
            payload = response.json()
            if not isinstance(payload, dict):
                raise RuntimeError(f"Arenyze {player.key} returned a non-object payload")
            live_name = str(
                (payload.get("player") or {}).get("nameOnPlatform") or player.username
            ).strip()
            return _parse_fullstats(payload), live_name
    raise RuntimeError(f"Arenyze {player.key} failed with HTTP {last_status}")
