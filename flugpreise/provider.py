"""Abstraktion der Datenquelle: Live (SerpApi) oder Fixture (Offline/Test).

Zählt jeden echten API-Request gegen ein Monatsbudget, das in der DB persistiert
wird, damit der SerpApi-Free-Tier (100/Monat) nie überschritten wird -- egal wie
oft der Scheduler läuft.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from . import serpapi_client, storage


class BudgetExhausted(RuntimeError):
    pass


class Budget:
    """Monatliches Request-Budget, in der DB (state-Tabelle) gezählt."""

    def __init__(self, conn, monthly_max: int):
        self.conn = conn
        self.monthly_max = monthly_max
        self.month = datetime.now(timezone.utc).strftime("%Y-%m")

    @property
    def used(self) -> int:
        return storage.budget_used(self.conn, self.month)

    @property
    def remaining(self) -> int:
        return max(self.monthly_max - self.used, 0)

    def spend(self, n: int = 1) -> None:
        if self.remaining < n:
            raise BudgetExhausted(
                f"Monatsbudget erschöpft ({self.used}/{self.monthly_max} im {self.month})."
            )
        storage.budget_add(self.conn, self.month, n)


class LiveProvider:
    """Ruft SerpApi wirklich auf und bucht jeden Call gegen das Budget."""

    def __init__(self, api_key: str, budget: Budget):
        self.api_key = api_key
        self.budget = budget

    def search_leg1(self, params: dict) -> dict:
        self.budget.spend(1)
        return serpapi_client.search(params)

    def search_return(self, params: dict, departure_token: str) -> dict:
        self.budget.spend(1)
        return serpapi_client.search_return(params, departure_token)


class FixtureProvider:
    """Liefert gespeicherte Antworten für Offline-Betrieb/Tests.

    Fixture-Format (JSON):
        {
          "leg1": { ... SerpApi-Antwort für den Hinflug ... },
          "leg2_by_token": { "<departure_token>": { ... Rückflug-Antwort ... } }
        }
    Es wird -- unabhängig von der Datumskombi -- immer dieselbe Fixture geliefert
    (für deterministische Tests der Pipeline).
    """

    def __init__(self, path: str | Path):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        self._leg1 = data.get("leg1", data)  # erlaubt auch flache Fixtures
        self._leg2 = data.get("leg2_by_token", {})

    def search_leg1(self, params: dict) -> dict:
        return self._leg1

    def search_return(self, params: dict, departure_token: str) -> dict:
        return self._leg2.get(departure_token, {"best_flights": [], "other_flights": []})
