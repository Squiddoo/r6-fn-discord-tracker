from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import fortnite_api
from siegeapi import Auth

from tracker.arenyze import fetch_r6_player_arenyze
from tracker.compare import diff_stats, is_uninitialized
from tracker.config import load_settings
from tracker.discord_webhook import build_embed, refresh_game_embeds, send_embeds
from tracker.fortnite import fetch_fn_player
from tracker.r6 import PLAYER_GAP_SECONDS, connect_with_backoff, fetch_r6_player
from tracker.schema import empty_snapshot, labels_for
from tracker.store import load_message_ids, load_snapshot, write_message_ids, write_snapshot

ROOT = Path(__file__).resolve().parent.parent
STATS_PATH = ROOT / "stats.json"
MESSAGES_PATH = ROOT / "discord_messages.json"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def _safe_failure(player_key: str, exc: BaseException) -> str:
    text = str(exc)
    if "nameOnPlatform=" in text:
        text = text.split("nameOnPlatform=")[0] + "nameOnPlatform=[redacted]"
    return f"{player_key}: {type(exc).__name__}: {text[:300]}"


async def _send_game_previews(
    webhook_url: str,
    game: str,
    player_keys: list[str],
    display_names: dict[str, str],
    snapshot: dict,
) -> int:
    embeds = []
    for player_key in player_keys:
        changes = diff_stats(
            empty_snapshot()[player_key],
            snapshot[player_key],
            labels_for(player_key),
        )
        if not changes:
            print(f"No preview fields for {player_key}; skipping that embed.")
            continue
        embeds.append(
            build_embed(
                game=game,
                display_name=display_names[player_key],
                changes=changes,
                stats=snapshot[player_key],
                preview=True,
            )
        )
    if not embeds:
        print(f"No preview embeds for {game}; skipping.")
        return 0
    await send_embeds(webhook_url, embeds)
    print(f"Sent one-time {game} preview ({len(embeds)} player embed(s)).")
    return len(embeds)


