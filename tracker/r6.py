from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, TypeVar

from siegeapi import Auth
from siegeapi.exceptions import FailedToConnect, InvalidRequest
from siegeapi.rank_profile import FullProfile

from tracker.config import R6Player
from tracker.schema import R6_FIELDS

_PLATFORM_MAP = {
    "pc": "uplay",
    "uplay": "uplay",
    "ubi": "uplay",
    "psn": "psn",
    "ps": "psn",
    "ps4": "psn",
    "ps5": "psn",
    "playstation": "psn",
    "xbl": "xbl",
    "xbox": "xbl",
    "xboxone": "xbl",
}

# Minutes-scale backoff: Ubisoft 429s often need a long cool-down.
LOGIN_BACKOFF_SECONDS = (45, 90, 180, 300)
REQUEST_BACKOFF_SECONDS = (20, 45, 90, 180)
PLAYER_GAP_SECONDS = 8

T = TypeVar("T")


def _kd(kills: int, deaths: int) -> float:
    if deaths <= 0:
        return round(float(kills), 2) if kills else 0.0
    return round(kills / deaths, 2)


def _is_rate_limited(exc: BaseException) -> bool:
    if getattr(exc, "code", None) == 429:
        return True
    message = str(exc).lower()
    return (
        "429" in message
        or "too many" in message
        or "login on cooldown" in message
        or "rate limit" in message
    )


def _session_closed(auth: Auth) -> bool:
    session = getattr(auth, "session", None)
    return session is None or bool(getattr(session, "closed", False))


async def _ensure_session(auth: Auth) -> None:
    if _session_closed(auth):
        await auth.refresh_session()


async def connect_with_backoff(
    auth: Auth,
    delays: tuple[int, ...] | None = None,
) -> None:
    """Log in to Ubisoft. Long delays are skipped when an Arenyze fallback is configured."""
    wait_for = LOGIN_BACKOFF_SECONDS if delays is None else delays
    last_error: BaseException | None = None
    attempts = len(wait_for) + 1
    for attempt in range(attempts):
        try:
            await _ensure_session(auth)
            await auth.connect()
            print("Ubisoft login succeeded.")
            return
        except FailedToConnect as exc:
            last_error = exc
            if not _is_rate_limited(exc):
                raise
            if attempt >= len(wait_for):
                break
            delay = wait_for[attempt]
            print(
                f"Ubisoft rate-limited login; waiting {delay}s "
                f"(attempt {attempt + 1}/{attempts})."
            )
            await asyncio.sleep(delay)
    raise RuntimeError(f"Ubisoft login still rate-limited after backoff: {last_error}")


async def _call_with_backoff(
    action: Callable[[], Awaitable[T]],
    *,
    context: str,
    delays: tuple[int, ...] = REQUEST_BACKOFF_SECONDS,
) -> T:
    last_error: BaseException | None = None
    attempts = len(delays) + 1
    for attempt in range(attempts):
        try:
            return await action()
        except (FailedToConnect, InvalidRequest) as exc:
            last_error = exc
            if not _is_rate_limited(exc):
                raise
            if attempt >= len(delays):
                break
            delay = delays[attempt]
            print(
                f"Ubisoft rate-limited {context}; waiting {delay}s "
                f"(attempt {attempt + 1}/{attempts})."
            )
            await asyncio.sleep(delay)
    raise RuntimeError(f"Ubisoft rate-limited {context}: {last_error}")


def _profile_stats(profile: FullProfile | None) -> dict[str, Any]:
    if profile is None:
        return {
            "kills": 0,
            "deaths": 0,
            "wins": 0,
            "kd": 0.0,
            "rank": "Unranked",
            "points": 0,
        }
    kills = int(profile.kills or 0)
    deaths = int(profile.deaths or 0)
    rank = (profile.rank or "").strip() or "Unranked"
    return {
        "kills": kills,
        "deaths": deaths,
        "wins": int(profile.wins or 0),
        "kd": _kd(kills, deaths),
        "rank": rank,
        "points": int(profile.rank_points or 0),
    }


def _latest_all_role(summary_map: dict[Any, Any] | None) -> Any | None:
    if not summary_map:
        return None

    def season_key(item: Any) -> int:
        try:
            return int(item)
        except (TypeError, ValueError):
            return 0

    season = summary_map[max(summary_map.keys(), key=season_key)]
    if isinstance(season, dict):
        return season.get("all") or next(iter(season.values()), None)
    return season


async def fetch_r6_player(auth: Auth, player: R6Player) -> tuple[dict[str, Any], str]:
    platform = _PLATFORM_MAP.get(player.platform, "uplay")

    async def lookup():
        await _ensure_session(auth)
        return await auth.get_player(name=player.username, platform=platform)

    ubi_player = await _call_with_backoff(lookup, context=f"lookup {player.key}")
    await _call_with_backoff(ubi_player.load_ranked_v2, context=f"ranked {player.key}")
    await _call_with_backoff(ubi_player.load_playtime, context=f"playtime {player.key}")
    try:
        await _call_with_backoff(ubi_player.load_progress, context=f"progress {player.key}")
    except Exception:
        pass
    try:
        await _call_with_backoff(
            lambda: ubi_player.load_summaries(
                gamemodes=["all", "ranked", "casual"],
                team_roles=["all"],
            ),
            context=f"summaries {player.key}",
        )
    except Exception:
        pass

    ranked = _profile_stats(ubi_player.ranked_profile)
    casual = _profile_stats(ubi_player.casual_profile)
    overall = _latest_all_role(getattr(ubi_player, "all_summary", None))

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
            "level": int(ubi_player.level or 0),
            "time_played_hours": int(getattr(ubi_player, "total_time_played_hours", 0) or 0),
        }
    )
    if overall is not None:
        kills = int(getattr(overall, "kills", 0) or 0)
        deaths = int(getattr(overall, "death", 0) or 0)
        parsed["overall_kills"] = kills
        parsed["overall_deaths"] = deaths
        parsed["overall_wins"] = int(getattr(overall, "matches_won", 0) or 0)
        parsed["overall_kd"] = _kd(kills, deaths)
    live_name = (getattr(ubi_player, "name", None) or player.username).strip()
    return parsed, live_name
