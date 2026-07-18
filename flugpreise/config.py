"""Laden und Aufbereiten der Konfiguration."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# Mapping Kabinenklasse -> SerpApi/Google-Flights travel_class-Code.
TRAVEL_CLASS_CODES = {
    "economy": 1,
    "premium_economy": 2,
    "business": 3,
    "first": 4,
}

# Mapping Trip-Typ -> SerpApi type-Code.
TRIP_TYPE_CODES = {
    "round_trip": 1,
    "one_way": 2,
}


@dataclass
class Config:
    raw: dict

    departure_id: str
    arrival_id: str
    trip_type: str
    outbound_date: str
    return_date: str | None
    passengers: dict
    travel_class: str
    currency: str
    hl: str
    gl: str
    deep_search: bool
    require_layover: bool
    verify_return_leg: bool
    max_jitter_minutes: int
    db_path: str
    top_n: int
    output_html: str

    @property
    def route(self) -> str:
        return f"{self.departure_id}-{self.arrival_id}"

    @property
    def travel_class_code(self) -> int:
        return TRAVEL_CLASS_CODES[self.travel_class]

    @property
    def trip_type_code(self) -> int:
        return TRIP_TYPE_CODES[self.trip_type]

    def serpapi_params(self, api_key: str) -> dict:
        """Baut die SerpApi-Parameter (ohne api_key-Ausgabe im Log)."""
        params = {
            "engine": "google_flights",
            "departure_id": self.departure_id,
            "arrival_id": self.arrival_id,
            "outbound_date": self.outbound_date,
            "type": self.trip_type_code,
            "travel_class": self.travel_class_code,
            "adults": self.passengers.get("adults", 1),
            "children": self.passengers.get("children", 0),
            "infants_in_seat": self.passengers.get("infants_in_seat", 0),
            "infants_on_lap": self.passengers.get("infants_on_lap", 0),
            "currency": self.currency,
            "hl": self.hl,
            "gl": self.gl,
            "deep_search": self.deep_search,
            "api_key": api_key,
        }
        if self.trip_type == "round_trip":
            if not self.return_date:
                raise ValueError("round_trip benötigt ein return_date in der Config.")
            params["return_date"] = self.return_date
        return params


def load_config(path: str | os.PathLike = "config.yaml") -> Config:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}

    route = data.get("route", {})
    trip = data.get("trip", {})
    passengers = data.get("passengers", {})
    cabin = data.get("cabin", {})
    search = data.get("search", {})
    flt = data.get("filter", {})
    schedule = data.get("schedule", {})
    storage = data.get("storage", {})
    report = data.get("report", {})

    travel_class = (cabin.get("travel_class") or "economy").lower()
    if travel_class not in TRAVEL_CLASS_CODES:
        raise ValueError(f"Unbekannte Kabinenklasse: {travel_class}")

    trip_type = (trip.get("type") or "round_trip").lower()
    if trip_type not in TRIP_TYPE_CODES:
        raise ValueError(f"Unbekannter Trip-Typ: {trip_type}")

    return Config(
        raw=data,
        departure_id=(route.get("departure_id") or "FRA").upper(),
        arrival_id=(route.get("arrival_id") or "MEL").upper(),
        trip_type=trip_type,
        outbound_date=str(trip.get("outbound_date") or ""),
        return_date=(str(trip["return_date"]) if trip.get("return_date") else None),
        passengers={
            "adults": int(passengers.get("adults", 2)),
            "children": int(passengers.get("children", 0)),
            "infants_in_seat": int(passengers.get("infants_in_seat", 0)),
            "infants_on_lap": int(passengers.get("infants_on_lap", 1)),
        },
        travel_class=travel_class,
        currency=(search.get("currency") or "EUR").upper(),
        hl=search.get("hl") or "de",
        gl=search.get("gl") or "de",
        deep_search=bool(search.get("deep_search", False)),
        require_layover=bool(flt.get("require_layover", True)),
        verify_return_leg=bool(flt.get("verify_return_leg", False)),
        max_jitter_minutes=int(schedule.get("max_jitter_minutes", 20)),
        db_path=storage.get("db_path") or "data/flugpreise.db",
        top_n=int(report.get("top_n", 3)),
        output_html=report.get("output_html") or "docs/index.html",
    )
