"""Zwischenstopp-Filter (Ausschluss-Logik).

Regel (aktualisiert auf Wunsch des Nutzers):
    Grundsätzlich sind ALLE Umsteigeflughäfen erlaubt -- auch wenn sie günstiger
    sind -- MIT AUSNAHME von:
      1. der Region Naher Osten (Middle East) sowie Istanbul, und
      2. Flughäfen, für die (deutscher Pass) ein Transit-/Visum nötig ist.

    Ein Angebot wird verworfen, sobald AUCH NUR EIN Zwischenstopp in einer der
    beiden Ausschlusslisten liegt.

Der Filter wird bewusst PROGRAMMATISCH auf die Segment-/Layover-Daten der
API-Antwort angewendet (nicht als Suchparameter).

WICHTIG zur Visum-Liste: Ob für einen Transit ein Visum nötig ist, lässt sich
NICHT zuverlässig aus den Flugdaten ableiten. ``VISA_TRANSIT_REQUIRED`` ist
daher eine gepflegte Best-Effort-Liste (deutscher Reisepass) und sollte im
Zweifel selbst geprüft/angepasst werden.
"""

from __future__ import annotations

from typing import Iterable

#: Naher Osten + Istanbul -- als Zwischenstopp ausgeschlossen.
MIDDLE_EAST_ISTANBUL: "frozenset[str]" = frozenset({
    # Golfregion / Arabische Halbinsel
    "DXB", "DWC", "AUH", "SHJ", "RKT", "DOH", "RUH", "JED", "MED", "DMM",
    "KWI", "BAH", "MCT", "SLL",
    # Levante / weiterer Naher Osten
    "AMM", "BEY", "DAM", "TLV", "BGW", "BSR", "EBL", "ISU",
    # Iran
    "IKA", "THR", "MHD", "SYZ",
    # Türkei (Istanbul)
    "IST", "SAW",
    # Ägypten (MENA-Region)
    "CAI",
})

#: Flughäfen/Länder, für die (deutscher Pass) i.d.R. ein Transit-/Visum nötig
#: ist bzw. dessen Notwendigkeit unklar ist -> ausgeschlossen.
#: BEST-EFFORT, bitte selbst verifizieren und bei Bedarf anpassen.
VISA_TRANSIT_REQUIRED: "frozenset[str]" = frozenset({
    # USA (ESTA/Visum auch für reinen Transit)
    "JFK", "EWR", "LAX", "SFO", "ORD", "IAD", "DFW", "ATL", "SEA", "BOS", "MIA", "IAH",
    # Festland-China (visafreier Transit nur bedingt/zeitlich begrenzt)
    "PEK", "PKX", "PVG", "SHA", "CAN", "SZX", "CTU", "CKG", "XIY", "HGH", "WUH",
    "KMG", "NKG",
    # Indien (kein regulärer visafreier internationaler Transit)
    "DEL", "BOM", "MAA", "BLR", "HYD", "CCU", "COK", "AMD",
    # Russland
    "SVO", "DME", "VKO", "LED",
})

#: Vereinigte Ausschlussmenge -- ein Zwischenstopp hier => Angebot verworfen.
EXCLUDED_LAYOVER_AIRPORTS: "frozenset[str]" = MIDDLE_EAST_ISTANBUL | VISA_TRANSIT_REQUIRED


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

    Zulässig genau dann, wenn *kein* Zwischenstopp in
    :data:`EXCLUDED_LAYOVER_AIRPORTS` liegt (Naher Osten + Istanbul sowie
    visumpflichtige Transit-Flughäfen).

    ``require_layover=True`` (Standard) verwirft zusätzlich Angebote ganz ohne
    Zwischenstopp (echte Direktflüge FRA->MEL existieren praktisch nicht).
    """
    codes = [c.strip().upper() for c in layover_codes if c and c.strip()]

    if require_layover and not codes:
        return False

    return all(code not in EXCLUDED_LAYOVER_AIRPORTS for code in codes)


def flight_passes(flight: dict, *, require_layover: bool = True) -> bool:
    """Wendet den Zwischenstopp-Filter auf ein einzelnes SerpApi-Flugobjekt an."""
    return is_allowed(
        layover_codes_from_flight(flight),
        require_layover=require_layover,
    )


# --------------------------------------------------------------------------
# Harter Kabinenklassen-Filter
#
# SerpApi/Google-Flights hält sich bei Multi-City nicht immer an travel_class
# und mischt teurere Segmente (z. B. Business) in ein Angebot. Damit Preise
# fair vergleichbar bleiben (Projektauftrag: nur Economy), wird jede
# Kabinenklasse programmatisch nachgeprüft: ALLE Segmente eines Angebots müssen
# der gewünschten Klasse entsprechen, sonst wird es verworfen.
# --------------------------------------------------------------------------

_CABIN_LABEL = {
    "economy": "economy",
    "premium_economy": "premium economy",
    "business": "business",
    "first": "first",
}


def normalize_cabin(value: str | None) -> str:
    """Normalisiert eine Kabinenklassen-Bezeichnung ('Business Class' -> 'business')."""
    return (value or "").strip().lower().replace(" class", "")


def cabin_ok(flight: dict, expected_travel_class: str) -> bool:
    """True, wenn ALLE Segmente des Angebots in der erwarteten Kabinenklasse sind."""
    expected = _CABIN_LABEL.get(expected_travel_class, "economy")
    segments = flight.get("flights", []) or []
    if not segments:
        return False
    return all(normalize_cabin(s.get("travel_class")) == expected for s in segments)


def filter_flights(
    flights: Iterable[dict], *, require_layover: bool = True
) -> list[dict]:
    """Gibt nur die Flüge zurück, die den SIN/BKK-Filter erfüllen."""
    return [f for f in flights if flight_passes(f, require_layover=require_layover)]
