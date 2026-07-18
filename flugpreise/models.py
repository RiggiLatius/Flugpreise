"""Datenmodelle für Abfragen und Angebote (Open-Jaw)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _fmt_duration(minutes: int | None) -> str:
    if not minutes:
        return "?"
    h, m = divmod(int(minutes), 60)
    return f"{h}h{m:02d}m"


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
class Leg:
    """Ein Reise-Leg (Hinflug oder Rückflug) mit Segmenten und Zwischenstopps."""

    origin: str
    destination: str
    segments: list[Segment]
    layover_airports: list[str]
    duration_min: int | None = None
    baggage_checked: str = ""
    baggage_carry_on: str = ""

    @property
    def stops(self) -> int:
        return max(len(self.segments) - 1, 0)

    @property
    def airlines(self) -> list[str]:
        return [s.airline for s in self.segments if s.airline]

    @property
    def departure_time(self) -> str:
        return self.segments[0].departure_time if self.segments else ""

    @property
    def arrival_time(self) -> str:
        return self.segments[-1].arrival_time if self.segments else ""


@dataclass
class Offer:
    """Ein vollständiges, gefiltertes Open-Jaw-Angebot (beide Legs SIN/BKK)."""

    price: float
    currency: str
    outbound: Leg
    return_leg: Leg | None
    total_duration_min: int | None = None
    booking_token: str | None = None
    carbon_emissions_g: int | None = None
    return_verified: bool = False

    # ---- abgeleitete Darstellung ------------------------------------------

    @property
    def airlines(self) -> list[str]:
        a = list(self.outbound.airlines)
        if self.return_leg:
            a += self.return_leg.airlines
        return list(dict.fromkeys(a))

    @property
    def airline_label(self) -> str:
        return ", ".join(self.airlines) or "unbekannt"

    @property
    def layover_airports(self) -> list[str]:
        los = list(self.outbound.layover_airports)
        if self.return_leg:
            los += self.return_leg.layover_airports
        return los

    @property
    def stops(self) -> int:
        s = self.outbound.stops
        if self.return_leg:
            s += self.return_leg.stops
        return s

    def fare_summary(self) -> str:
        out_hubs = "/".join(self.outbound.layover_airports) or "-"
        ret_hubs = "/".join(self.return_leg.layover_airports) if self.return_leg else "-"
        ret = ""
        if self.return_leg:
            ret = f" | Rückflug über {ret_hubs}"
        return (
            f"{self.airline_label} | Hinflug über {out_hubs}{ret} | "
            f"Aufg.: {self.outbound.baggage_checked}; Handg.: {self.outbound.baggage_carry_on}"
        )

    def to_row(self) -> dict:
        def leg_row(leg: Leg | None) -> str:
            if not leg:
                return json.dumps(None)
            d = asdict(leg)
            return json.dumps(d, ensure_ascii=False)

        return {
            "price": self.price,
            "currency": self.currency,
            "airlines": json.dumps(self.airlines, ensure_ascii=False),
            "total_duration_min": self.total_duration_min,
            "stops": self.stops,
            "layover_airports": ",".join(self.layover_airports),
            "outbound_departure_time": self.outbound.departure_time,
            "outbound_arrival_time": self.outbound.arrival_time,
            "outbound_hubs": ",".join(self.outbound.layover_airports),
            "outbound_baggage_checked": self.outbound.baggage_checked,
            "outbound_baggage_carry_on": self.outbound.baggage_carry_on,
            "return_departure_time": self.return_leg.departure_time if self.return_leg else "",
            "return_arrival_time": self.return_leg.arrival_time if self.return_leg else "",
            "return_hubs": ",".join(self.return_leg.layover_airports) if self.return_leg else "",
            "return_baggage_checked": self.return_leg.baggage_checked if self.return_leg else "",
            "return_verified": 1 if self.return_verified else 0,
            "outbound_leg": leg_row(self.outbound),
            "return_leg": leg_row(self.return_leg),
            "booking_token": self.booking_token,
            "carbon_emissions_g": self.carbon_emissions_g,
        }


@dataclass
class QueryResult:
    """Ergebnis einer Abfrage für EINE Datumskombination."""

    queried_at_utc: str = field(default_factory=_now_utc_iso)
    route: str = ""
    outbound_date: str = ""      # Abflug FRA
    return_date: str = ""        # Abflug CHC
    target_arrival: str = ""     # angestrebte MEL-Ankunft
    stay_days: int = 0
    trip_type: str = "open_jaw"
    passengers: dict = field(default_factory=dict)
    currency: str = "EUR"
    total_results: int = 0
    filtered_results: int = 0
    offers: list[Offer] = field(default_factory=list)
