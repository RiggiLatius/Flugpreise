"""Laden und Aufbereiten der Konfiguration (Open-Jaw-Modus)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

from .dates import parse_date
from .grid import DateCombo, build_grid, grid_signature

# Mapping Kabinenklasse -> SerpApi/Google-Flights travel_class-Code.
TRAVEL_CLASS_CODES = {
    "economy": 1,
    "premium_economy": 2,
    "business": 3,
    "first": 4,
}


@dataclass
class Config:
    raw: dict

    mode: str
    outbound_from: str
    outbound_to: str
    return_from: str
    return_to: str

    arrival_start: date
    arrival_end: date
    stay_days: list[int]
    arrival_step_days: int
    outbound_offset_days: int

    passengers: dict
    travel_class: str
    currency: str
    hl: str
    gl: str
    deep_search: bool

    require_layover: bool
    verify_return_leg: bool
    drill_max_candidates: int

    monthly_max_requests: int
    searches_per_run: int

    db_path: str
    top_n: int
    output_html: str

    # ---- abgeleitete Werte -------------------------------------------------

    @property
    def route(self) -> str:
        return f"{self.outbound_from}-{self.outbound_to}...{self.return_from}-{self.return_to}"

    @property
    def travel_class_code(self) -> int:
        return TRAVEL_CLASS_CODES[self.travel_class]

    def grid(self) -> list[DateCombo]:
        return build_grid(
            arrival_start=self.arrival_start,
            arrival_end=self.arrival_end,
            stay_days=self.stay_days,
            arrival_step_days=self.arrival_step_days,
            outbound_offset_days=self.outbound_offset_days,
        )

    def grid_signature(self) -> str:
        return grid_signature(self.grid())

    def _passenger_params(self) -> dict:
        return {
            "adults": self.passengers.get("adults", 1),
            "children": self.passengers.get("children", 0),
            "infants_in_seat": self.passengers.get("infants_in_seat", 0),
            "infants_on_lap": self.passengers.get("infants_on_lap", 0),
        }

    def multi_city_params(self, combo: DateCombo, api_key: str) -> dict:
        """SerpApi-Parameter für die Multi-City-Open-Jaw-Suche einer Datumskombi."""
        import json

        multi_city = [
            {
                "departure_id": self.outbound_from,
                "arrival_id": self.outbound_to,
                "date": combo.outbound_date.isoformat(),
            },
            {
                "departure_id": self.return_from,
                "arrival_id": self.return_to,
                "date": combo.return_date.isoformat(),
            },
        ]
        params = {
            "engine": "google_flights",
            "type": 3,  # Multi-City
            "multi_city_json": json.dumps(multi_city),
            "travel_class": self.travel_class_code,
            "currency": self.currency,
            "hl": self.hl,
            "gl": self.gl,
            "deep_search": self.deep_search,
            "api_key": api_key,
        }
        params.update(self._passenger_params())
        return params


def load_config(path: str | os.PathLike = "config.yaml") -> Config:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}

    outbound = data.get("outbound", {})
    ret = data.get("return", {})
    window = data.get("arrival_window", {})
    grid_cfg = data.get("grid", {})
    passengers = data.get("passengers", {})
    cabin = data.get("cabin", {})
    search = data.get("search", {})
    flt = data.get("filter", {})
    budget = data.get("budget", {})
    storage = data.get("storage", {})
    report = data.get("report", {})

    travel_class = (cabin.get("travel_class") or "economy").lower()
    if travel_class not in TRAVEL_CLASS_CODES:
        raise ValueError(f"Unbekannte Kabinenklasse: {travel_class}")

    stay_days = [int(x) for x in (data.get("stay_days") or [21])]

    return Config(
        raw=data,
        mode=(data.get("mode") or "open_jaw").lower(),
        outbound_from=(outbound.get("from") or "FRA").upper(),
        outbound_to=(outbound.get("to") or "MEL").upper(),
        return_from=(ret.get("from") or "CHC").upper(),
        return_to=(ret.get("to") or "FRA").upper(),
        arrival_start=parse_date(str(window.get("start"))),
        arrival_end=parse_date(str(window.get("end"))),
        stay_days=stay_days,
        arrival_step_days=int(grid_cfg.get("arrival_step_days", 4)),
        outbound_offset_days=int(grid_cfg.get("outbound_offset_days", 1)),
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
        verify_return_leg=bool(flt.get("verify_return_leg", True)),
        drill_max_candidates=int(flt.get("drill_max_candidates", 2)),
        monthly_max_requests=int(budget.get("monthly_max_requests", 95)),
        searches_per_run=int(budget.get("searches_per_run", 2)),
        db_path=storage.get("db_path") or "data/flugpreise.db",
        top_n=int(report.get("top_n", 3)),
        output_html=report.get("output_html") or "docs/index.html",
    )
