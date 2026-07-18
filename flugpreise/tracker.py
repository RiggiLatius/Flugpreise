"""Haupt-Orchestrierung (Open-Jaw, flexibles Datums-Raster, budgetsicher).

Ablauf je Lauf:
    1. Konfiguration + API-Key laden, Budget-Wächter initialisieren
    2. Datums-Raster bilden; per rotierendem Cursor die nächsten N Kombinationen wählen
    3. je Kombination: Multi-City-Suche FRA->MEL ... CHC->FRA
       - HARTER SIN/BKK-Filter auf den Hinflug (Leg 1)
       - Post-Filter: MEL-Ankunft muss im Fenster liegen
       - optional Rückflug (Leg 2, CHC->FRA) via departure_token nachladen und
         ebenfalls hart auf SIN/BKK filtern
       - Top-N günstigste vollständige Angebote je Kombination speichern
    4. Cursor + Monatsbudget fortschreiben, HTML-Report neu erzeugen
"""

from __future__ import annotations

import argparse
import os
import random
import sys
import time

from . import storage
from .config import Config, load_config
from .dates import date_in_window
from .filters import flight_passes
from .grid import DateCombo
from .models import Offer, QueryResult
from .parse import (
    collect_flight_entries,
    entry_price,
    entry_token,
    leg_arrival_datetime,
    leg_from_entry,
)
from .provider import Budget, BudgetExhausted, FixtureProvider, LiveProvider
from .report import write_report


def _log(msg: str) -> None:
    print(f"[flugpreise] {msg}", flush=True)


def _apply_jitter(max_minutes: int) -> None:
    if max_minutes <= 0:
        return
    delay = random.randint(0, max_minutes * 60)
    _log(f"Variiere Abfragezeit: warte {delay} s (max {max_minutes} min).")
    time.sleep(delay)


def _arrival_in_window(entry: dict, cfg: Config) -> bool:
    dt = leg_arrival_datetime(entry)
    if not dt:
        return False
    return date_in_window(dt.date(), cfg.arrival_start, cfg.arrival_end)


def process_combo(cfg: Config, provider, combo: DateCombo, api_key: str) -> QueryResult:
    """Verarbeitet eine einzelne Datumskombination und liefert deren Top-N."""
    params = cfg.multi_city_params(combo, api_key)
    data1 = provider.search_leg1(params)
    entries = collect_flight_entries(data1)

    # --- HARTER FILTER Leg 1 (FRA->MEL): nur SIN/BKK ---------------------
    hub_ok = [e for e in entries if flight_passes(e, require_layover=cfg.require_layover)]
    # --- Post-Filter: MEL-Ankunft im Fenster -----------------------------
    candidates = [e for e in hub_ok if _arrival_in_window(e, cfg)]
    candidates.sort(key=entry_price)

    offers: list[Offer] = []

    if cfg.verify_return_leg:
        # Rückflug (Leg 2, CHC->FRA) für MEHRERE Hinflug-Kandidaten nachladen und
        # ebenfalls auf SIN/BKK filtern. Wichtig: NICHT nach dem ersten Treffer
        # abbrechen -- der billigste Hinflug (dessen Gesamtpreis einen evtl.
        # Nicht-SIN/BKK-Rückflug unterstellt) ergibt nach dem SIN/BKK-Zwang nicht
        # zwingend den günstigsten Gesamtpreis. Wir sammeln daher alle Varianten
        # und wählen unten global den günstigsten.
        for cand in candidates[: cfg.drill_max_candidates]:
            token = entry_token(cand)
            if not token:
                continue
            data2 = provider.search_return(params, token)
            ret_entries = collect_flight_entries(data2)
            ret_ok = [
                e for e in ret_entries
                if flight_passes(e, require_layover=cfg.require_layover)
                and entry_price(e) > 0  # Angebote ohne Preisangabe verwerfen
            ]
            if not ret_ok:
                _log("    Kein (bepreister) SIN/BKK-Rückflug für diesen Hinflug-Kandidaten.")
                continue
            ret_ok.sort(key=entry_price)
            out_leg = leg_from_entry(cand)
            for r in ret_ok[: cfg.top_n]:
                ret_leg = leg_from_entry(r)
                offers.append(
                    Offer(
                        price=entry_price(r),  # Gesamtpreis der Open-Jaw-Kombination
                        currency=cfg.currency,
                        outbound=out_leg,
                        return_leg=ret_leg,
                        total_duration_min=out_leg.duration_min,
                        booking_token=entry_token(r),
                        return_verified=True,
                        carbon_emissions_g=(r.get("carbon_emissions") or {}).get("this_flight"),
                    )
                )
    else:
        # Ohne Rückflug-Verifikation: nur Hinflug-basierte Angebote (Gesamtpreis-Schätzung).
        priced = [c for c in candidates if entry_price(c) > 0]
        for e in priced[: cfg.top_n]:
            out_leg = leg_from_entry(e)
            offers.append(
                Offer(
                    price=entry_price(e),
                    currency=cfg.currency,
                    outbound=out_leg,
                    return_leg=None,
                    total_duration_min=out_leg.duration_min,
                    booking_token=entry_token(e),
                    return_verified=False,
                    carbon_emissions_g=(e.get("carbon_emissions") or {}).get("this_flight"),
                )
            )

    # Sicherheitsnetz: Angebote ohne gültigen Preis (z. B. fehlendes price-Feld
    # in der API-Antwort) verwerfen, damit sie die Top-N/Best-Preis-Auswertung
    # nicht verfälschen.
    offers = [o for o in offers if o.price and o.price > 0]
    offers.sort(key=lambda o: o.price)
    offers = offers[: cfg.top_n]

    return QueryResult(
        route=cfg.route,
        outbound_date=combo.outbound_date.isoformat(),
        return_date=combo.return_date.isoformat(),
        target_arrival=combo.target_arrival.isoformat(),
        stay_days=combo.stay_days,
        trip_type=cfg.mode,
        passengers=cfg.passengers,
        currency=cfg.currency,
        total_results=len(entries),
        filtered_results=len(candidates),
        offers=offers,
    )


