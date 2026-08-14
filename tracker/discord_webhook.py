from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import httpx

from tracker.compare import StatChange, numeric_delta

# Brand colors — gold / purple stay primary so alerts look like a stats bot, not a spreadsheet.
R6_COLOR = 0xC4A35A
FN_COLOR = 0x9B59F5

R6_ICON = "https://cdn.cloudflare.steamstatic.com/steam/apps/359550/hero_capsule.jpg"
R6_THUMB = "https://cdn.akamai.steamstatic.com/steam/apps/359550/library_600x900.jpg"
FN_ICON = "https://cdn2.unrealengine.com/14br-consoles-1920x1080-wlogo-1920x1080-432974386.jpg"
FN_THUMB = FN_ICON

R6_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Ranked",
        (
            "ranked_rank",
            "rank_points",
            "ranked_kd",
            "ranked_wins",
            "ranked_kills",
            "ranked_deaths",
        ),
    ),
    (
        "Casual",
        (
            "casual_rank",
            "casual_mmr",
            "casual_kd",
            "casual_wins",
            "casual_kills",
            "casual_deaths",
        ),
    ),
    (
        "Overall",
        (
            "overall_kills",
            "overall_deaths",
            "overall_wins",
            "overall_kd",
            "level",
            "time_played_hours",
        ),
    ),
)

FN_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Career", ("wins", "kills", "matches", "kd")),
    ("Modes", ("solo_wins", "duo_wins", "squad_wins")),
    ("Season", ("battle_pass_level",)),
)

SHORT_LABELS = {
    "ranked_rank": "Rank",
    "rank_points": "RP",
    "ranked_kd": "K/D",
    "ranked_wins": "Wins",
    "ranked_kills": "Kills",
    "ranked_deaths": "Deaths",
    "casual_rank": "Rank",
    "casual_mmr": "MMR",
    "casual_kd": "K/D",
    "casual_wins": "Wins",
    "casual_kills": "Kills",
    "casual_deaths": "Deaths",
    "overall_kills": "Kills",
    "overall_deaths": "Deaths",
    "overall_wins": "Wins",
    "overall_kd": "K/D",
    "level": "Level",
    "time_played_hours": "Hours",
    "wins": "Victory Royales",
    "kills": "Eliminations",
    "matches": "Matches",
    "kd": "K/D",
    "solo_wins": "Solo",
    "duo_wins": "Duo",
    "squad_wins": "Squad",
    "battle_pass_level": "Battle Pass",
}

R6_HEADLINE_FIELDS = (
    "ranked_rank",
    "rank_points",
    "ranked_wins",
    "casual_rank",
    "overall_kills",
    "level",
)
FN_HEADLINE_FIELDS = (
    "wins",
    "solo_wins",
    "duo_wins",
    "squad_wins",
    "kills",
    "battle_pass_level",
)


def _format_value(value: Any) -> str:
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return f"{value:.2f}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def _format_delta(delta: float) -> str:
    if delta.is_integer():
        formatted = f"{int(delta):+,}"
    else:
        formatted = f"{delta:+.2f}"
    return formatted


def _safe_display_name(display_name: str) -> str:
    return display_name.replace("@", "").strip() or "Unknown player"


def _change_line(change: StatChange) -> str:
    label = SHORT_LABELS.get(change.field, change.label)
    arrow = f"`{_format_value(change.old)}` → `{_format_value(change.new)}`"
    delta = numeric_delta(change.old, change.new)
    if delta is None or delta == 0:
        return f"**{label}** · {arrow}"
    return f"**{label}** · {arrow}  ({_format_delta(delta)})"


def _pick_headline_change(game: str, changes: list[StatChange]) -> StatChange:
    order = R6_HEADLINE_FIELDS if game == "r6" else FN_HEADLINE_FIELDS
    by_field = {change.field: change for change in changes}
    for field in order:
        if field in by_field:
            return by_field[field]
    return changes[0]


def _headline(game: str, changes: list[StatChange]) -> str:
    change = _pick_headline_change(game, changes)
    if change.field == "ranked_rank":
        return f"Ranked · **{change.old}** → **{change.new}**"
    if change.field == "casual_rank":
        return f"Casual · **{change.old}** → **{change.new}**"
    if change.field == "wins":
        delta = numeric_delta(change.old, change.new)
        if delta == 1:
            return "**Victory Royale**"
        if delta is not None and delta > 1:
            return f"**+{int(delta)}** Victory Royales"
    if change.field in {"solo_wins", "duo_wins", "squad_wins"}:
        mode = SHORT_LABELS[change.field]
        delta = numeric_delta(change.old, change.new)
        if delta == 1:
            return f"**{mode}** Victory Royale"
        if delta is not None and delta > 1:
            return f"**{mode}** · **+{int(delta)}** wins"
    return _change_line(change)


def _grouped_fields(game: str, changes: list[StatChange]) -> list[dict[str, Any]]:
    groups = R6_GROUPS if game == "r6" else FN_GROUPS
    by_field = {change.field: change for change in changes}
    built: list[tuple[str, str]] = []
    for title, keys in groups:
        lines = [
            _change_line(by_field[key])
            for key in keys
            if key in by_field
        ]
        if lines:
            built.append((title, "\n".join(lines)))

    fields: list[dict[str, Any]] = []
    for index, (title, value) in enumerate(built):
        inline = len(built) >= 2 and not (len(built) == 3 and index == 2)
        fields.append({"name": title, "value": value, "inline": inline})
    return fields


def build_embed(
    *,
    game: str,
    display_name: str,
    changes: list[StatChange],
    preview: bool = False,
) -> dict[str, Any]:
    is_r6 = game == "r6"
    name = _safe_display_name(display_name)
    author_name = "Rainbow Six Siege" if is_r6 else "Fortnite"
    headline = _headline(game, changes) if changes else "Tracked stats updated."
    if preview:
        description = f"{headline}\nExample of how alerts look — live messages only send when a stat changes."
        footer = "Preview · no pings"
    else:
        description = headline
        footer = "Checked every 15 minutes"

    return {
        "author": {
            "name": author_name,
            "icon_url": R6_ICON if is_r6 else FN_ICON,
        },
        "title": name,
        "description": description,
        "color": R6_COLOR if is_r6 else FN_COLOR,
        "thumbnail": {"url": R6_THUMB if is_r6 else FN_THUMB},
        "fields": _grouped_fields(game, changes),
        "footer": {
            "text": footer,
            "icon_url": R6_ICON if is_r6 else FN_ICON,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _payload(embed: dict[str, Any]) -> dict[str, Any]:
    return {
        "embeds": [embed],
        "allowed_mentions": {
            "parse": [],
            "users": [],
            "roles": [],
            "replied_user": False,
        },
    }


async def send_embed(webhook_url: str, embed: dict[str, Any]) -> None:
    payload = _payload(embed)
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(webhook_url, json=payload)
        if response.status_code == 429:
            retry_after = float(response.headers.get("Retry-After", "2"))
            await asyncio.sleep(retry_after)
            response = await client.post(webhook_url, json=payload)
        if response.status_code >= 400:
            raise RuntimeError(
                f"Discord webhook failed with HTTP {response.status_code}: {response.text[:300]}"
            )
