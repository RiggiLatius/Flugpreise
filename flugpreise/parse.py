"""Umwandlung roher SerpApi-Flugobjekte in Legs/Offers."""

from __future__ import annotations

from .dates import parse_serpapi_datetime
from .filters import layover_codes_from_flight
from .models import Leg, Segment
from .normalize import normalize_baggage_for_airlines


def collect_flight_entries(data: dict) -> list[dict]:
    """Sammelt alle Flug-Einträge aus ``best_flights`` und ``other_flights``."""
    entries: list[dict] = []
    entries.extend(data.get("best_flights", []) or [])
    entries.extend(data.get("other_flights", []) or [])
    return entries


def leg_from_entry(entry: dict) -> Leg:
    """Baut aus einem SerpApi-Flugobjekt ein normalisiertes Leg."""
    raw_segments = entry.get("flights", []) or []
    segments = [Segment.from_serpapi(s) for s in raw_segments]
    airlines = [s.airline for s in segments if s.airline]
    baggage = normalize_baggage_for_airlines(airlines)

    origin = segments[0].departure_airport if segments else ""
    destination = segments[-1].arrival_airport if segments else ""

    return Leg(
        origin=origin,
        destination=destination,
        segments=segments,
        layover_airports=layover_codes_from_flight(entry),
        duration_min=entry.get("total_duration"),
        baggage_checked=baggage["checked"],
        baggage_carry_on=baggage["carry_on"],
    )


def entry_price(entry: dict) -> float:
    return float(entry.get("price") or 0)


def entry_token(entry: dict) -> str | None:
    return entry.get("departure_token") or entry.get("booking_token")


def leg_arrival_datetime(entry: dict):
    """Ankunftszeitpunkt des letzten Segments eines Eintrags (oder None)."""
    segs = entry.get("flights", []) or []
    if not segs:
        return None
    arr = (segs[-1].get("arrival_airport") or {}).get("time")
    return parse_serpapi_datetime(arr)
