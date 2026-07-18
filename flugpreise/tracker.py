"""Haupt-Orchestrierung: Abfragen, Filtern, Top-N speichern, Report erzeugen.

Ablauf:
    1. Konfiguration + API-Key laden
    2. (optional) zufällige Wartezeit, um Abfragezeiten zu variieren
    3. SerpApi-Suche FRA->MEL (2 Erwachsene + 1 Infant, Economy)
    4. Harten SIN/BKK-Filter auf die Segmentdaten anwenden
    5. optional Rückflug-Leg verifizieren (Round-Trip)
    6. Top-3 der günstigsten gefilterten Angebote in SQLite schreiben
    7. Statische HTML-Seite (docs/index.html) neu erzeugen
"""

from __future__ import annotations

import argparse
import os
import random
import sys
import time

from . import serpapi_client, storage
from .config import Config, load_config
from .filters import filter_flights, is_allowed
from .models import Offer, QueryResult, Segment
from .parse import build_offer, collect_flight_entries
from .report import write_report


def _log(msg: str) -> None:
    print(f"[flugpreise] {msg}", flush=True)


def _apply_jitter(max_minutes: int) -> None:
    if max_minutes <= 0:
        return
    delay = random.randint(0, max_minutes * 60)
    _log(f"Variiere Abfragezeit: warte {delay} Sekunden (max {max_minutes} min).")
    time.sleep(delay)


def _verify_return_legs(
    offers: list[Offer], cfg: Config, base_params: dict
) -> list[Offer]:
    """Prüft für Round-Trip den Rückflug-Leg auf den SIN/BKK-Filter.

    Kostet je Angebot einen zusätzlichen SerpApi-Request -- daher nur für die
    (bereits nach Hinflug gefilterten) Top-Kandidaten und nur wenn aktiviert.
    Angebote, deren Rückflug keinen gültigen Hub hat, werden verworfen.
    """
    verified: list[Offer] = []
    for offer in offers:
        if not offer.booking_token:
            _log("  Kein departure_token -> Rückflug nicht prüfbar, verwerfe Angebot.")
            continue
        try:
            ret = serpapi_client.search_return(base_params, offer.booking_token)
        except serpapi_client.SerpApiError as exc:
            _log(f"  Rückflug-Abruf fehlgeschlagen: {exc}")
            continue

        ret_entries = collect_flight_entries(ret)
        # günstigsten gültigen Rückflug wählen
        valid = [
            build_offer(e, cfg.currency)
            for e in ret_entries
        ]
        valid = [
            o for o in valid
            if is_allowed(o.layover_airports, require_layover=cfg.require_layover)
        ]
        if not valid:
            _log("  Kein Rückflug über SIN/BKK -> Angebot verworfen.")
            continue
        best_ret = min(valid, key=lambda o: o.price or float("inf"))
        offer.return_segments = best_ret.segments
        offer.return_layover_airports = best_ret.layover_airports
        # Preis aus dem Round-Trip-Abschluss übernehmen (Gesamtpreis)
        if best_ret.price:
            offer.price = best_ret.price
        verified.append(offer)
    return verified


def run(cfg: Config, *, fixture: str | None = None, no_jitter: bool = False) -> QueryResult:
    api_key = os.environ.get("SERPAPI_KEY", "").strip()

    if fixture:
        _log(f"Offline-Modus: lade Fixture {fixture}")
        data = serpapi_client.load_fixture(fixture)
        base_params = {}
    else:
        if not api_key:
            raise SystemExit(
                "SERPAPI_KEY ist nicht gesetzt. Bitte als Umgebungsvariable/Secret "
                "bereitstellen oder mit --fixture offline testen."
            )
        if not no_jitter:
            _apply_jitter(cfg.max_jitter_minutes)
        base_params = cfg.serpapi_params(api_key)
        safe = {k: v for k, v in base_params.items() if k != "api_key"}
        _log(f"SerpApi-Abfrage: {safe}")
        data = serpapi_client.search(base_params)

    entries = collect_flight_entries(data)
    _log(f"{len(entries)} Angebote von der API erhalten.")

    # --- HARTER FILTER: nur Zwischenstopp SIN oder BKK -------------------
    passing = filter_flights(entries, require_layover=cfg.require_layover)
    _log(f"{len(passing)} Angebote erfüllen den SIN/BKK-Filter.")

    offers = [build_offer(e, cfg.currency) for e in passing]
    offers.sort(key=lambda o: o.price or float("inf"))

    # Top-N vorauswählen (spart Requests bei der Rückflug-Prüfung)
    top = offers[: cfg.top_n]

    if cfg.trip_type == "round_trip" and cfg.verify_return_leg and not fixture:
        _log("Verifiziere Rückflug-Leg der Top-Kandidaten ...")
        top = _verify_return_legs(top, cfg, base_params)
        top.sort(key=lambda o: o.price or float("inf"))
        top = top[: cfg.top_n]

    result = QueryResult(
        route=cfg.route,
        outbound_date=cfg.outbound_date,
        return_date=cfg.return_date,
        trip_type=cfg.trip_type,
        passengers=cfg.passengers,
        currency=cfg.currency,
        total_results=len(entries),
        filtered_results=len(passing),
        offers=top,
    )

    for i, o in enumerate(top, 1):
        _log(f"  #{i}: {o.price} {o.currency} | {o.fare_summary()}")

    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Flugpreis-Tracker FRA->MEL")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument(
        "--fixture",
        help="Statt der API eine gespeicherte SerpApi-JSON-Antwort verwenden.",
    )
    parser.add_argument(
        "--no-jitter",
        action="store_true",
        help="Zufällige Wartezeit vor der Abfrage überspringen.",
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="Kein HTML-Report erzeugen.",
    )
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    result = run(cfg, fixture=args.fixture, no_jitter=args.no_jitter)

    conn = storage.connect(cfg.db_path)
    storage.init_db(conn)
    query_id = storage.save_query(conn, result)
    _log(f"Abfrage #{query_id} mit {len(result.offers)} Angeboten gespeichert.")

    if not args.no_report:
        write_report(conn, cfg)
        _log(f"Report aktualisiert: {cfg.output_html}")

    conn.close()

    if result.filtered_results == 0:
        _log("WARNUNG: Kein Angebot erfüllte den SIN/BKK-Filter.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
