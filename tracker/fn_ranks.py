"""Current-season Fortnite ranked labels for Battle Royale and Reload."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

UNRANKED = "Unranked"
_HEADERS = {
    "Accept": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Referer": "https://fortnite.gg/",
}


def _format_rank(payload: dict[str, Any]) -> str:
    if payload.get("error"):
        return UNRANKED
    stats = payload.get("stats")
    if not isinstance(stats, dict):
        return UNRANKED
    text = str(stats.get("rank_text") or "").strip()
    if not text:
        return UNRANKED
    percent = stats.get("rank_percent")
    try:
        pct = int(percent)
    except (TypeError, ValueError):
        return text
    return f"{text} ({pct}%)"


async def _fetch_mode(client: httpx.AsyncClient, path: str, name: str) -> str:
    encoded = quote(name, safe="")
    url = f"https://fortnite.gg/{path}?player={encoded}&ajax"
    response = await client.get(url, headers=_HEADERS)
    if response.status_code >= 400:
        raise RuntimeError(f"fortnite.gg {path} HTTP {response.status_code}")
    content_type = response.headers.get("content-type", "")
    if "json" not in content_type and not response.text.lstrip().startswith("{"):
        raise RuntimeError(f"fortnite.gg {path} returned a challenge page")
    return _format_rank(response.json())


async def fetch_season_ranks(display_name: str) -> dict[str, str]:
    """Return current-season BR and Reload ranks. Unranked if they have not played."""
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        br_rank = await _fetch_mode(client, "ranked-stats", display_name)
        reload_rank = await _fetch_mode(client, "ranked-reload-stats", display_name)
    return {"br_rank": br_rank, "reload_rank": reload_rank}
