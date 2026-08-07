"""Google Chat картууд — удирдлагад ойлгомжтой энгийн хэлээр."""

from __future__ import annotations

import datetime as dt
from typing import Any, Sequence

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


def tier_label(tier: str) -> str:
    lowered = tier.lower()
    if "tier 1" in lowered:
        return "Tier 1 — лицензийн эрсдэл"
    if "tier 2" in lowered:
        return "Tier 2 — үйл ажиллагаа"
    if "tier 3" in lowered:
        return "Tier 3 — тайлагнал"
    return tier or "—"


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


def problem_reason(item: Obligation) -> str:
    """Яагаад асуудалтай болохыг нэг мөрөөр."""
    if item.days_left is not None and item.days_left < 0:
        status = f"  ·  {item.status}" if item.status else ""
        return f"{day_label(item.days_left)}{status}"
    return item.status or "төлөв тодорхойгүй"


def _obligation_widget(item: Obligation, *, icon: str, top: str) -> dict[str, Any]:
    return {
        "decoratedText": {
            "startIcon": {"knownIcon": icon},
            "topLabel": top,
            "text": f"<b>{trim(item.name, 70)}</b>",
            "bottomLabel": (
                f"{tier_label(item.tier)}  ·  {item.license}"
                f"  ·  {item.owner or 'эзэн тодорхойгүй'}"
            ),
            "wrapText": True,
        }
    }


def _open_button(settings: Settings) -> dict[str, Any]:
    return {
        "buttonList": {
            "buttons": [
                {
                    "text": "Бүртгэлийг нээх",
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
) -> dict[str, Any]:
    """Өдөр тутмын товч — дүгнэлт болон хамгийн ойртсон үүргүүд."""
    if summary.overdue:
        verdict = f"🔴 {summary.overdue} үүрэг хугацаа хэтэрсэн — нэн даруй арга хэмжээ авна уу."
    elif summary.flagged:
        verdict = (
            f"🔴 {summary.flagged} үүрэг асуудалтай төлөвт байна "
            "(Exception open / Rejected) — шийдвэр шаардлагатай."
        )
    elif summary.critical:
        verdict = (
            f"🟠 {summary.critical} үүрэг 7 хоногийн дотор дуусна — "
            "энэ долоо хоногт хийгдэх ёстой."
        )
    else:
        verdict = "🟢 Хугацаа хэтэрсэн үүрэг алга. Хяналт хэвийн."

    widgets: list[dict[str, Any]] = [
        {
            "decoratedText": {
                "topLabel": "ӨНӨӨДРИЙН ДҮГНЭЛТ",
                "text": f"<b>{verdict}</b>",
                "wrapText": True,
            }
        },
    ]

    if warning:
        widgets.insert(
            0,
            {
                "decoratedText": {
                    "startIcon": {"knownIcon": "DESCRIPTION"},
                    "topLabel": "⚠️ АНХААРУУЛГА",
                    "text": warning,
                    "wrapText": True,
                }
            },
        )

    sections: list[dict[str, Any]] = [{"widgets": widgets}]

    # Дүгнэлтэд дурдсан асуудалтай үүргүүдийг нэрлэн харуулна — "3 үүрэг
    # асуудалтай" гэсэн тоо аль үүрэг болох нь тодорхойгүй үлдэхээс сэргийлнэ.
    problems = problem_rows(rows)
    shown_problems = problems[: settings.max_exception_items]

    if shown_problems:
        problem_widgets = [
            _obligation_widget(
                item,
                icon="CLOCK",
                top=f"{problem_reason(item)}  ·  {item.id}",
            )
            for item in shown_problems
        ]
        if len(problems) > len(shown_problems):
            problem_widgets.append(
                {
                    "textParagraph": {
                        "text": f"…бусад {len(problems) - len(shown_problems)} үүргийг "
                        "бүртгэлээс харна уу."
                    }
                }
            )
        sections.append(
            {
                "header": f"🔴 АСУУДАЛТАЙ {len(problems)} ҮҮРЭГ",
                "widgets": problem_widgets,
            }
        )

    listed = {item.id for item in shown_problems}
    urgent = sorted(
        (
            item
            for item in rows
            if item.is_active
            and item.days_left is not None
            and item.days_left <= settings.due_soon_days
            and item.id not in listed
        ),
        key=lambda item: item.days_left,
    )[: settings.max_list_items]

    if urgent:
        sections.append(
            {
                "header": f"ХАМГИЙН ОЙРТСОН {len(urgent)} ҮҮРЭГ",
                "widgets": [
                    _obligation_widget(
                        item,
                        icon="CLOCK" if item.days_left < 0 else "STAR",
                        top=f"{day_label(item.days_left)}  ·  {item.id}",
                    )
                    for item in urgent
                ],
            }
        )

    sections.append({"widgets": [_open_button(settings)]})

    return {
        "cardsV2": [
            {
                "cardId": f"daily-{summary.stamp}",
                "card": {
                    "header": {
                        "title": "Лицензийн үүргийн өдөр тутмын хяналт",
                        "subtitle": (
                            f"{summary.stamp}  ·  идэвхтэй {summary.active} үүрэг"
                            f"  ·  Tier 1: {summary.tier1}"
                            + (f"  ·  эх: {source}" if source else "")
                        ),
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
