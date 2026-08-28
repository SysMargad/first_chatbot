"""Google Chat картууд — удирдлагад ойлгомжтой энгийн хэлээр.

Өдөр тутмын карт нь гүйцэтгэх удирдлагын тайлангийн бүтэцтэй:

    01  Лицензийн портфелийн тойм
    02  Лиценз тус бүрийн төлөв
    03  Tier ангиллын хураангуй
    04  Удирдлагын анхаарах асуудал
    05  Үүргийн төрлийн exception
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Sequence

from . import report, risk
from .analyze import BAD_STATUSES, SEVERITY_CRITICAL, SEVERITY_WARNING, Exception_, Summary
from .config import Settings
from .report import LicenseGroup, Portfolio, TierStat, TypeStat
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
        if item.is_active and item.is_late
    ]
    flagged = [
        item
        for item in rows
        if item.is_active
        and not item.is_late
        and item.status.strip().lower() in BAD_STATUSES
    ]
    overdue.sort(key=lambda item: item.days_left)
    flagged.sort(key=lambda item: (item.status.lower(), item.id))
    return overdue + flagged


def _problem_headline(item: Obligation) -> str:
    """Яагаад асуудалтай болохыг богино гарчиг болгоно."""
    if item.is_late:
        return f"{abs(item.days_left)} хоног хэтэрсэн"
    return item.status or "төлөв тодорхойгүй"


# ---------------------------------------------------------------- widget тулгуур


def _kpi(label: str, value: Any, detail: str) -> dict[str, Any]:
    return {
        "horizontalSizeStyle": "FILL_AVAILABLE_SPACE",
        "horizontalAlignment": "START",
        "verticalAlignment": "TOP",
        "widgets": [
            {
                "decoratedText": {
                    "topLabel": label,
                    "text": f"<b>{value}</b>",
                    "bottomLabel": detail,
                    "wrapText": True,
                }
            }
        ],
    }


def _kpi_row(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    return {"columns": {"columnItems": [left, right]}}


def _paragraph(lines: Sequence[str]) -> dict[str, Any]:
    return {"textParagraph": {"text": "<br>".join(lines)}}


def _section(
    header: str,
    widgets: list[dict[str, Any]],
    *,
    collapsible: bool = False,
    visible: int = 1,
) -> dict[str, Any]:
    section: dict[str, Any] = {"header": header, "widgets": widgets}
    if collapsible:
        section["collapsible"] = True
        section["uncollapsibleWidgetsCount"] = visible
    return section


def _open_button(settings: Settings) -> dict[str, Any]:
    return {
        "buttonList": {
            "buttons": [
                {
                    "text": "📊 ХЯНАЛТЫН БҮРТГЭЛ НЭЭХ",
                    "onClick": {"openLink": {"url": settings.spreadsheet_url}},
                }
            ]
        }
    }


def _stack(blocks: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Блокуудын хооронд зураас тавина."""
    widgets: list[dict[str, Any]] = []
    for index, block in enumerate(blocks):
        if index:
            widgets.append({"divider": {}})
        widgets.append(block)
    return widgets


# ---------------------------------------------------------------- 01–05 хэсгүүд


def _license_flag(group: LicenseGroup, settings: Settings) -> str:
    if group.overdue or group.red:
        return "🔴"
    if group.flagged(settings):
        return "🟠"
    return "🟢"


def _license_line(group: LicenseGroup, settings: Settings) -> str:
    """Нэг лицензийн мөр — дугаар, төсөл, тоонууд, ойрын хугацаа."""
    title = group.number or "дугаар хүлээгдэж"
    facts = [f"{group.active}/{group.total} идэвхтэй"]

    if group.overdue:
        facts.append(f"хэтэрсэн {group.overdue}")
    if group.red:
        facts.append(f"RED {group.red}")

    due_soon = group.due_within(settings.due_soon_days)
    if due_soon:
        facts.append(f"{settings.due_soon_days} хоногт {due_soon}")
    if group.evidence_gap:
        facts.append(f"нотолгоо {group.evidence_gap}")

    if group.next_due:
        facts.append(f"{group.next_due.isoformat()} ({day_label(group.days_left)})")

    return (
        f"{_license_flag(group, settings)} {title} · "
        f"<b>{trim(group.project, 28)}</b> — {' · '.join(facts)}"
    )


