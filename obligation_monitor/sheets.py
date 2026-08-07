"""Obligation Register spreadsheet-ээс дата унших.

Багануудыг ГАРЧГИЙН НЭРЭЭР олно — багана нэмэгдэж/шилжсэн ч код эвдэрдэггүй.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from google.oauth2 import service_account
from googleapiclient.discovery import build

from .config import Settings

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

# Excel/Sheets серийн огнооны эхлэл
_SERIAL_EPOCH = dt.date(1899, 12, 30)

Row = Sequence[Any]


# ---------------------------------------------------------------- загварууд


@dataclass
class Obligation:
    """Register-ийн нэг мөр."""

    sheet: str
    id: str
    name: str
    tier: str
    license: str
    company: str
    owner: str
    approver: str
    escalation: dt.date | None
    due: dt.date | None
    flag: str
    status: str
    evidence: str
    link: str
    days_left: int | None

    @property
    def is_active(self) -> bool:
        """`Not applicable` эсхүл хоосон статустай мөрийг тооцохгүй."""
        status = self.status.strip().lower()
        return bool(status) and "not applicable" not in status

    @property
    def is_tier1(self) -> bool:
        return "tier 1" in self.tier.lower()


@dataclass
class RegisterData:
    rows: list[Obligation]
    sheets_used: list[str]
    year: int | None = None
    warning: str | None = None


# ---------------------------------------------------------------- туслахууд


def normalize(value: Any) -> str:
    """Харьцуулахад тохиромжтой хэлбэрт оруулна."""
    return re.sub(r"\s+", " ", str(value if value is not None else "")).strip().lower()


def parse_date(value: Any, *, today: dt.date | None = None) -> dt.date | None:
    """Date, `yyyy-mm-dd` текст болон Sheets серийн дугаарыг таньна."""
    if value is None or value == "":
        return None

    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        # 20000–80000 хооронд байвал огнооны серийн дугаар гэж үзнэ (1954–2119)
        if 20000 <= value <= 80000:
            return _SERIAL_EPOCH + dt.timedelta(days=int(value))
        return None

    text = str(value).strip()

    iso = re.match(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", text)
    if iso:
        return _safe_date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))

    # Sheet-ийн локалиас шалтгаалан m/d/yyyy хэлбэрээр гардаг (ж: 8/6/2026)
    us = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})", text)
    if us:
        return _safe_date(int(us.group(3)), int(us.group(1)), int(us.group(2)))

    if text.isdigit():
        return parse_date(int(text), today=today)

    return None


def _safe_date(year: int, month: int, day: int) -> dt.date | None:
    try:
        return dt.date(year, month, day)
    except ValueError:
        return None


def parse_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(str(value).replace(",", "").strip()))
    except (TypeError, ValueError):
        return None


def clean_license(text: str) -> str:
    """`XV-023099 – Нэргүй өндөр (NGM); ...` → эхний лицензээр богиносгоно."""
    value = re.sub(r"\s+", " ", text).strip()
    if ";" in value:
        value = value.split(";", 1)[0] + " …"
    return trim(value, 60)


def trim(text: str, limit: int) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    return value if len(value) <= limit else value[: limit - 1] + "…"


# ---------------------------------------------------------------- API давхарга


def build_service(credentials_path: Path):
    """Sheets API клиент үүсгэнэ (service account)."""
    if not credentials_path.exists():
        raise RuntimeError(
            f"Service account файл олдсонгүй: {credentials_path}\n"
            "README.md-ийн 'Google хандалт тохируулах' хэсгийг үзнэ үү."
        )
    creds = service_account.Credentials.from_service_account_file(
        str(credentials_path), scopes=SCOPES
    )
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def list_sheet_titles(service, spreadsheet_id: str) -> list[str]:
    meta = (
        service.spreadsheets()
        .get(spreadsheetId=spreadsheet_id, fields="sheets.properties.title")
        .execute()
    )
    return [s["properties"]["title"] for s in meta.get("sheets", [])]


def match_title(titles: Iterable[str], wanted: str) -> str | None:
    """Яг таарал → хэсэгчилсэн таарал."""
    target = normalize(wanted)
    titles = list(titles)
    for title in titles:
        if normalize(title) == target:
            return title
    for title in titles:
        if target in normalize(title):
            return title
    return None


# `OB 2027`, `OB2027`, `OB-2027`, `OB_2027` бүгдийг таана
_YEAR_SHEET_RE = re.compile(r"^ob[\s._-]*(\d{4})\b")


def resolve_year_sheet(
    titles: Sequence[str], year: int, pattern: str = "OB {year}"
) -> tuple[str | None, str | None]:
    """Тухайн оны register хуудсыг олно.

    2026 онд `OB 2026`, 2027 онд `OB 2027` … гэх мэтээр автоматаар шилжинэ.
    Тухайн оных байхгүй бол хамгийн ойрын өмнөх оныг ашиглаж, анхааруулга
    буцаана — чимээгүй хоосон тайлан гаргахаас сэргийлнэ.
    """
    wanted = pattern.format(year=year)
    exact = match_title(titles, wanted)
    if exact:
        return exact, None

    # `OB <он>` хэлбэрийн бүх хуудсыг оноор нь цуглуулна
    candidates: dict[int, str] = {}
    for title in titles:
        found = _YEAR_SHEET_RE.match(normalize(title))
        if found:
            candidates[int(found.group(1))] = title

    # Нэрийн бичиглэл зөрсөн ч (ж: `OB2027`) тухайн оных нь байвал энэ хэвийн —
    # анхааруулга гаргах шаардлагагүй.
    if year in candidates:
        return candidates[year], None

    if not candidates:
        return None, f"'{wanted}' хуудас олдсонгүй, оны хуудас огт байхгүй байна."

    earlier = [y for y in candidates if y <= year]
    fallback_year = max(earlier) if earlier else min(candidates)
    return (
        candidates[fallback_year],
        f"'{wanted}' хуудас хараахан үүсээгүй тул '{candidates[fallback_year]}'-г "
        "түр ашиглаж байна. Шинэ оны бүртгэлийг үүсгэнэ үү.",
    )


def fetch_values(service, spreadsheet_id: str, title: str) -> list[Row]:
    """Хуудсыг бүтнээр нь уншина (харагдаж буй утгаар)."""
    result = (
        service.spreadsheets()
        .values()
        .get(
            spreadsheetId=spreadsheet_id,
            range=f"'{title}'",
            valueRenderOption="FORMATTED_VALUE",
            dateTimeRenderOption="FORMATTED_STRING",
        )
        .execute()
    )
    return result.get("values", [])


# ---------------------------------------------------------------- гарчиг тайлах


def find_header_row(values: Sequence[Row], marker: str = "obligation id") -> int:
    """`Obligation ID` бичээстэй нүдээр гарчгийн мөрийг таньна."""
    for index, row in enumerate(values[:20]):
        if any(normalize(cell) == marker for cell in row):
            return index
    return -1


def index_headers(header_row: Row) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for column, cell in enumerate(header_row):
        key = normalize(cell)
        if key and key not in mapping:
            mapping[key] = column
    return mapping


def pick(headers: dict[str, int], candidates: Sequence[str]) -> int:
    """Нэрсээс эхэлж таарсныг буцаана; олдохгүй бол -1."""
    for candidate in candidates:
        key = normalize(candidate)
        if key in headers:
            return headers[key]
    for candidate in candidates:
        fragment = normalize(candidate)
        for key, column in headers.items():
            if fragment in key:
                return column
    return -1


def cell(row: Row, column: int) -> Any:
    if column < 0 or column >= len(row):
        return ""
    return row[column]


def text(row: Row, column: int) -> str:
    return str(cell(row, column) or "").strip()


# ---------------------------------------------------------------- үндсэн уншилт

def _column_aliases(year: int) -> dict[str, list[str]]:
    """Хайх гарчгийн нэрс. Статус/evidence/link нь оноор ялгагддаг тул
    эхлээд тухайн оны багана, дараа нь helper багана руу шилжинэ."""
    return {
        "id": ["obligation id"],
        "name": ["үүргийн нэр"],
        "tier": ["criticality"],
        "license": ["лиценз / төсөл", "лиценз/төсөл"],
        "escalation": [
            "escalation date (идэвхтэй мөчлөг)",
            f"{year} escalation date",
            "escalation date",
        ],
        "due": [
            "дараагийн due date (идэвхтэй мөчлөг)",
            f"{year} due date",
            "due date",
        ],
        "days_left": ["үлдсэн хоног"],
        "flag": [
            "weekly report flag (идэвхтэй мөчлөг)",
            f"{year} weekly report flag",
            "weekly report flag",
        ],
        "status": [
            f"{year} одоогийн статус",
            "active status (helper)",
            "одоогийн статус",
        ],
        "evidence": [
            f"{year} evidence бүрдэлт",
            "active evidence (helper)",
            "evidence бүрдэлт",
        ],
        "link": [
            f"{year} exact evidence file link",
            f"{year} drive folder link",
            "active drive link (helper)",
            "evidence file link",
            "drive folder link",
        ],
        "owner": ["owner"],
        "approver": ["reviewer / approver", "approver"],
        "company": ["компани (helper)", "компани"],
    }


def collect_obligations(
    settings: Settings, *, today: dt.date | None = None, service=None
) -> RegisterData:
    """Register хуудсуудаас үүргүүдийг уншиж, нэгтгэж буцаана."""
    today = today or dt.datetime.now(settings.timezone).date()
    service = service or build_service(settings.credentials_path)

    titles = list_sheet_titles(service, settings.spreadsheet_id)
    rows: list[Obligation] = []
    used: list[str] = []
    warning: str | None = None

    # Гараар тогтоогоогүй бол зөвхөн тухайн оны хуудсыг уншина.
    if settings.register_sheets:
        wanted_titles = list(settings.register_sheets)
    else:
        resolved, warning = resolve_year_sheet(
            titles, today.year, settings.register_sheet_pattern
        )
        if warning:
            print(f"[анхаар] {warning}")
        wanted_titles = [resolved] if resolved else []

    for wanted in wanted_titles:
        title = match_title(titles, wanted)
        if not title:
            print(f"[анхаар] Хуудас олдсонгүй: {wanted}. Байгаа хуудсууд: {titles}")
            continue

        values = fetch_values(service, settings.spreadsheet_id, title)
        header_index = find_header_row(values)
        if header_index == -1:
            print(f"[анхаар] '{title}' дээр Obligation ID гарчиг олдсонгүй.")
            continue

        used.append(title)
        headers = index_headers(values[header_index])
        columns = {
            name: pick(headers, aliases)
            for name, aliases in _column_aliases(today.year).items()
        }

        for row in values[header_index + 1 :]:
            obligation_id = text(row, columns["id"])
            if not obligation_id.upper().startswith("OB-"):
                continue

            due = parse_date(cell(row, columns["due"]), today=today)
            days_left = (
                (due - today).days if due else parse_int(cell(row, columns["days_left"]))
            )

            rows.append(
                Obligation(
                    sheet=title,
                    id=obligation_id,
                    name=text(row, columns["name"]),
                    tier=text(row, columns["tier"]),
                    license=clean_license(text(row, columns["license"])),
                    company=text(row, columns["company"]),
                    owner=text(row, columns["owner"]),
                    approver=text(row, columns["approver"]),
                    escalation=parse_date(cell(row, columns["escalation"]), today=today),
                    due=due,
                    flag=text(row, columns["flag"]),
                    status=text(row, columns["status"]),
                    evidence=text(row, columns["evidence"]),
                    link=text(row, columns["link"]),
                    days_left=days_left,
                )
            )

    return RegisterData(
        rows=deduplicate(rows),
        sheets_used=used,
        year=today.year,
        warning=warning,
    )


def deduplicate(rows: Sequence[Obligation]) -> list[Obligation]:
    """Нэг ID 2026/2027 хоёуланд байвал идэвхтэй мөчлөгтэйг нь үлдээнэ."""

    def score(item: Obligation) -> int:
        return (2 if item.due else 0) + (1 if item.is_active else 0)

    best: dict[str, Obligation] = {}
    for item in rows:
        current = best.get(item.id)
        if current is None or score(item) > score(current):
            best[item.id] = item
    return list(best.values())


def read_run_log(settings: Settings, *, service=None) -> tuple[list[dict[str, Any]], str | None]:
    """Weekly Control хуудсан дахь REPORT RUN LOG-ийг уншина."""
    service = service or build_service(settings.credentials_path)
    titles = list_sheet_titles(service, settings.spreadsheet_id)
    title = match_title(titles, settings.runlog_sheet_hint)
    if not title:
        return [], None

    values = fetch_values(service, settings.spreadsheet_id, title)

    header_index, headers = -1, {}
    for index, row in enumerate(values):
        probe = index_headers(row)
        if "week key" in probe and "status" in probe:
            header_index, headers = index, probe
            break
    if header_index == -1:
        return [], title

    entries: list[dict[str, Any]] = []
    for row in values[header_index + 1 :]:
        week = text(row, headers.get("week key", -1))
        if not week:
            continue
        entries.append(
            {
                "week": week,
                "status": text(row, headers.get("status", -1)).upper(),
                "sent_at": parse_date(cell(row, headers.get("sent at", -1))),
                "error": text(row, headers.get("error", -1)),
            }
        )
    return entries, title
