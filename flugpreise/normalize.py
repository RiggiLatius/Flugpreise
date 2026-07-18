"""Normalisierung von Gepäck- und Tarifinformationen je Airline.

Google Flights (und damit SerpApi) liefert die Freigepäck-Menge nicht
zuverlässig strukturiert mit. Damit Preise je Airline dennoch *fair vergleichbar*
sind, pflegen wir hier eine Normalisierungstabelle für die Economy-Freigepäck-
Regeln der auf FRA->MEL via SIN/BKK relevanten Airlines.

Werte beziehen sich auf einen zahlenden Erwachsenen in Economy und dienen als
Orientierung -- bitte gelegentlich gegen die AGB der Airline prüfen. Für ein
Kleinkind (Infant on lap) gelten reduzierte/abweichende Regeln; siehe
``INFANT_NOTE``.
"""

from __future__ import annotations

# Freigepäck Economy je Airline (Orientierungswerte, Stand pflegebedürftig).
# Schlüssel = so wie der Airline-Name in der SerpApi-Antwort auftaucht.
BAGGAGE_TABLE: dict[str, dict[str, str]] = {
    "Singapore Airlines": {"checked": "2 x 23 kg (Stückkonzept)", "carry_on": "7 kg"},
    "Scoot":              {"checked": "kein Freigepäck (Zubuchung)", "carry_on": "10 kg"},
    "Thai Airways":       {"checked": "30 kg (Gewichtskonzept)", "carry_on": "7 kg"},
    "Thai Airasia":       {"checked": "kein Freigepäck (Zubuchung)", "carry_on": "7 kg"},
    "Lufthansa":          {"checked": "1 x 23 kg", "carry_on": "8 kg"},
    "Qantas":             {"checked": "1 x 30 kg", "carry_on": "7 kg"},
    "Emirates":           {"checked": "35 kg (Gewichtskonzept)", "carry_on": "7 kg"},
    "Swiss":              {"checked": "1 x 23 kg", "carry_on": "8 kg"},
    "Austrian":           {"checked": "1 x 23 kg", "carry_on": "8 kg"},
}

#: Fallback, wenn eine Airline nicht in der Tabelle steht.
DEFAULT_BAGGAGE = {"checked": "unbekannt -- bitte Tarif prüfen", "carry_on": "unbekannt"}

#: Hinweis zur Infant-Kategorie (1 Jahr, auf dem Schoss).
INFANT_NOTE = (
    "Kleinkind (Infant on lap): i.d.R. 0-10 kg Freigepäck bzw. keins, "
    "je nach Airline. Bitte separat prüfen."
)


def normalize_baggage(airline: str | None) -> dict[str, str]:
    """Liefert normalisierte Economy-Freigepäckangaben für eine Airline."""
    if not airline:
        return dict(DEFAULT_BAGGAGE)
    return dict(BAGGAGE_TABLE.get(airline.strip(), DEFAULT_BAGGAGE))


def normalize_baggage_for_airlines(airlines: list[str]) -> dict[str, str]:
    """Normalisiert Freigepäck für ein Angebot mit ggf. mehreren Airlines.

    Bei Codeshare/mehreren Airlines wird der *restriktivste* bekannte Wert
    genannt, indem alle vorkommenden Airlines aufgeführt werden.
    """
    if not airlines:
        return dict(DEFAULT_BAGGAGE)

    if len(set(airlines)) == 1:
        return normalize_baggage(airlines[0])

    checked = []
    carry = []
    for a in dict.fromkeys(airlines):  # Reihenfolge erhalten, dedupliziert
        b = normalize_baggage(a)
        checked.append(f"{a}: {b['checked']}")
        carry.append(f"{a}: {b['carry_on']}")
    return {"checked": " | ".join(checked), "carry_on": " | ".join(carry)}
