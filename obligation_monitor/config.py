"""Тохиргоо — .env файл болон орчны хувьсагчаас уншина."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent

# Google Chat webhook URL-ийг таних загвар (.env-д түлхүүргүй, нүцгэн байсан ч олно)
_WEBHOOK_RE = re.compile(r"https://chat\.googleapis\.com/\S+")


def load_env_file(path: Path) -> dict[str, str]:
    """`KEY=VALUE` мөрүүдийг уншина.

    .env дотор түлхүүргүй, зөвхөн webhook URL байсан ч ажиллана — тэр
    тохиолдолд CHAT_WEBHOOK_URL гэж үзнэ.
    """
    out: dict[str, str] = {}
    if not path.exists():
        return out

    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        if "=" in line and not line.lower().startswith("http"):
            key, _, value = line.partition("=")
            out[key.strip()] = value.strip().strip("'\"")
            continue

        match = _WEBHOOK_RE.search(line)
        if match:
            out.setdefault("CHAT_WEBHOOK_URL", match.group(0))

    return out


@dataclass(frozen=True)
class Settings:
    """Ажиллах бүх тохиргоо."""

    spreadsheet_id: str
    webhook_url: str
    credentials_path: Path
    state_path: Path

    timezone: ZoneInfo = ZoneInfo("Asia/Ulaanbaatar")

    critical_days: int = 7      # "нэн яаралтай" гэж үзэх хоног
    due_soon_days: int = 30     # "ойртсон" гэж үзэх хоног
    max_list_items: int = 5     # картад жагсаах мөрийн дээд тоо
    max_exception_items: int = 10
    stale_report_days: int = 8  # 7 хоногийн тайлан хэдэн хоног гарахгүй бол анхааруулах

    # Хуудсыг оноор нь автоматаар сонгоно: 2026 онд "OB 2026", 2027 онд "OB 2027".
    register_sheet_pattern: str = "Obligations {year}"
    # Гараар тогтоох бол (жишээ нь хоёр оныг зэрэг унших) — энэ давамгайлна.
    register_sheets: tuple[str, ...] | None = None
    runlog_sheet_hint: str = "weekly"

    @property
    def spreadsheet_url(self) -> str:
        return f"https://docs.google.com/spreadsheets/d/{self.spreadsheet_id}/edit"


def load_settings(env_path: Path | None = None) -> Settings:
    """`.env` + орчны хувьсагчаас Settings угсарна (орчны хувьсагч давамгайлна)."""
    env = load_env_file(env_path or (ROOT / ".env"))

    def value(key: str, default: str = "") -> str:
        return os.environ.get(key) or env.get(key) or default

    webhook = value("CHAT_WEBHOOK_URL")
    if not webhook:
        raise RuntimeError(
            "CHAT_WEBHOOK_URL олдсонгүй. .env дотор Google Chat webhook URL-ээ "
            "нэмнэ үү (нүцгэн URL эсхүл CHAT_WEBHOOK_URL=... хэлбэрээр)."
        )

    spreadsheet_id = value(
        "SPREADSHEET_ID", "1fS3eBYObw8l9zKv-Gz02xTWVoUZwixgk62uRDMxqI_0"
    )

    credentials = Path(
        value("GOOGLE_APPLICATION_CREDENTIALS", str(ROOT / "service-account.json"))
    )

    def as_int(key: str, default: int) -> int:
        raw = value(key)
        return int(raw) if raw.strip().isdigit() else default

    sheets_raw = value("REGISTER_SHEETS")
    register = (
        tuple(s.strip() for s in sheets_raw.split(",") if s.strip())
        if sheets_raw
        else None
    )

    return Settings(
        spreadsheet_id=spreadsheet_id,
        webhook_url=webhook,
        credentials_path=credentials,
        state_path=Path(value("STATE_PATH", str(ROOT / "state.json"))),
        timezone=ZoneInfo(value("TIME_ZONE", "Asia/Ulaanbaatar")),
        critical_days=as_int("CRITICAL_DAYS", 7),
        due_soon_days=as_int("DUE_SOON_DAYS", 30),
        max_list_items=as_int("MAX_LIST_ITEMS", 5),
        register_sheet_pattern=value(
            "REGISTER_SHEET_PATTERN", "Obligations {year}"
        ),
        register_sheets=register,
        runlog_sheet_hint=value("RUNLOG_SHEET_HINT", "weekly"),
    )
