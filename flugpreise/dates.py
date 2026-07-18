"""Hilfsfunktionen rund um Datumsangaben."""

from __future__ import annotations

from datetime import date, datetime, timedelta


def parse_date(value: str) -> date:
    """Parst ein ISO-Datum 'YYYY-MM-DD'."""
    return datetime.strptime(value.strip(), "%Y-%m-%d").date()


def parse_serpapi_datetime(value: str) -> datetime | None:
    """Parst einen SerpApi-Zeitstempel 'YYYY-MM-DD HH:MM' (Zeit optional)."""
    if not value:
        return None
    value = value.strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def date_in_window(value: date, start: date, end: date) -> bool:
    """True, wenn ``start <= value <= end`` (inklusiv)."""
    return start <= value <= end


def daterange(start: date, end: date, step_days: int) -> list[date]:
    """Liste von ``start`` bis ``end`` (inklusiv) in ``step_days``-Schritten.

    Das Enddatum ist immer enthalten, auch wenn es nicht exakt auf ein
    Rasterintervall fällt.
    """
    if step_days < 1:
        step_days = 1
    if end < start:
        return [start]
    out: list[date] = []
    cur = start
    while cur < end:
        out.append(cur)
        cur = cur + timedelta(days=step_days)
    if out and out[-1] != end:
        out.append(end)
    elif not out:
        out.append(end)
    return out
