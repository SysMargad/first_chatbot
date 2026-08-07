"""Google Chat webhook руу илгээх."""

from __future__ import annotations

import json
from typing import Any

import requests

TIMEOUT_SECONDS = 30


def send(webhook_url: str, payload: dict[str, Any], *, dry_run: bool = False) -> None:
    """Мессежийг илгээнэ. `dry_run` үед зөвхөн хэвлээд гарна."""
    if dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        print("[dry-run] Илгээгээгүй.")
        return

    response = requests.post(
        webhook_url,
        json=payload,
        headers={"Content-Type": "application/json; charset=UTF-8"},
        timeout=TIMEOUT_SECONDS,
    )

    if not response.ok:
        raise RuntimeError(
            f"Chat илгээхэд алдаа гарлаа ({response.status_code}): {response.text[:500]}"
        )

    print(f"Chat илгээгдлээ ({response.status_code})")