async def run(*, preview_once: bool = False, preview_only: str = "both") -> int:
    settings = load_settings()
    snapshot = load_snapshot(STATS_PATH)
    failures: list[str] = []
    r6_ok: list[str] = []
    fn_ok: list[str] = []

    display_names = {
        player.key: player.username
        for player in (*settings.r6_players, *settings.fn_players)
    }

    cache_dir = ROOT / ".cache"
    cache_dir.mkdir(exist_ok=True)
    auth: Auth | None = None
    ubi_ready = False
    try:
        if settings.ubisoft_email and settings.ubisoft_password:
            auth = Auth(
                email=settings.ubisoft_email,
                password=settings.ubisoft_password,
                creds_path=str(cache_dir / "ubi_session.json"),
                max_connect_retries=5,
            )
            try:
                delays = () if settings.arenyze_api_key else None
                await connect_with_backoff(auth, delays=delays)
                ubi_ready = True
            except Exception as exc:
                failures.append(_safe_failure("ubisoft_login", exc))
                print(f"::warning::{failures[-1]}")
                if settings.arenyze_api_key:
                    print("Falling back to Arenyze for Rainbow Six.")
                else:
                    print("No ARENYZE_API_KEY set; Rainbow Six players will keep previous stats.")
        elif settings.arenyze_api_key:
            print("No Ubisoft credentials; using Arenyze for Rainbow Six.")

        for index, player in enumerate(settings.r6_players):
            if index:
                await asyncio.sleep(PLAYER_GAP_SECONDS if ubi_ready else 1)
            fetched = False
            if ubi_ready:
                try:
                    assert auth is not None
                    stats, live_name = await fetch_r6_player(auth, player)
                    snapshot[player.key] = stats
                    display_names[player.key] = live_name
                    r6_ok.append(player.key)
                    fetched = True
                    print(f"Fetched {player.key} via ubisoft.")
                except Exception as exc:
                    print(f"::warning::{_safe_failure(player.key, exc)}")
                    if settings.arenyze_api_key:
                        print(f"Falling back to Arenyze for {player.key}.")
                    else:
                        failures.append(_safe_failure(player.key, exc))
            if fetched:
                continue
            if not settings.arenyze_api_key:
                continue
            try:
                stats, live_name = await fetch_r6_player_arenyze(
                    settings.arenyze_api_key, player
                )
                snapshot[player.key] = stats
                display_names[player.key] = live_name
                r6_ok.append(player.key)
                print(f"Fetched {player.key} via arenyze.")
            except Exception as exc:
                failures.append(_safe_failure(player.key, exc))
                print(f"::warning::{failures[-1]}")
    finally:
        if auth is not None:
            await auth.close()

    async with fortnite_api.Client(api_key=settings.fortnite_api_key) as fn_client:
        for player in settings.fn_players:
            try:
                stats, resolved_name = await fetch_fn_player(fn_client, player)
                snapshot[player.key] = stats
                display_names[player.key] = resolved_name
                fn_ok.append(player.key)
                print(f"Fetched {player.key}.")
            except Exception as exc:
                failures.append(_safe_failure(player.key, exc))
                print(f"::warning::{failures[-1]}")

    previous = load_snapshot(STATS_PATH)
    notified = 0

    if preview_once:
        send_r6 = preview_only in {"r6", "both"}
        send_fn = preview_only in {"fn", "both"}
        if send_r6 and r6_ok:
            try:
                notified += await _send_game_previews(
                    settings.webhook_url,
                    "r6",
                    r6_ok,
                    display_names,
                    snapshot,
                )
            except Exception as exc:
                failures.append(_safe_failure("discord_preview_r6", exc))
                print(f"::warning::{failures[-1]}")
            await asyncio.sleep(1)
        if send_fn and fn_ok:
            try:
                notified += await _send_game_previews(
                    settings.webhook_url,
                    "fn",
                    fn_ok,
                    display_names,
                    snapshot,
                )
            except Exception as exc:
                failures.append(_safe_failure("discord_preview_fn", exc))
                print(f"::warning::{failures[-1]}")
        print("Preview sent; saving overwrite-only baseline without 0->real spam.")
    else:
        message_ids = load_message_ids(MESSAGES_PATH)
        game_players = (
            ("r6", settings.r6_players),
            ("fn", settings.fn_players),
        )
        for game, players in game_players:
            embeds = []
            for player in players:
                old = previous[player.key]
                new = snapshot[player.key]
                if old == new:
                    continue
                if is_uninitialized(old):
                    print(f"Baseline saved for {player.key}; skipping Discord.")
                    continue
                changes = diff_stats(old, new, labels_for(player.key))
                if not changes:
                    continue
                embeds.append(
                    build_embed(
                        game=game,
                        display_name=display_names[player.key],
                        changes=changes,
                        stats=new,
                    )
                )
            if not embeds:
                continue
            try:
                old_ids = message_ids.get(game, [])
                message_ids[game] = await refresh_game_embeds(
                    settings.webhook_url,
                    old_ids,
                    embeds,
                )
                notified += len(embeds)
                print(
                    f"Refreshed {game} Discord message "
                    f"(posted {len(embeds)}, removed {len(old_ids)})."
                )
            except Exception as exc:
                failures.append(_safe_failure(f"discord_{game}", exc))
                print(f"::warning::{failures[-1]}")
        write_message_ids(MESSAGES_PATH, message_ids)

    write_snapshot(STATS_PATH, snapshot)
    print(f"Wrote current snapshot to {STATS_PATH}")
    print(f"Discord embeds sent: {notified}")

    if failures:
        print("Player fetch failures (previous values kept for those keys):")
        for line in failures:
            print(f"::warning::{line}")
        if len(failures) >= 6:
            return 1
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Overwrite-only R6/Fortnite Discord stats bot")
    parser.add_argument(
        "--preview-once",
        action="store_true",
        help=(
            "Send a one-time Discord preview of current stats for every fetched player, "
            "then save the baseline without 0->real spam."
        ),
    )
    parser.add_argument(
        "--preview-only",
        choices=("r6", "fn", "both"),
        default="both",
        help="With --preview-once, which game(s) to send.",
    )
    args = parser.parse_args()
    raise SystemExit(
        asyncio.run(run(preview_once=args.preview_once, preview_only=args.preview_only))
    )


if __name__ == "__main__":
    main()
