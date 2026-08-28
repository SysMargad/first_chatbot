"""Үүрэг бүрийн эрсдэлийг удирдлагад ойлгомжтой нэг өгүүлбэрээр илэрхийлнэ.

⚠️ ЭНД БИЧСЭН ТЕКСТ НЬ ЗАГВАР — эрх зүйн албан ёсны дүгнэлт БИШ.
Тухайн үүргийн онцлогоос үл хамааран Tier болон төлөвөөр нь ерөнхийлж
бичсэн болно. Хууль/комплаенсийн багаар хянуулж, шаардлагатай бол
зөвхөн ЭНЭ файлын текстийг засна — картын код өөрчлөгдөхгүй.
"""

from __future__ import annotations

from .sheets import Obligation

# Санхүүгийн шинжтэй үүргийг нэрээр нь таних түлхүүр үгс
_FINANCIAL_HINTS = ("төл", "хураамж", "татвар", "үнийн зөрүү", "барьцаа")

# Нөхцөл байдал: хугацаа хэтэрсэн / төлөв асуудалтай / хугацаа ойртсон
OVERDUE = "overdue"
FLAGGED = "flagged"
DUE = "due"


def is_financial(item: Obligation) -> bool:
    name = item.name.lower()
    return any(hint in name for hint in _FINANCIAL_HINTS)


def label(item: Obligation) -> str:
    """Эрсдэлийн ангилал — картад том үсгээр гарна."""
    if item.is_tier1:
        return "LICENSE / FINANCIAL RISK" if is_financial(item) else "LICENSE / SUSPENSION RISK"
    tier = item.tier.lower()
    if "tier 2" in tier:
        return "OPERATIONAL RISK"
    if "tier 3" in tier:
        return "REPORTING RISK"
    return "COMPLIANCE RISK"


def note(item: Obligation, situation: str) -> str:
    """Яагаад эрсдэлтэй болохыг нэг өгүүлбэрээр."""
    if item.is_tier1 and is_financial(item):
        return {
            OVERDUE: "Төлбөр хугацаандаа хийгдээгүй тул алданги нэмэгдэж, "
            "лиценз олголтын дараагийн шат хаагдах эрсдэлтэй.",
            FLAGGED: "Төлбөрийн асуудал шийдэгдээгүй тул лиценз олголтын "
            "дараагийн шат хаагдах эрсдэлтэй.",
        }.get(
            situation,
            "Хугацаанд төлөөгүй бол лиценз олголтын дараагийн шат "
            "хаагдах эрсдэлтэй.",
        )

    if item.is_tier1:
        return {
            OVERDUE: "Хугацаа хэтэрсэн тул тусгай зөвшөөрлийн үйл ажиллагаанд "
            "хязгаарлалт үүсэх эрсдэлтэй.",
            FLAGGED: "Зөрчил арилгагдаагүй тохиолдолд тусгай зөвшөөрлийн "
            "үйл ажиллагаанд хязгаарлалт үүсэх эрсдэлтэй.",
        }.get(
            situation,
            "Хугацаанд биелүүлээгүй бол тусгай зөвшөөрлийн нөхцөл "
            "зөрчигдөх эрсдэлтэй.",
        )

    tier = item.tier.lower()
    if "tier 2" in tier:
        return (
            "Хугацаа хэтэрсэн тул үйл ажиллагааны тасалдал үүсэх эрсдэлтэй."
            if situation == OVERDUE
            else "Биелүүлээгүй тохиолдолд үйл ажиллагааны тасалдал үүсэх эрсдэлтэй."
        )
    if "tier 3" in tier:
        return (
            "Тайлан хугацаандаа гараагүй тул зөрчил бүртгэгдэх эрсдэлтэй."
            if situation == OVERDUE
            else "Тайлан хугацаандаа гараагүй бол зөрчил бүртгэгдэх эрсдэлтэй."
        )
    return "Биелэлтийг хянаж, хариуцагчтай тодруулах шаардлагатай."


def situation(item: Obligation, *, bad_status: bool) -> str:
    if item.is_late:
        return OVERDUE
    return FLAGGED if bad_status else DUE
