"""Harter, nicht umgehbarer Zwischenstopp-Filter.

Regel (nicht verhandelbar, siehe Projektauftrag):
    Ein Angebot ist NUR gültig, wenn ausschließlich Singapur (SIN) oder
    Bangkok (BKK) als Umsteigeflughafen genutzt werden.
    Jedes Angebot mit einem anderen Zwischenstopp wird verworfen -- egal wie
    günstig es ist. Direktflüge über andere Hubs zählen nicht.

Dieser Filter wird bewusst PROGRAMMATISCH auf die Segment-/Layover-Daten der
API-Antwort angewendet und nicht als Suchparameter an die API übergeben
(die Google-Flights-/Amadeus-APIs bieten keinen "nur über Hub X"-Parameter).

Die erlaubten Flughäfen stehen absichtlich als Modul-Konstante hier im Code und
werden NICHT aus der Konfiguration gelesen, damit der Filter nicht über eine
config.yaml o.ä. aufgeweicht oder umgangen werden kann.
"""

from __future__ import annotations

from typing import Iterable

#: Ausschliesslich diese Flughäfen sind als Zwischenstopp zulässig.
#: Bewusst hart im Code -- nicht konfigurierbar.
ALLOWED_LAYOVER_AIRPORTS: "frozenset[str]" = frozenset({"SIN", "BKK"})


def layover_codes_from_flight(flight: dict) -> list[str]:
    """Extrahiert die IATA-Codes aller Zwischenstopps eines SerpApi-Flugobjekts.

    Bevorzugt das explizite ``layovers``-Feld der SerpApi-Antwort. Fehlt dieses,
    werden die Zwischenstopps aus den Segmenten rekonstruiert: jeder
    Ankunftsflughafen ausser dem letzten Segment ist ein Umsteigepunkt.
    """
    codes: list[str] = []

    layovers = flight.get("layovers")
    if layovers:
        for layover in layovers:
            code = (layover.get("id") or "").strip().upper()
            if code:
                codes.append(code)
        return codes

    # Fallback: Zwischenstopps aus den Segmenten ableiten.
    segments = flight.get("flights", []) or []
    for segment in segments[:-1]:
        arrival = segment.get("arrival_airport") or {}
        code = (arrival.get("id") or "").strip().upper()
        if code:
            codes.append(code)
    return codes


def is_allowed(layover_codes: Iterable[str], *, require_layover: bool = True) -> bool:
    """Prüft, ob eine Menge von Zwischenstopp-Codes zulässig ist.

    Zulässig genau dann, wenn *alle* Zwischenstopps in
    :data:`ALLOWED_LAYOVER_AIRPORTS` liegen.

    ``require_layover=True`` (Standard) verwirft zusätzlich Angebote ganz ohne
    Zwischenstopp (echte Direktflüge), da für FRA->MEL zwingend über SIN oder
    BKK umgestiegen werden soll.
    """
    codes = [c.strip().upper() for c in layover_codes if c and c.strip()]

    if require_layover and not codes:
        return False

    return all(code in ALLOWED_LAYOVER_AIRPORTS for code in codes)


def flight_passes(flight: dict, *, require_layover: bool = True) -> bool:
    """Wendet den harten Filter auf ein einzelnes SerpApi-Flugobjekt an."""
    return is_allowed(
        layover_codes_from_flight(flight),
        require_layover=require_layover,
    )


def filter_flights(
    flights: Iterable[dict], *, require_layover: bool = True
) -> list[dict]:
    """Gibt nur die Flüge zurück, die den SIN/BKK-Filter erfüllen."""
    return [f for f in flights if flight_passes(f, require_layover=require_layover)]
