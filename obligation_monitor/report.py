"""Портфелийн нэгтгэл — лиценз, Tier болон үүргийн төрлөөр.

Картын 01–05 хэсгийн бүх тоог энд бэлддэг. `cards.py` зөвхөн зурна.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from typing import Sequence

from .analyze import BAD_STATUSES, EVIDENCE_GAP, Summary
from .config import Settings
from .sheets import Obligation

# Лицензийн ID суффикс: L01–L24 (олгогдсон) эсхүл S8901 (сонгон шалгаруулалт).
# Бусад суффикс (NCM, C01 …) нь нэгдсэн scope — олон лицензэд нэгэн зэрэг хамаарна.
_LICENSE_KEY_RE = re.compile(r"^[LS]\d+$", re.IGNORECASE)
_PENDING_KEY_RE = re.compile(r"^S\d+$", re.IGNORECASE)
_LICENSE_NUMBER_RE = re.compile(r"^[A-Za-z]{1,3}[-\s]?\d{4,}$")

# Төлөвийн ангилал — картад энэ дарааллаар харагдана
STATUS_BUCKETS: tuple[tuple[str, str], ...] = (
    ("Эхлээгүй", "not started"),
    ("Хэрэгжиж", "in progress"),
    ("Хүргүүлсэн", "submitted"),
    ("Хүлээгдэж", "not yet due"),
    ("Биелсэн", "completed"),
)


def parse_license(item: Obligation, *, pooled: bool) -> tuple[str, str, str]:
    """`XV-020915 – Цагаан жалга - 2 (NGE)` → (дугаар, төслийн нэр, компани)."""
    raw = re.sub(r"\[.*$", "", item.license).strip().rstrip("…").strip()

    if pooled:
        return "", "бүх хайгуулын лиценз", item.company

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

    if not _LICENSE_NUMBER_RE.match(number):
        number = ""  # `Сонгон 8901` — дугаар хараахан олгогдоогүй
    return number, name, company or item.company


@dataclass
class LicenseGroup:
    """Нэг лиценз (эсхүл нэгдсэн scope) дээрх бүх үүрэг."""

    key: str
    number: str
    project: str
    company: str
    pooled: bool
    rows: list[Obligation] = field(default_factory=list)

    @property
    def active_rows(self) -> list[Obligation]:
        return [item for item in self.rows if item.is_active]

    @property
    def total(self) -> int:
        return len(self.rows)

    @property
    def active(self) -> int:
        return len(self.active_rows)

    @property
    def pending_number(self) -> bool:
        """Сонгон шалгаруулалтаар авсан, дугаар хүлээгдэж буй."""
        return bool(_PENDING_KEY_RE.match(self.key))

    def buckets(self) -> dict[str, int]:
        counts = {label: 0 for label, _ in STATUS_BUCKETS}
        for item in self.active_rows:
            status = item.status.strip().lower()
            for label, needle in STATUS_BUCKETS:
                if needle in status:
                    counts[label] += 1
                    break
        return counts

    @property
    def done(self) -> int:
        return self.buckets()["Биелсэн"]

    @property
    def overdue(self) -> int:
        return sum(
            1
            for item in self.active_rows
            if item.days_left is not None and item.days_left < 0
        )

    @property
    def red(self) -> int:
        """Хугацаа хэтрээгүй ч төлөв нь блоклогдсон (Exception open / Rejected)."""
        return sum(
            1
            for item in self.active_rows
            if not (item.days_left is not None and item.days_left < 0)
            and item.status.strip().lower() in BAD_STATUSES
        )

    def due_within(self, days: int) -> int:
        return sum(
            1
            for item in self.active_rows
            if item.days_left is not None and 0 <= item.days_left <= days
        )

    @property
    def evidence_gap(self) -> int:
        return sum(
            1
            for item in self.active_rows
            if item.evidence.strip().lower() in EVIDENCE_GAP
        )

    @property
    def next_due(self) -> dt.date | None:
        dates = [
            item.due
            for item in self.active_rows
            if item.due and item.days_left is not None and item.days_left >= 0
        ]
        return min(dates) if dates else None

    @property
    def days_left(self) -> int | None:
        upcoming = [
            item.days_left
            for item in self.active_rows
            if item.days_left is not None and item.days_left >= 0
        ]
        return min(upcoming) if upcoming else None

    def flagged(self, settings: Settings) -> bool:
        return bool(
            self.overdue
            or self.red
            or self.evidence_gap
            or self.due_within(settings.due_soon_days)
        )


@dataclass
class TierStat:
    name: str
    title: str
    active: int = 0
    exception: int = 0
    overdue: int = 0
    red: int = 0
    evidence_gap: int = 0


@dataclass
class TypeStat:
    """Үүргийн төрөл (OB-07 гэх мэт) — бүх лицензээр нэгтгэсэн."""

    code: str
    name: str
    total: int = 0
    overdue: int = 0
    due_soon: int = 0
    evidence_gap: int = 0
    red: int = 0
    next_due: dt.date | None = None

    @property
    def flagged(self) -> bool:
        return bool(self.overdue or self.red or self.evidence_gap or self.due_soon)


@dataclass
class Portfolio:
    licenses: list[LicenseGroup]
    pooled: list[LicenseGroup]
    tiers: list[TierStat]
    types: list[TypeStat]

    @property
    def license_total(self) -> int:
        return len(self.licenses)

    @property
    def license_granted(self) -> int:
        return sum(1 for group in self.licenses if not group.pending_number)

    @property
    def license_pending(self) -> int:
        return sum(1 for group in self.licenses if group.pending_number)

    @property
    def license_critical(self) -> int:
        """Хугацаа хэтэрсэн эсхүл блоклогдсон үүрэгтэй лиценз."""
        return sum(1 for group in self.licenses if group.overdue or group.red)

    def license_flagged(self, settings: Settings) -> int:
        return sum(1 for group in self.licenses if group.flagged(settings))

    def by_company(self, settings: Settings) -> list[tuple[str, list[LicenseGroup]]]:
        """Компаниар бүлэглэнэ — анхаарах лиценз олонтой нь эхэнд."""
        groups: dict[str, list[LicenseGroup]] = {}
        for group in self.licenses:
            groups.setdefault(group.company or "—", []).append(group)
        for members in groups.values():
            members.sort(key=lambda g: (not g.flagged(settings), g.days_left or 9999))
        return sorted(
            groups.items(),
            key=lambda pair: -sum(1 for g in pair[1] if g.flagged(settings)),
        )

    @property
    def pooled_rows(self) -> int:
        return sum(group.total for group in self.pooled)


def _tier_key(item: Obligation) -> str:
    tier = item.tier.lower()
    if "tier 1" in tier:
        return "Tier 1"
    if "tier 2" in tier:
        return "Tier 2"
    if "tier 3" in tier:
        return "Tier 3"
    return "Бусад"


_TIER_TITLES = {
    "Tier 1": "Лицензийн ноцтой эрсдэл",
    "Tier 2": "Үйл ажиллагааны ноцтой эрсдэл",
    "Tier 3": "Материаллаг комплайнсын эрсдэл",
}


def build_portfolio(
    rows: Sequence[Obligation], settings: Settings, *, today: dt.date
) -> Portfolio:
    """Бүх мөрийг лиценз, Tier болон үүргийн төрлөөр нэгтгэнэ."""
    groups: dict[str, LicenseGroup] = {}

    for item in rows:
        suffix = item.id.rsplit("-", 1)[-1]
        pooled = not _LICENSE_KEY_RE.match(suffix)
        # Нэгдсэн scope-ийг компаниар нь нэгтгэнэ — OB-12-NCM ба OB-13-C03 хоёр
        # адилхан "NCM-ийн бүх лиценз"-д хамаарна.
        key = f"pool:{item.company}" if pooled else suffix
        group = groups.get(key)
        if group is None:
            number, project, company = parse_license(item, pooled=pooled)
            group = LicenseGroup(
                key=suffix,
                number=number,
                project=project,
                company=company,
                pooled=pooled,
            )
            groups[key] = group
        group.rows.append(item)

    licenses = sorted(
        (g for g in groups.values() if not g.pooled),
        key=lambda g: (g.company, g.number or "я", g.project),
    )
    pooled = sorted((g for g in groups.values() if g.pooled), key=lambda g: g.company)

    # ---- Tier
    tiers = {
        name: TierStat(name=name, title=title) for name, title in _TIER_TITLES.items()
    }

    for item in rows:
        if not item.is_active:
            continue
        stat = tiers.get(_tier_key(item))
        if stat is None:
            continue
        stat.active += 1

        overdue = item.days_left is not None and item.days_left < 0
        red = not overdue and item.status.strip().lower() in BAD_STATUSES
        gap = item.evidence.strip().lower() in EVIDENCE_GAP

        stat.overdue += overdue
        stat.red += red
        stat.evidence_gap += gap
        stat.exception += bool(overdue or red or gap)

    # ---- Үүргийн төрөл
    types: dict[str, TypeStat] = {}
    for item in rows:
        if not item.is_active:
            continue
        code = item.id.rsplit("-", 1)[0]
        stat = types.get(code)
        if stat is None:
            stat = TypeStat(code=code, name=item.name)
            types[code] = stat

        stat.total += 1
        overdue = item.days_left is not None and item.days_left < 0
        stat.overdue += overdue
        stat.red += not overdue and item.status.strip().lower() in BAD_STATUSES
        stat.evidence_gap += item.evidence.strip().lower() in EVIDENCE_GAP
        if item.days_left is not None and 0 <= item.days_left <= settings.due_soon_days:
            stat.due_soon += 1
        if item.due and item.days_left is not None and item.days_left >= 0:
            stat.next_due = min(stat.next_due or item.due, item.due)

    ordered_types = sorted(
        types.values(),
        key=lambda s: (-s.overdue, -s.red, -s.evidence_gap, -s.due_soon, s.code),
    )

    return Portfolio(
        licenses=licenses,
        pooled=pooled,
        tiers=[tiers[name] for name in ("Tier 1", "Tier 2", "Tier 3")],
        types=ordered_types,
    )


def executive_note(portfolio: Portfolio, summary: Summary, settings: Settings) -> str:
    """Удирдлагын товч үнэлгээ — нэг догол мөр."""
    parts = [
        f"{portfolio.license_total} лицензээс "
        f"{portfolio.license_flagged(settings)} нь анхаарах төлөвтэй."
    ]

    if summary.overdue:
        parts.append(
            f"{summary.overdue} үүрэг хугацаа хэтэрсэн — нэн даруй арга хэмжээ авна."
        )
    else:
        parts.append("Хугацаа хэтэрсэн үүрэг алга.")

    parts.append(
        f"{settings.critical_days} хоногийн дотор {summary.critical}, "
        f"{settings.critical_days + 1}–{settings.due_soon_days} хоногт "
        f"{summary.due_soon} үүрэг байна."
    )

    if summary.evidence_gap:
        parts.append(
            f"{summary.evidence_gap} evidence gap-ийг нөхөж баталгаажуулах шаардлагатай."
        )

    return " ".join(parts)


def describe_license(item: Obligation) -> str:
    """Нэг мөрийн лицензийг `XV-022954 · Дархан сүүжийн худаг · TIM` хэлбэрт."""
    suffix = item.id.rsplit("-", 1)[-1]
    pooled = not _LICENSE_KEY_RE.match(suffix)
    number, project, company = parse_license(item, pooled=pooled)
    return "  ·  ".join(part for part in (number, project, company) if part)
