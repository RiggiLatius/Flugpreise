"""Erzeugung des Datums-Rasters für die flexible Open-Jaw-Suche.

Aus dem Ankunftsfenster in Melbourne (MEL) und den gewünschten
Aufenthaltslängen wird eine Liste konkreter Datumskombinationen gebildet:

    Hinflug  FRA -> MEL  am  (Ziel-Ankunft - outbound_offset_days)
    Rückflug CHC -> FRA  am  (Ziel-Ankunft + stay_days)

Die tatsächliche MEL-Ankunft wird später zusätzlich per Post-Filter gegen das
Fenster geprüft (der Offset ist nur eine Startannahme für das Abflugdatum).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, timedelta

from .dates import daterange


@dataclass(frozen=True)
class DateCombo:
    outbound_date: date        # Abflug FRA -> MEL
    return_date: date          # Abflug CHC -> FRA
    target_arrival: date       # angestrebte Ankunft in MEL
    stay_days: int

    def key(self) -> str:
        return f"{self.outbound_date.isoformat()}|{self.return_date.isoformat()}|{self.stay_days}"


def build_grid(
    *,
    arrival_start: date,
    arrival_end: date,
    stay_days: list[int],
    arrival_step_days: int,
    outbound_offset_days: int,
) -> list[DateCombo]:
    """Baut die deterministisch sortierte Liste aller Datumskombinationen."""
    combos: list[DateCombo] = []
    arrivals = daterange(arrival_start, arrival_end, arrival_step_days)
    for arrival in arrivals:
        outbound = arrival - timedelta(days=outbound_offset_days)
        for stay in sorted(set(stay_days)):
            ret = arrival + timedelta(days=stay)
            combos.append(
                DateCombo(
                    outbound_date=outbound,
                    return_date=ret,
                    target_arrival=arrival,
                    stay_days=stay,
                )
            )
    # Stabile Reihenfolge (Ankunft, dann Aufenthaltsdauer)
    combos.sort(key=lambda c: (c.target_arrival, c.stay_days))
    return combos


def grid_signature(combos: list[DateCombo]) -> str:
    """Kurzer Hash über das Raster -- dient zum Invalidieren des Rotations-Cursors,
    falls sich die Konfiguration (und damit das Raster) ändert."""
    joined = ";".join(c.key() for c in combos)
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()[:12]
