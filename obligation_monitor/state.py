"""Өмнөх ажиллуулалтын төлөв — аль exception-ийг аль хэдийн мэдэгдсэнийг санана."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

MAX_SEEN_KEYS = 800


def load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[анхаар] Төлөвийн файл уншигдсангүй ({exc}). Шинээр эхэлнэ.")
        return {}


def save(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )


def seen_keys(state: dict[str, Any]) -> set[str]:
    value = state.get("seen_exceptions")
    return set(value) if isinstance(value, list) else set()


def remember_exceptions(state: dict[str, Any], keys: list[str]) -> None:
    """Одоо идэвхтэй байгаа түлхүүрүүдийг л хадгална.

    Ингэснээр шийдэгдсэн асуудал дахин гарвал дахин мэдэгдэнэ.
    """
    state["seen_exceptions"] = keys[:MAX_SEEN_KEYS]
