"""Umwandlung roher SerpApi-Flugobjekte in :class:`Offer`-Objekte."""

from __future__ import annotations

from .filters import layover_codes_from_flight
from .models import Offer, Segment
from .normalize import normalize_baggage_for_airlines


def collect_flight_entries(data: dict) -> list[dict]:
    """Sammelt alle Flug-Einträge aus ``best_flights`` und ``other_flights``."""
    entries: list[dict] = []
    entries.extend(data.get("best_flights", []) or [])
    entries.extend(data.get("other_flights", []) or [])
    return entries


def build_offer(entry: dict, currency: str) -> Offer:
    """Baut aus einem SerpApi-Flugobjekt ein normalisiertes Angebot."""
    raw_segments = entry.get("flights", []) or []
    segments = [Segment.from_serpapi(s) for s in raw_segments]

    airlines = [s.airline for s in segments if s.airline]
    layover_codes = layover_codes_from_flight(entry)
    layover_details = entry.get("layovers", []) or []

    travel_class = ""
    if segments:
        travel_class = segments[0].travel_class or ""

    baggage = normalize_baggage_for_airlines(airlines)

    dep = segments[0] if segments else None
    arr = segments[-1] if segments else None

    return Offer(
        price=float(entry.get("price") or 0),
        currency=currency,
        airlines=airlines,
        total_duration_min=entry.get("total_duration"),
        stops=max(len(segments) - 1, 0),
        layover_airports=layover_codes,
        layover_details=layover_details,
        departure_airport=dep.departure_airport if dep else "",
        departure_time=dep.departure_time if dep else "",
        arrival_airport=arr.arrival_airport if arr else "",
        arrival_time=arr.arrival_time if arr else "",
        travel_class=travel_class,
        baggage_checked=baggage["checked"],
        baggage_carry_on=baggage["carry_on"],
        segments=segments,
        booking_token=entry.get("booking_token") or entry.get("departure_token"),
        carbon_emissions_g=(entry.get("carbon_emissions") or {}).get("this_flight"),
    )
