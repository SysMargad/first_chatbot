"""Нэгтгэл, exception илрүүлэлт болон тайлангийн хяналт."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Sequence

from .config import Settings
from .sheets import Obligation, RegisterData

# Эрсдэлтэй гэж үзэх ажлын төлөвүүд
BAD_STATUSES = {"overdue", "rejected", "exception open"}
EVIDENCE_GAP = {"missing", "partial"}
# Эдгээр evidence төлөвтэй мөрөнд Drive холбоос шаардахгүй
LINK_NOT_REQUIRED = {"", "not applicable", "not yet due"}

SEVERITY_CRITICAL = 1
SEVERITY_WARNING = 2
SEVERITY_INFO = 3


@dataclass
class Summary:
    """Өдөр тутмын картад харагдах тоонууд."""

    stamp: str
    total: int = 0
    active: int = 0
    tier1: int = 0
    overdue: int = 0   # due date нь өнгөрсөн
    flagged: int = 0   # огноо хэтрээгүй ч төлөв нь асуудалтай (Exception open / Rejected)
    critical: int = 0
    due_soon: int = 0
    evidence_gap: int = 0
    no_link: int = 0
    closed: int = 0
    in_progress: int = 0
    not_started: int = 0
    # 30 хоногт дуусах боловч ажил хараахан эхлээгүй — "ACTION RISK" хайрцаг
    not_started_soon: int = 0

    @property
    def evidence_rate(self) -> int:
        if not self.active:
            return 0
        return round((self.active - self.no_link) / self.active * 100)

    def to_dict(self) -> dict[str, Any]:
        data = {k: v for k, v in self.__dict__.items()}
        data["evidence_rate"] = self.evidence_rate
        return data


@dataclass
class Exception_:
    """Мэдэгдэх шаардлагатай нэг тохиолдол."""

    key: str
    obligation: Obligation
    severity: int
    reason: str

    @property
    def days_left(self) -> int | None:
        return self.obligation.days_left


def is_overdue(item: Obligation) -> bool:
    if item.days_left is not None and item.days_left < 0:
        return True
    return item.status.strip().lower() in BAD_STATUSES


def needs_link(item: Obligation) -> bool:
    return not item.link and item.evidence.strip().lower() not in LINK_NOT_REQUIRED


def summarize(data: RegisterData, settings: Settings, *, today: dt.date | None = None) -> Summary:
    today = today or dt.datetime.now(settings.timezone).date()
    summary = Summary(stamp=today.isoformat(), total=len(data.rows))

    for item in data.rows:
        if not item.is_active:
            continue
        summary.active += 1

        if item.is_tier1:
            summary.tier1 += 1

        status = item.status.lower()
        if "completed" in status or "closed" in status:
            summary.closed += 1
        elif any(word in status for word in ("in progress", "submitted", "pending")):
            summary.in_progress += 1
        elif "not started" in status:
            summary.not_started += 1

        # Хугацааны ангилал — харилцан давхцахгүй
        if item.days_left is not None and item.days_left < 0:
            summary.overdue += 1
        elif item.status.strip().lower() in BAD_STATUSES:
            summary.flagged += 1
        elif item.days_left is not None:
            if item.days_left <= settings.critical_days:
                summary.critical += 1
            elif item.days_left <= settings.due_soon_days:
                summary.due_soon += 1

        if (
            item.days_left is not None
            and 0 <= item.days_left <= settings.due_soon_days
            and "not started" in status
        ):
            summary.not_started_soon += 1

        if item.evidence.strip().lower() in EVIDENCE_GAP:
            summary.evidence_gap += 1
        if needs_link(item):
            summary.no_link += 1

    return summary


def detect_exceptions(data: RegisterData, settings: Settings) -> list[Exception_]:
    """Удирдлагад мэдэгдэх нөхцөлүүд. Мөр бүрээс хамгийн ноцтой нэгийг л авна."""
    found: list[Exception_] = []

    for item in data.rows:
        if not item.is_active:
            continue

        days = item.days_left
        status = item.status.strip().lower()

        if days is not None and days < 0:
            found.append(
                _make(item, "OVERDUE", SEVERITY_CRITICAL, f"Хугацаа {abs(days)} хоногоор хэтэрсэн")
            )
            continue

        if status in BAD_STATUSES:
            found.append(
                _make(item, f"STATUS-{status}", SEVERITY_CRITICAL, f"Төлөв: {item.status}")
            )
            continue

        if days is not None and days <= settings.critical_days and item.is_tier1:
            found.append(
                _make(
                    item,
                    "T1-CRITICAL",
                    SEVERITY_CRITICAL,
                    f"{days} хоногийн дараа дуусна (лицензийн эрсдэл)",
                )
            )
            continue

        if days is not None and days <= settings.due_soon_days:
            if item.evidence.strip().lower() in EVIDENCE_GAP:
                found.append(
                    _make(
                        item,
                        "EVIDENCE-GAP",
                        SEVERITY_WARNING,
                        f"{days} хоног үлдсэн, нотлох баримт: {item.evidence}",
                    )
                )
                continue

            if days <= settings.critical_days and "not started" in status:
                found.append(
                    _make(
                        item,
                        "NOT-STARTED",
                        SEVERITY_WARNING,
                        f"{days} хоног үлдсэн, ажил эхлээгүй",
                    )
                )
                continue

            if needs_link(item):
                found.append(
                    _make(
                        item,
                        "NO-LINK",
                        SEVERITY_INFO,
                        f"{days} хоног үлдсэн, Drive холбоос оруулаагүй",
                    )
                )

    found.sort(key=lambda e: (e.severity, e.days_left if e.days_left is not None else 9999))
    return found


def _make(item: Obligation, kind: str, severity: int, reason: str) -> Exception_:
    due = item.due.isoformat() if item.due else "no-due"
    return Exception_(
        key=f"{item.id}|{kind}|{due}",
        obligation=item,
        severity=severity,
        reason=reason,
    )


def check_run_log(
    entries: Sequence[dict[str, Any]],
    settings: Settings,
    *,
    sheet_found: bool,
    today: dt.date | None = None,
) -> list[str]:
    """7 хоногийн тайлан тогтмол гарч байгаа эсэхийг шалгана."""
    if not sheet_found:
        return ["Run log хуудас олдсонгүй — тайлангийн бүртгэл хянагдахгүй байна."]

    today = today or dt.datetime.now(settings.timezone).date()
    issues: list[str] = []
    last_sent: dt.date | None = None
    stalled = 0

    for entry in entries:
        if entry["week"].upper().startswith("TEST"):
            continue  # тест ажиллуулалтыг тооцохгүй

        if entry["status"] == "SENT":
            sent = entry["sent_at"]
            if sent and (last_sent is None or sent > last_sent):
                last_sent = sent
        else:
            stalled += 1

    if last_sent is None:
        issues.append("7 хоногийн тайлан хэзээ ч амжилттай илгээгдээгүй байна.")
    else:
        gap = (today - last_sent).days
        if gap > settings.stale_report_days:
            issues.append(
                f"Сүүлийн 7 хоногийн тайлан {gap} хоногийн өмнө ({last_sent.isoformat()}) "
                "илгээгдсэн. Хуваарь тасарсан байж болзошгүй."
            )

    if stalled:
        issues.append(
            f"{stalled} ажиллуулалт дуусаагүй төлөвт (SENT биш) үлдсэн — "
            "тайлан үүсгэх явцад алдаа гарсан байж магадгүй."
        )

    return issues
