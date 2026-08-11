"""Google Chat картууд — удирдлагад ойлгомжтой энгийн хэлээр."""

from __future__ import annotations

import datetime as dt
import re
from typing import Any, Sequence

from . import risk
from .analyze import BAD_STATUSES, SEVERITY_CRITICAL, SEVERITY_WARNING, Exception_, Summary
from .config import Settings
from .sheets import Obligation, trim


def day_label(days: int | None) -> str:
    if days is None:
        return "огноо тодорхойгүй"
    if days < 0:
        return f"{abs(days)} хоног ХЭТЭРСЭН"
    if days == 0:
        return "ӨНӨӨДӨР дуусна"
    return f"{days} хоног үлдсэн"


def severity_label(severity: int) -> str:
    if severity == SEVERITY_CRITICAL:
        return "🔴 КРИТИК"
    if severity == SEVERITY_WARNING:
        return "🟠 АНХААР"
    return "🟡 БАРИМТ"


def problem_rows(rows: Sequence[Obligation]) -> list[Obligation]:
    """Дүгнэлтэд тоологддог асуудалтай үүргүүд — хэтэрсэн нь эхэнд.

    `summarize`-тай яг ижил ангилал: эхлээд хугацаа хэтэрсэн, дараа нь
    хугацаа хэтрээгүй ч төлөв нь асуудалтай (Exception open / Rejected).
    """
    overdue = [
        item
        for item in rows
        if item.is_active and item.days_left is not None and item.days_left < 0
    ]
    flagged = [
        item
        for item in rows
        if item.is_active
        and not (item.days_left is not None and item.days_left < 0)
        and item.status.strip().lower() in BAD_STATUSES
    ]
    overdue.sort(key=lambda item: item.days_left)
    flagged.sort(key=lambda item: (item.status.lower(), item.id))
    return overdue + flagged


def _problem_headline(item: Obligation) -> str:
    """Яагаад асуудалтай болохыг богино гарчиг болгоно."""
    if item.days_left is not None and item.days_left < 0:
        return f"{abs(item.days_left)} хоног хэтэрсэн"
    return item.status or "төлөв тодорхойгүй"


# `XV-022954` төрлийн жинхэнэ лицензийн дугаар (`Сонгон 8901` гэх мэт
# түр нэрийг оруулахгүй — лиценз хараахан олгогдоогүй гэсэн үг)
_LICENSE_NUMBER_RE = re.compile(r"^[A-Za-z]{1,3}[-\s]?\d{4,}$")


def license_line(item: Obligation) -> str:
    """`XV-022954 – Дархан сүүжийн худаг (TIM)` → `XV-022954 · Дархан сүүжийн худаг · TIM`."""
    raw = re.sub(r"\[.*$", "", item.license).strip().rstrip("…").strip()

    number, name = "", raw
    for separator in ("–", "—", " - "):
        if separator in raw:
            left, right = raw.split(separator, 1)
            number, name = left.strip(), right.strip()
            break

    company = ""
    inside = re.search(r"\(([^)]+)\)\s*$", name)
    if inside:
        company = inside.group(1).strip()
        name = name[: inside.start()].strip()

    parts = []
    if number and _LICENSE_NUMBER_RE.match(number):
        parts.append(number)
    if name:
        parts.append(trim(name, 40))
    if company or item.company:
        parts.append(company or item.company)
    return "  ·  ".join(parts)


def _kpi(icon: str, count: int, label: str) -> dict[str, Any]:
    return {
        "horizontalSizeStyle": "FILL_AVAILABLE_SPACE",
        "horizontalAlignment": "START",
        "verticalAlignment": "CENTER",
        "widgets": [
            {
                "decoratedText": {
                    "text": f"<b>{icon} {count}</b>",
                    "bottomLabel": label,
                    "wrapText": True,
                }
            }
        ],
    }