def _portfolio_section(
    portfolio: Portfolio, summary: Summary, settings: Settings
) -> dict[str, Any]:
    widgets = [
        _kpi_row(
            _kpi(
                "Нийт лиценз",
                portfolio.license_total,
                f"{portfolio.license_granted} хүчинтэй · "
                f"{portfolio.license_pending} дугаар хүлээгдэж",
            ),
            _kpi(
                "Ноцтой лиценз",
                portfolio.license_critical,
                f"{portfolio.license_flagged(settings)} лиценз анхаарах төлөвтэй",
            ),
        ),
        _kpi_row(
            _kpi(
                "Идэвхтэй үүрэг",
                summary.active,
                f"{summary.closed} биелсэн · {summary.total - summary.active} хамаарахгүй",
            ),
            _kpi("Хугацаа хэтэрсэн", summary.overdue, "Due date-аас тооцсон"),
        ),
        _kpi_row(
            _kpi(
                f"{settings.due_soon_days} хоногт дуусах",
                summary.critical + summary.due_soon,
                f"{settings.critical_days} хоногт {summary.critical} үүрэг",
            ),
            _kpi("Evidence gap", summary.evidence_gap, "Missing эсхүл Partial"),
        ),
        {
            "decoratedText": {
                "topLabel": "УДИРДЛАГЫН ТОВЧ ҮНЭЛГЭЭ",
                "text": report.executive_note(portfolio, summary, settings),
                "wrapText": True,
            }
        },
    ]
    return _section("01 · ЛИЦЕНЗИЙН ПОРТФЕЛИЙН ТОЙМ", widgets)


def _license_section(portfolio: Portfolio, settings: Settings) -> dict[str, Any]:
    widgets: list[dict[str, Any]] = []

    for company, members in portfolio.by_company(settings):
        flagged = sum(1 for group in members if group.flagged(settings))
        lines = [
            f"<b>{company} · {len(members)} лиценз · {flagged} анхаарах</b>",
            *(_license_line(group, settings) for group in members),
        ]
        widgets.append(_paragraph(lines))

    if portfolio.pooled:
        widgets.append(
            _paragraph(
                [
                    "<b>КОМПАНИЙН НЭГДСЭН SCOPE</b>",
                    f"{len(portfolio.pooled)} нэгдсэн scope · {portfolio.pooled_rows} үүрэг "
                    "— лицензийн тоонд давхардуулан оруулаагүй.",
                    "  ·  ".join(
                        f"{group.company} {group.total}" for group in portfolio.pooled
                    ),
                ]
            )
        )

    return _section(
        "02 · ЛИЦЕНЗ ТУС БҮРИЙН ТӨЛӨВ", widgets, collapsible=True, visible=1
    )


def _tier_widget(stat: TierStat) -> dict[str, Any]:
    return {
        "decoratedText": {
            "topLabel": f"{stat.name} · {stat.title}",
            "text": f"<b>{stat.exception} / {stat.active}</b>  exception / идэвхтэй",
            "bottomLabel": (
                f"хэтэрсэн {stat.overdue}  ·  RED {stat.red}  ·  "
                f"нотолгоо дутуу {stat.evidence_gap}"
            ),
            "wrapText": True,
        }
    }


def _tier_section(portfolio: Portfolio) -> dict[str, Any]:
    return _section(
        "03 · TIER АНГИЛЛЫН ХУРААНГУЙ",
        [_tier_widget(stat) for stat in portfolio.tiers],
    )


def group_problems(
    problems: Sequence[Obligation],
) -> list[tuple[Obligation, list[Obligation]]]:
    """Ижил үүргийг олон лицензээр нэгтгэнэ.

    OB-05 нь 7 лиценз дээр адилхан хугацаа хэтэрсэн бол 7 биш нэг мөр болж,
    доор нь нөлөөлсөн лицензүүд жагсана — загварын "бүх хайгуулын лиценз"
    блоктой ижил.
    """
    groups: dict[tuple[str, str], list[Obligation]] = {}
    for item in problems:
        key = (item.id.rsplit("-", 1)[0], _problem_headline(item))
        groups.setdefault(key, []).append(item)
    return [(members[0], members) for members in groups.values()]


def _issue_block(lead: Obligation, members: Sequence[Obligation]) -> dict[str, Any]:
    situation = risk.situation(
        lead, bad_status=lead.status.strip().lower() in BAD_STATUSES
    )
    code = lead.id.rsplit("-", 1)[0]
    scope = f"{code}  ·  {len(members)} лиценз" if len(members) > 1 else lead.id

    lines = [
        f"<b>🔴 {_problem_headline(lead)}  ·  {scope}</b>",
        trim(lead.name, 90),
    ]

    if len(members) > 1:
        by_company: dict[str, list[str]] = {}
        for item in members:
            number, project, company = report.parse_license(item, pooled=False)
            by_company.setdefault(company or "—", []).append(number or project)
        lines.append(
            "  ·  ".join(
                f"{company}: {', '.join(names)}" for company, names in by_company.items()
            )
        )
    else:
        location = report.describe_license(lead)
        if location:
            lines.append(location)

    lines += ["", f"<b>⚠️ {risk.label(lead)}</b>", risk.note(lead, situation)]

    owners = sorted({item.owner for item in members if item.owner})
    lines += ["", f"Owner  ·  {', '.join(owners) or 'тодорхойгүй'}"]

    return _paragraph(lines)


