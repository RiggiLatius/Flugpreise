"""End-to-End-Test der Open-Jaw-Pipeline über die Fixture (ohne echten API-Call)."""

from pathlib import Path

from flugpreise import storage
from flugpreise.config import load_config
from flugpreise.tracker import run

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "open_jaw_sample.json"


def _run(tmp_path):
    cfg = load_config(ROOT / "config.yaml")
    conn = storage.connect(tmp_path / "test.db")
    storage.init_db(conn)
    results = run(cfg, conn, fixture=str(FIXTURE), no_jitter=True)
    return cfg, conn, results


def test_leg1_hub_and_arrival_window_filter(tmp_path):
    _, conn, results = _run(tmp_path)
    assert len(results) == 1
    r = results[0]
    # Kandidaten nach Filter: SQ(SIN, Ankunft 21.01.) und TG(BKK, 22.01.).
    # Emirates(DXB) faellt am Hub-Filter, Scoot(01.03.) am Ankunftsfenster,
    # der (billigere) SQ-Business-Flug am Kabinenfilter.
    assert r.total_results == 5
    assert r.filtered_results == 2


def test_return_leg_is_also_hub_filtered(tmp_path):
    _, conn, results = _run(tmp_path)
    offers = results[0].offers
    assert offers, "es sollten Angebote entstehen"
    # Guenstigster gueltiger Rueckflug via SIN = 3120; der billigere DXB-Rueckflug
    # (2980) muss trotz niedrigerem Preis ausgeschlossen sein.
    assert offers[0].price == 3120
    from flugpreise.filters import EXCLUDED_LAYOVER_AIRPORTS
    for o in offers:
        assert o.return_verified is True
        assert o.return_leg is not None
        for hub in o.outbound.layover_airports + o.return_leg.layover_airports:
            assert hub not in EXCLUDED_LAYOVER_AIRPORTS
    # Der 2980-EUR-Rueckflug ueber SYD/DXB darf nicht auftauchen (DXB = Naher Osten).
    assert all(o.price != 2980 for o in offers)
    # Angebote ohne Preisangabe (price fehlt in der API-Antwort) muessen
    # verworfen werden -- kein 0-EUR-Angebot darf durchrutschen.
    assert all(o.price and o.price > 0 for o in offers)
    # Der billigere (1500 EUR) Business-Class-Hinflug darf NICHT auftauchen --
    # nur reine Economy-Angebote zaehlen.
    assert all(o.price != 1500 for o in offers)
    for o in offers:
        for seg in o.outbound.segments + (o.return_leg.segments if o.return_leg else []):
            assert (seg.travel_class or "").lower().startswith("economy")


def test_storage_and_best_per_combo(tmp_path):
    _, conn, results = _run(tmp_path)
    rows = storage.latest_offers(conn)
    assert len(rows) == len(results[0].offers)
    assert rows[0]["return_verified"] == 1
    assert rows[0]["outbound_hubs"] in ("SIN", "BKK")

    best = storage.best_per_combo(conn)
    assert best
    assert best[0]["best_price"] == 3120