def run(cfg: Config, conn, *, fixture: str | None = None, no_jitter: bool = False) -> list[QueryResult]:
    grid = cfg.grid()
    n = len(grid)
    if n == 0:
        _log("Leeres Datums-Raster -- nichts zu tun.")
        return []

    if fixture:
        _log(f"Offline-Modus: Fixture {fixture} (verarbeite 1 Kombination).")
        provider = FixtureProvider(fixture)
        combos = grid[:1]
        cursor = 0
        api_key = "FIXTURE"
    else:
        api_key = os.environ.get("SERPAPI_KEY", "").strip()
        if not api_key:
            raise SystemExit(
                "SERPAPI_KEY ist nicht gesetzt. Als Secret/Umgebungsvariable bereitstellen "
                "oder mit --fixture offline testen."
            )
        budget = Budget(conn, cfg.monthly_max_requests)
        _log(f"Monatsbudget: {budget.used}/{budget.monthly_max} verbraucht.")
        if budget.remaining <= 0:
            _log("Monatsbudget erschöpft -- Lauf wird übersprungen.")
            return []
        if not no_jitter:
            _apply_jitter(cfg.raw.get("schedule", {}).get("max_jitter_minutes", 20))
        provider = LiveProvider(api_key, budget)
        cursor = storage.get_cursor(conn, cfg.grid_signature())
        combos = [grid[(cursor + i) % n] for i in range(cfg.searches_per_run)]

    results: list[QueryResult] = []
    processed = 0
    for combo in combos:
        _log(
            f"Kombi: Abflug {combo.outbound_date} | Ziel-Ankunft {combo.target_arrival} "
            f"| Aufenthalt {combo.stay_days} T | Rückflug CHC {combo.return_date}"
        )
        try:
            result = process_combo(cfg, provider, combo, api_key)
        except BudgetExhausted as exc:
            _log(f"{exc} -- Lauf wird hier beendet.")
            break
        results.append(result)
        processed += 1
        storage.save_query(conn, result)
        _log(f"  {result.filtered_results} gefiltert, {len(result.offers)} Angebote gespeichert.")
        for i, o in enumerate(result.offers, 1):
            verified = "Rückflug SIN/BKK ✓" if o.return_verified else "nur Hinflug gefiltert"
            _log(f"    #{i}: {o.price:.0f} {o.currency} | {o.airline_label} | {verified}")

    if not fixture and processed:
        storage.set_cursor(conn, (cursor + processed) % n)

    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Flugpreis-Tracker Open-Jaw FRA-MEL / CHC-FRA")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--fixture", help="Statt der API eine gespeicherte Antwort verwenden.")
    parser.add_argument("--no-jitter", action="store_true", help="Zufällige Wartezeit überspringen.")
    parser.add_argument("--no-report", action="store_true", help="Kein HTML-Report erzeugen.")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    conn = storage.connect(cfg.db_path)
    storage.init_db(conn)

    results = run(cfg, conn, fixture=args.fixture, no_jitter=args.no_jitter)

    if not args.no_report:
        write_report(conn, cfg)
        _log(f"Report aktualisiert: {cfg.output_html}")

    conn.close()

    total_offers = sum(len(r.offers) for r in results)
    if results and total_offers == 0:
        _log("WARNUNG: In diesem Lauf erfüllte keine Kombination den SIN/BKK-Filter.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