def _issue_section(
    problems: Sequence[Obligation], settings: Settings
) -> dict[str, Any]:
    groups = group_problems(problems)
    shown = groups[: settings.max_exception_items]

    widgets = _stack([_issue_block(lead, members) for lead, members in shown])
    if len(groups) > len(shown):
        widgets.append(
            _paragraph(
                [f"Нэмэлт {len(groups) - len(shown)} асуудал хяналтын бүртгэлд байна."]
            )
        )
    return _section(f"04 · УДИРДЛАГЫН АНХААРАХ АСУУДАЛ · {len(problems)}", widgets)


def _type_line(stat: TypeStat, settings: Settings) -> list[str]:
    facts = [f"нийт {stat.total}"]
    if stat.overdue:
        facts.append(f"хэтэрсэн {stat.overdue}")
    if stat.red:
        facts.append(f"RED {stat.red}")
    if stat.due_soon:
        facts.append(f"{settings.due_soon_days} хоногт {stat.due_soon}")
    if stat.evidence_gap:
        facts.append(f"нотолгоо дутуу {stat.evidence_gap}")
    if stat.next_due:
        facts.append(f"ойрын хугацаа {stat.next_due.isoformat()}")

    return [
        f"<b>{stat.code} · {trim(stat.name, 60)}</b>",
        "  ·  ".join(facts),
    ]


def _type_section(portfolio: Portfolio, settings: Settings) -> dict[str, Any] | None:
    flagged = [stat for stat in portfolio.types if stat.flagged]
    if not flagged:
        return None

    shown = flagged[: settings.max_list_items]
    widgets = [_paragraph(_type_line(stat, settings)) for stat in shown]
    if len(flagged) > len(shown):
        widgets.append(
            _paragraph(
                [f"Нэмэлт {len(flagged) - len(shown)} үүргийн төрөл бүртгэлд байна."]
            )
        )
    return _section(
        f"05 · ҮҮРГИЙН ТӨРЛИЙН EXCEPTION · {len(flagged)}",
        widgets,
        collapsible=True,
        visible=1,
    )


# ---------------------------------------------------------------- үндсэн картууд


def build_daily_card(
    summary: Summary,
    rows: Sequence[Obligation],
    settings: Settings,
    *,
    source: str = "",
    warning: str | None = None,
    now: dt.datetime | None = None,
    today: dt.date | None = None,
) -> dict[str, Any]:
    """Өдөр тутмын гүйцэтгэх удирдлагын тайлан."""
    today = today or dt.date.fromisoformat(summary.stamp)
    portfolio = report.build_portfolio(rows, settings, today=today)

    problems = problem_rows(rows)

    if summary.overdue or portfolio.license_critical:
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

    sections.append({"widgets": [_open_button(settings)]})
    sections.append(_portfolio_section(portfolio, summary, settings))
    sections.append(_license_section(portfolio, settings))
    sections.append(_tier_section(portfolio))

    if problems:
        sections.append(_issue_section(problems, settings))

    type_section = _type_section(portfolio, settings)
    if type_section:
        sections.append(type_section)

    sections.append(
        {
            "widgets": [
                _paragraph(
                    [
                        f"Тайлангийн source: {source or '—'}  ·  "
                        "үлдсэн хоногийг due date-аас дахин тооцсон."
                    ]
                )
            ]
        }
    )

    subtitle = f"{summary.stamp}  ·  {summary.active} идэвхтэй үүрэг"
    if source:
        subtitle += f"  ·  {source}"
    if now:
        subtitle += f"  ·  Snapshot {now.strftime('%H:%M')}"

    return {
        "cardsV2": [
            {
                "cardId": f"daily-{summary.stamp}",
                "card": {
                    "header": {
                        "title": f"{mood} ЛИЦЕНЗИЙН ҮҮРГИЙН ХЯНАЛТ",
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
                            f"{item.reason}\n{report.describe_license(item.obligation)}"
                            f"  ·  {item.obligation.owner or 'эзэн тодорхойгүй'}"
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
