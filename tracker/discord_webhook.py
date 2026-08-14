from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import httpx

from tracker.compare import StatChange, numeric_delta

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
    ("Ranked", ("br_rank", "reload_rank")),
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
    "wins": "Wins",
    "kills": "Elims",
    "matches": "Matches",
    "kd": "K/D",
    "solo_wins": "Solo",
    "duo_wins": "Duo",
    "squad_wins": "Squad",
    "battle_pass_level": "Battle Pass",
    "br_rank": "BR",
    "reload_rank": "Reload",
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
    "br_rank",
    "reload_rank",
    "wins",
    "solo_wins",
    "duo_wins",
    "squad_wins",
    "kills",
    "battle_pass_level",
)

RANK_FIELDS = {"ranked_rank", "casual_rank", "br_rank", "reload_rank"}
SUMMARY_SKIP = RANK_FIELDS
BLANK = "\u200b"


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
        return f"{int(delta):+,}"
    return f"{delta:+.2f}"


def _safe_display_name(display_name: str) -> str:
    return display_name.replace("@", "").strip() or "Unknown player"


def _delta_of(change: StatChange | None) -> float | None:
    if change is None:
        return None
    return numeric_delta(change.old, change.new)


def _pick_headline_change(game: str, changes: list[StatChange]) -> StatChange:
    order = R6_HEADLINE_FIELDS if game == "r6" else FN_HEADLINE_FIELDS
    by_field = {change.field: change for change in changes}
    for field in order:
        if field in by_field:
            return by_field[field]
    return changes[0]


def _headline(game: str, changes: list[StatChange]) -> str:
    by_field = {change.field: change for change in changes}
    change = _pick_headline_change(game, changes)

    if change.field == "ranked_rank":
        rp_delta = _delta_of(by_field.get("rank_points"))
        if rp_delta is not None and rp_delta > 0:
            return f"**Promoted** to {change.new}"
        if rp_delta is not None and rp_delta < 0:
            return f"**Demoted** to {change.new}"
        return f"**{change.old}** → **{change.new}**"

    if change.field == "casual_rank":
        return f"Casual · **{change.old}** → **{change.new}**"

    if change.field == "rank_points":
        delta = _delta_of(change)
        if delta is not None:
            return f"**{_format_delta(delta)} RP** this check"

    if change.field == "ranked_wins":
        delta = _delta_of(change)
        if delta == 1:
            return "**Ranked win**"
        if delta is not None and delta > 1:
            return f"**+{int(delta)}** ranked wins"

    if change.field == "br_rank":
        return f"BR · **{change.old}** → **{change.new}**"

    if change.field == "reload_rank":
        return f"Reload · **{change.old}** → **{change.new}**"

    if change.field == "wins":
        delta = _delta_of(change)
        mode = next(
            (
                SHORT_LABELS[field]
                for field in ("solo_wins", "duo_wins", "squad_wins")
                if field in by_field
            ),
            None,
        )
        if delta == 1:
            return f"**Victory Royale**" + (f" · {mode}" if mode else "")
        if delta is not None and delta > 1:
            return f"**+{int(delta)}** Victory Royales"

    if change.field in {"solo_wins", "duo_wins", "squad_wins"}:
        mode = SHORT_LABELS[change.field]
        delta = _delta_of(change)
        if delta == 1:
            return f"**Victory Royale** · {mode}"
        if delta is not None and delta > 1:
            return f"**{mode}** · **+{int(delta)}** wins"

    if change.field == "battle_pass_level":
        return f"Battle Pass · **{_format_value(change.new)}**"

    delta = _delta_of(change)
    label = SHORT_LABELS.get(change.field, change.label)
    if delta is None:
        return f"**{label}**  {_format_value(change.old)} → **{_format_value(change.new)}**"
    return f"**{label}**  {_format_value(change.new)}  `{_format_delta(delta)}`"


def _summary_line(changes: list[StatChange]) -> str | None:
    bits: list[str] = []
    for change in changes:
        if change.field in SUMMARY_SKIP:
            continue
        delta = numeric_delta(change.old, change.new)
        if delta is None or delta == 0:
            continue
        label = SHORT_LABELS.get(change.field, change.label)
        bits.append(f"`{_format_delta(delta)}` {label}")
        if len(bits) == 6:
            break
    if not bits:
        return None
    return " · ".join(bits)


def _stat_value(change: StatChange) -> str:
    new = _format_value(change.new)
    old = _format_value(change.old)
    delta = numeric_delta(change.old, change.new)
    if change.field in RANK_FIELDS or delta is None:
        if change.old == change.new:
            return f"**{new}**"
        return f"**{new}**\n{old}"
    return f"**{new}**\n{old} → `{_format_delta(delta)}`"


def _pad_inline(count: int) -> list[dict[str, Any]]:
    remainder = count % 3
    if remainder == 0:
        return []
    return [{"name": BLANK, "value": BLANK, "inline": True}] * (3 - remainder)


def _scoreboard_fields(game: str, changes: list[StatChange]) -> list[dict[str, Any]]:
    groups = R6_GROUPS if game == "r6" else FN_GROUPS
    by_field = {change.field: change for change in changes}
    active = [(title, [by_field[key] for key in keys if key in by_field]) for title, keys in groups]
    active = [(title, stats) for title, stats in active if stats]
    show_headers = len(active) > 1 or (active and len(active[0][1]) > 3)

    fields: list[dict[str, Any]] = []
    for title, stats in active:
        if show_headers:
            fields.append({"name": title, "value": BLANK, "inline": False})
        for change in stats:
            fields.append(
                {
                    "name": SHORT_LABELS.get(change.field, change.label),
                    "value": _stat_value(change),
                    "inline": True,
                }
            )
        fields.extend(_pad_inline(len(stats)))
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
    summary = _summary_line(changes) if changes else None
    description = f"{headline}\n{summary}" if summary else headline
    footer = "Preview" if preview else "Stats tracker"

    return {
        "author": {
            "name": author_name,
            "icon_url": R6_ICON if is_r6 else FN_ICON,
        },
        "title": name,
        "description": description,
        "color": R6_COLOR if is_r6 else FN_COLOR,
        "thumbnail": {"url": R6_THUMB if is_r6 else FN_THUMB},
        "fields": _scoreboard_fields(game, changes),
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
