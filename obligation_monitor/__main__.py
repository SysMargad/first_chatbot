"""CLI — өдөр тутмын хяналтын командууд.

    python -m obligation_monitor daily        # өдөр бүрийн товч (үргэлж илгээнэ)
    python -m obligation_monitor exceptions   # зөвхөн ШИНЭ exception гарвал илгээнэ
    python -m obligation_monitor watchdog     # 7 хоногийн тайлан гарсан эсэх
    python -m obligation_monitor test         # холболт шалгах
    python -m obligation_monitor sheets       # spreadsheet-ийн хуудсуудыг жагсаах

Аль ч командад `--dry-run` нэмбэл илгээхгүй, зөвхөн хэвлэнэ.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

from . import analyze, cards, chat, sheets, state
from .config import Settings, load_settings


def _force_utf8_output() -> None:
    """Windows консол анхдагчаар cp1252 тул кирилл хэвлэхэд унадаг."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def _now(settings: Settings) -> dt.datetime:
    return dt.datetime.now(settings.timezone)


def cmd_daily(settings: Settings, args: argparse.Namespace) -> int:
    now = _now(settings)
    today = now.date()
    data = sheets.collect_obligations(settings, today=today)
    summary = analyze.summarize(data, settings, today=today)

    payload = cards.build_daily_card(
        summary,
        data.rows,
        settings,
        source=", ".join(data.sheets_used),
        warning=data.warning,
        now=now,
    )
    chat.send(settings.webhook_url, payload, dry_run=args.dry_run)

    print(
        f"Идэвхтэй {summary.active} үүрэг · хэтэрсэн {summary.overdue} · "
        f"7 хоногт {summary.critical} · баримт дутуу {summary.evidence_gap}"
    )
    return 0


def cmd_exceptions(settings: Settings, args: argparse.Namespace) -> int:
    today = _now(settings).date()
    data = sheets.collect_obligations(settings, today=today)
    found = analyze.detect_exceptions(data, settings)

    stored = state.load(settings.state_path)
    already = state.seen_keys(stored)
    fresh = [item for item in found if item.key not in already]

    if args.all:
        fresh = found

    if not fresh:
        print(f"Шинэ exception алга (нийт идэвхтэй: {len(found)})")
        return 0

    payload = cards.build_exception_card(fresh, settings, _now(settings))
    chat.send(settings.webhook_url, payload, dry_run=args.dry_run)

    if not args.dry_run:
        state.remember_exceptions(stored, [item.key for item in found])
        state.save(settings.state_path, stored)

    print(f"{len(fresh)} шинэ exception илгээгдлээ (нийт {len(found)})")
    return 0


def cmd_watchdog(settings: Settings, args: argparse.Namespace) -> int:
    entries, title = sheets.read_run_log(settings)
    issues = analyze.check_run_log(
        entries, settings, sheet_found=title is not None, today=_now(settings).date()
    )

    if not issues:
        print("Reporting control хэвийн")
        return 0

    payload = cards.build_watchdog_card(issues, _now(settings))
    chat.send(settings.webhook_url, payload, dry_run=args.dry_run)
    for issue in issues:
        print(f"  - {issue}")
    return 0


def cmd_test(settings: Settings, args: argparse.Namespace) -> int:
    today = _now(settings).date()
    data = sheets.collect_obligations(settings, today=today)
    summary = analyze.summarize(data, settings, today=today)

    if data.warning:
        print(f"АНХААРУУЛГА   : {data.warning}")
    print(f"Он            : {data.year}")
    print(f"Хуудсууд      : {', '.join(data.sheets_used) or '— олдсонгүй —'}")
    print(f"Уншсан мөр    : {len(data.rows)}")
    print(f"Идэвхтэй      : {summary.active}")
    print(f"Хэтэрсэн      : {summary.overdue}")
    print(f"7 хоногт      : {summary.critical}")
    print(f"30 хоногт     : {summary.due_soon}")
    print(f"Баримт дутуу  : {summary.evidence_gap}")
    print(f"Холбоосгүй    : {summary.no_link}")

    payload = {
        "text": (
            f"✅ *Тест амжилттай* — {len(data.rows)} үүрэг уншигдлаа "
            f"({', '.join(data.sheets_used) or 'хуудас олдсонгүй'}). "
            "Өдөр тутмын мэдэгдэл ажиллахад бэлэн."
        )
    }
    chat.send(settings.webhook_url, payload, dry_run=args.dry_run)
    return 0


def cmd_sheets(settings: Settings, args: argparse.Namespace) -> int:
    """Хуудсуудын жинхэнэ нэрийг харах — REGISTER_SHEETS тааруулахад хэрэгтэй."""
    service = sheets.build_service(settings.credentials_path)
    titles = sheets.list_sheet_titles(service, settings.spreadsheet_id)
    year = _now(settings).date().year

    if settings.register_sheets:
        chosen = [sheets.match_title(titles, w) for w in settings.register_sheets]
        note = "гараар тогтоосон (REGISTER_SHEETS)"
    else:
        resolved, warning = sheets.resolve_year_sheet(
            titles, year, settings.register_sheet_pattern
        )
        chosen = [resolved]
        note = warning or f"{year} оны хуудас"

    print(f"Spreadsheet: {settings.spreadsheet_url}")
    print(f"Одоогийн он : {year}  →  {note}\n")
    for title in titles:
        marker = "   ← ЭНЭ ХУУДСЫГ УНШИНА" if title in chosen else ""
        print(f"  {title}{marker}")
    return 0


COMMANDS = {
    "daily": cmd_daily,
    "exceptions": cmd_exceptions,
    "watchdog": cmd_watchdog,
    "test": cmd_test,
    "sheets": cmd_sheets,
}


def main(argv: list[str] | None = None) -> int:
    _force_utf8_output()

    parser = argparse.ArgumentParser(
        prog="obligation_monitor",
        description="Лицензийн үүргийн өдөр тутмын хяналт → Google Chat",
    )
    parser.add_argument("command", choices=sorted(COMMANDS), help="ажиллуулах команд")
    parser.add_argument(
        "--dry-run", action="store_true", help="илгээхгүй, зөвхөн хэвлэнэ"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="exceptions: шинэ эсэхийг үл харгалзан бүгдийг илгээнэ",
    )
    parser.add_argument("--env", type=Path, default=None, help=".env файлын зам")

    args = parser.parse_args(argv)

    try:
        settings = load_settings(args.env)
        return COMMANDS[args.command](settings, args)
    except Exception as exc:  # noqa: BLE001 — CLI-д ойлгомжтой алдаа харуулна
        print(f"АЛДАА: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