def _kpi_row(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    return {"columns": {"columnItems": [left, right]}}


def _obligation_block(
    item: Obligation,
    *,
    icon: str,
    headline: str,
    situation: str,
    show_owner: bool,
) -> dict[str, Any]:
    """Нэг үүргийн бүтэн блок — гарчиг, нэр, лиценз, эрсдэл, хариуцагч."""
    lines = [
        f"<b>{icon} {headline}  ·  {item.id}</b>",
        trim(item.name, 90),
    ]

    location = license_line(item)
    if location:
        lines.append(location)

    lines += ["", f"<b>⚠️ {risk.label(item)}</b>", risk.note(item, situation)]

    if show_owner:
        lines += ["", f"Owner  ·  {item.owner or 'тодорхойгүй'}"]

    return {"textParagraph": {"text": "<br>".join(lines)}}


def _stack(blocks: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Блокуудын хооронд зураас тавина."""
    widgets: list[dict[str, Any]] = []
    for index, block in enumerate(blocks):
        if index:
            widgets.append({"divider": {}})
        widgets.append(block)
    return widgets


def _open_button(settings: Settings) -> dict[str, Any]:
    return {
        "buttonList": {
            "buttons": [
                {
                    "text": "📊 ҮҮРГИЙН БҮРТГЭЛ НЭЭХ",
                    "onClick": {"openLink": {"url": settings.spreadsheet_url}},
                }
            ]
        }
    }


def build_daily_card(
    summary: Summary,
    rows: Sequence[Obligation],
    settings: Settings,
    *,
    source: str = "",
    warning: str | None = None,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """Өдөр тутмын товч — KPI хайрцаг, шийдвэр шаардах болон ойртсон үүргүүд."""
    problems = problem_rows(rows)
    shown_problems = problems[: settings.max_exception_items]
    listed = {item.id for item in shown_problems}

    upcoming = sorted(
        (
            item
            for item in rows
            if item.is_active
            and item.days_left is not None
            and 0 <= item.days_left <= settings.due_soon_days
            and item.id not in listed
        ),
        key=lambda item: item.days_left,
    )[: settings.max_list_items]

    # Толгойн өнгө — хамгийн ноцтой байдлаар
    if problems:
        mood = "🔴"
    elif summary.critical:
        mood = "🟠"
    else:
        mood = "🟢"

    sections: list[dict[str, Any]] = []

    if warning:
        sections.append(
            {
                "widgets": [
                    {
                        "decoratedText": {
                            "startIcon": {"knownIcon": "DESCRIPTION"},
                            "topLabel": "⚠️ АНХААРУУЛГА",
                            "text": warning,
                            "wrapText": True,
                        }
                    }
                ]
            }
        )

    sections.append(
        {
            "widgets": [
                _kpi_row(
                    _kpi("🔴", len(problems), "LICENSE RISK"),
                    _kpi("🟠", summary.not_started_soon, "ACTION RISK"),
                ),
                _kpi_row(
                    _kpi("🟡", summary.critical, f"≤ {settings.critical_days} ХОНОГТ"),
                    _kpi("🔵", summary.evidence_gap, "EVIDENCE GAP"),
                ),
            ]
        }
    )

    if shown_problems:
        blocks = [
            _obligation_block(
                item,
                icon="🔴",
                headline=_problem_headline(item),
                situation=risk.situation(
                    item, bad_status=item.status.strip().lower() in BAD_STATUSES
                ),
                show_owner=True,
            )
            for item in shown_problems
        ]
        widgets = _stack(blocks)
        if len(problems) > len(shown_problems):
            widgets.append(
                {
                    "textParagraph": {
                        "text": f"…бусад {len(problems) - len(shown_problems)} үүргийг "
                        "бүртгэлээс харна уу."
                    }
                }
            )
        sections.append(
            {"header": f"⚠️ ШИЙДВЭР ШААРДАХ · {len(problems)}", "widgets": widgets}
        )

    if upcoming:
        sections.append(
            {
                "header": f"⏳ ОЙРТСОН ХУГАЦАА · {len(upcoming)}",
                "widgets": _stack(
                    [
                        _obligation_block(
                            item,
                            icon="🟠" if item.days_left <= settings.critical_days else "🟡",
                            headline=day_label(item.days_left),
                            situation=risk.DUE,
                            show_owner=False,
                        )
                        for item in upcoming
                    ]
                ),
            }
        )

    sections.append({"widgets": [_open_button(settings)]})

    subtitle = f"{summary.stamp}  ·  {summary.active} идэвхтэй"
    if now:
        subtitle += f"  ·  Snapshot {now.strftime('%H:%M')}"
    if source:
        subtitle += f"  ·  {source}"

    return {
        "cardsV2": [
            {
                "cardId": f"daily-{summary.stamp}",
                "card": {
                    "header": {
                        "title": f"{mood} ЛИЦЕНЗИЙН ҮҮРГИЙН ӨДӨР ТУТМЫН ХЯНАЛТ",
                        "subtitle": subtitle,
                        "imageType": "CIRCLE",
                    },
                    "sections": sections,
                },
            }
        ]
    }


def build_exception_card(
    fresh: Sequence[Exception_],
    settings: Settings,
    now: dt.datetime,
) -> dict[str, Any]:
    shown = list(fresh)[: settings.max_exception_items]

    sections: list[dict[str, Any]] = [
        {
            "widgets": [
                {
                    "decoratedText": {
                        "startIcon": {
                            "knownIcon": (
                                "CLOCK" if item.severity == SEVERITY_CRITICAL else "DESCRIPTION"
                            )
                        },
                        "topLabel": f"{severity_label(item.severity)}  ·  {item.obligation.id}",
                        "text": f"<b>{trim(item.obligation.name, 70)}</b>",
                        "bottomLabel": (
                            f"{item.reason}\n{item.obligation.license}  ·  "
                            f"{item.obligation.owner or 'эзэн тодорхойгүй'}"
                        ),
                        "wrapText": True,
                    }
                }
                for item in shown
            ],
        },
    ]

    if len(fresh) > len(shown):
        sections.append(
            {
                "widgets": [
                    {
                        "textParagraph": {
                            "text": f"…бусад {len(fresh) - len(shown)} exception бүртгэлээс харна уу."
                        }
                    }
                ]
            }
        )

    sections.append({"widgets": [_open_button(settings)]})

    return {
        "cardsV2": [
            {
                "cardId": f"exc-{now.strftime('%Y%m%d%H%M')}",
                "card": {
                    "header": {
                        "title": "⚠️ Exception анхааруулга",
                        "subtitle": now.strftime("%Y-%m-%d %H:%M"),
                        "imageType": "CIRCLE",
                    },
                    "sections": sections,
                },
            }
        ]
    }


def build_watchdog_card(issues: Sequence[str], now: dt.datetime) -> dict[str, Any]:
    return {
        "cardsV2": [
            {
                "cardId": f"watchdog-{now.strftime('%Y%m%d')}",
                "card": {
                    "header": {
                        "title": "🔧 Тайлангийн хяналт",
                        "subtitle": "Reporting control шалгалт",
                    },
                    "sections": [
                        {
                            "widgets": [
                                {
                                    "decoratedText": {
                                        "startIcon": {"knownIcon": "CLOCK"},
                                        "text": issue,
                                        "wrapText": True,
                                    }
                                }
                                for issue in issues
                            ]
                        }
                    ],
                },
            }
        ]
    }
