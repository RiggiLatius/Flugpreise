"""Dünner Client für die SerpApi Google-Flights-Engine.

Nutzt bewusst nur ``requests`` (keine zusätzliche SDK-Abhängigkeit).
Dokumentation: https://serpapi.com/google-flights-api
"""

from __future__ import annotations

import json
from pathlib import Path

import requests

SERPAPI_ENDPOINT = "https://serpapi.com/search.json"


class SerpApiError(RuntimeError):
    pass


def search(params: dict, *, timeout: int = 60) -> dict:
    """Führt eine SerpApi-Suche aus und gibt die JSON-Antwort zurück."""
    resp = requests.get(SERPAPI_ENDPOINT, params=params, timeout=timeout)
    if resp.status_code != 200:
        raise SerpApiError(
            f"SerpApi HTTP {resp.status_code}: {resp.text[:300]}"
        )
    data = resp.json()
    if data.get("error"):
        raise SerpApiError(f"SerpApi Fehler: {data['error']}")
    return data


def search_return(params: dict, departure_token: str, *, timeout: int = 60) -> dict:
    """Zweiter Schritt bei Round-Trip: Rückflüge zu einem Hinflug abrufen.

    Google Flights liefert bei Round-Trip zunächst die Hinflüge; die Rückflüge
    werden über den ``departure_token`` des gewählten Hinflugs nachgeladen.
    """
    p = dict(params)
    p["departure_token"] = departure_token
    return search(p, timeout=timeout)


def load_fixture(path: str | Path) -> dict:
    """Lädt eine gespeicherte SerpApi-Antwort (für Tests/Offline-Betrieb)."""
    return json.loads(Path(path).read_text(encoding="utf-8"))
