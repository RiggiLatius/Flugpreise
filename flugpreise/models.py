"""Datenmodelle für Abfragen und Angebote."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class Segment:
    """Ein einzelnes Flugsegment (ein Flug ohne Umstieg)."""

    departure_airport: str
    departure_time: str
    arrival_airport: str
    arrival_time: str
    airline: str
    flight_number: str
    duration_min: int | None
    travel_class: str | None
    airplane: str | None = None

    @classmethod
    def from_serpapi(cls, seg: dict) -> "Segment":
        dep = seg.get("departure_airport") or {}
        arr = seg.get("arrival_airport") or {}
        return cls(
            departure_airport=(dep.get("id") or "").upper(),
            departure_time=dep.get("time") or "",
            arrival_airport=(arr.get("id") or "").upper(),
            arrival_time=arr.get("time") or "",
            airline=seg.get("airline") or "",
            flight_number=seg.get("flight_number") or "",
            duration_min=seg.get("duration"),
            travel_class=seg.get("travel_class"),
            airplane=seg.get("airplane"),
        )


@dataclass
class Offer:
    """Ein gefiltertes, vergleichbar aufbereitetes Flugangebot."""

    price: float
    currency: str
    airlines: list[str]
    total_duration_min: int | None
    stops: int
    layover_airports: list[str]
    layover_details: list[dict]
    departure_airport: str
    departure_time: str
    arrival_airport: str
    arrival_time: str
    travel_class: str
    baggage_checked: str
    baggage_carry_on: str
    segments: list[Segment]
    booking_token: str | None = None
    carbon_emissions_g: int | None = None
    return_segments: list[Segment] = field(default_factory=list)
    return_layover_airports: list[str] = field(default_factory=list)

    @property
    def airline_label(self) -> str:
        return ", ".join(dict.fromkeys(self.airlines)) or "unbekannt"

    def fare_summary(self) -> str:
        """Kurze, menschenlesbare Zusammenfassung des Angebots."""
        dur = _fmt_duration(self.total_duration_min)
        hubs = "/".join(self.layover_airports) or "-"
        return (
            f"{self.airline_label} | {self.travel_class} | "
            f"{self.stops} Umstieg(e) über {hubs} | Gesamtdauer {dur} | "
            f"Aufgegeben: {self.baggage_checked}; Handgepäck: {self.baggage_carry_on}"
        )

    def to_row(self) -> dict:
        d = asdict(self)
        d["airlines"] = json.dumps(self.airlines, ensure_ascii=False)
        d["layover_airports"] = ",".join(self.layover_airports)
        d["layover_details"] = json.dumps(self.layover_details, ensure_ascii=False)
        d["segments"] = json.dumps(
            [asdict(s) for s in self.segments], ensure_ascii=False
        )
        d["return_segments"] = json.dumps(
            [asdict(s) for s in self.return_segments], ensure_ascii=False
        )
        d["return_layover_airports"] = ",".join(self.return_layover_airports)
        return d


@dataclass
class QueryResult:
    """Metadaten einer Abfrage plus die zugehörigen Top-N-Angebote."""

    queried_at_utc: str = field(default_factory=_now_utc_iso)
    route: str = ""
    outbound_date: str = ""
    return_date: str | None = None
    trip_type: str = ""
    passengers: dict = field(default_factory=dict)
    currency: str = "EUR"
    total_results: int = 0
    filtered_results: int = 0
    offers: list[Offer] = field(default_factory=list)


def _fmt_duration(minutes: int | None) -> str:
    if not minutes:
        return "?"
    h, m = divmod(int(minutes), 60)
    return f"{h}h{m:02d}m"
