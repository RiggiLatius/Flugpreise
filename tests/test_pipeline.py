"""End-to-End-Test über die Fixture (ohne echten API-Call)."""

from pathlib import Path

from flugpreise import storage
from flugpreise.config import load_config
from flugpreise.tracker import run

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "serpapi_sample.json"


def test_run_selects_top3_filtered(tmp_path):
    cfg = load_config(ROOT / "config.yaml")
    result = run(cfg, fixture=str(FIXTURE), no_jitter=True)

    assert result.total_results == 5
    assert result.filtered_results == 3
    assert len(result.offers) == 3

    # Günstigstes gefiltertes Angebot zuerst (Scoot via SIN, 1620).
    assert result.offers[0].price == 1620
    assert result.offers[0].layover_airports == ["SIN"]

    # Alle gespeicherten Angebote steigen nur über SIN/BKK um.
    for o in result.offers:
        assert set(o.layover_airports).issubset({"SIN", "BKK"})
        assert o.stops == 1
        assert o.baggage_checked  # normalisierte Gepäckangabe vorhanden


def test_storage_roundtrip(tmp_path):
    cfg = load_config(ROOT / "config.yaml")
    result = run(cfg, fixture=str(FIXTURE), no_jitter=True)

    db = tmp_path / "test.db"
    conn = storage.connect(db)
    storage.init_db(conn)
    qid = storage.save_query(conn, result)
    assert qid == 1

    rows = storage.latest_offers(conn)
    assert len(rows) == 3
    assert rows[0]["rank"] == 1
    assert rows[0]["layover_airports"] in ("SIN", "BKK")
    conn.close()
