from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def _optional(name: str, default: str) -> str:
    value = os.environ.get(name, "").strip()
    return value or default


@dataclass(frozen=True)
class R6Player:
    key: str
    username: str
    platform: str


@dataclass(frozen=True)
class FNPlayer:
    key: str
    username: str
    account_type: str
    fallback_username: str | None = None


@dataclass(frozen=True)
class Settings:
    webhook_url: str
    fortnite_api_key: str
    ubisoft_email: str | None
    ubisoft_password: str | None
    arenyze_api_key: str | None
    r6_players: tuple[R6Player, ...]
    fn_players: tuple[FNPlayer, ...]


def load_settings() -> Settings:
    r6_players = []
    fn_players = []
    for index in (1, 2, 3):
        r6_players.append(
            R6Player(
                key=f"player_{index}_r6",
                username=_require(f"R6_PLAYER_{index}_NAME"),
                platform=_optional(f"R6_PLAYER_{index}_PLATFORM", "pc").lower(),
            )
        )
        fallback = os.environ.get(f"FN_PLAYER_{index}_NAME_FALLBACK", "").strip() or None
        fn_players.append(
            FNPlayer(
                key=f"player_{index}_fn",
                username=_require(f"FN_PLAYER_{index}_NAME"),
                account_type=_optional(f"FN_PLAYER_{index}_ACCOUNT_TYPE", "epic").lower(),
                fallback_username=fallback,
            )
        )

    arenyze = os.environ.get("ARENYZE_API_KEY", "").strip() or None
    ubisoft_email = os.environ.get("UBISOFT_EMAIL", "").strip() or None
    ubisoft_password = os.environ.get("UBISOFT_PASSWORD", "").strip() or None
    if not arenyze and not (ubisoft_email and ubisoft_password):
        raise SystemExit(
            "Set ARENYZE_API_KEY, or both UBISOFT_EMAIL and UBISOFT_PASSWORD."
        )
    return Settings(
        webhook_url=_require("DISCORD_WEBHOOK_URL"),
        fortnite_api_key=_require("FORTNITE_API_KEY"),
        ubisoft_email=ubisoft_email,
        ubisoft_password=ubisoft_password,
        arenyze_api_key=arenyze,
        r6_players=tuple(r6_players),
        fn_players=tuple(fn_players),
    )
