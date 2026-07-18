"""Tests für den harten SIN/BKK-Filter -- die zentrale, nicht verhandelbare Regel."""

import json
from pathlib import Path

from flugpreise.filters import (
    ALLOWED_LAYOVER_AIRPORTS,
    filter_flights,
    flight_passes,
    is_allowed,
    layover_codes_from_flight,
)

FIXTURE = Path(__file__).parent / "fixtures" / "serpapi_sample.json"


def _entries():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return (data.get("best_flights") or []) + (data.get("other_flights") or [])


def test_allowed_set_is_exactly_sin_bkk():
    assert ALLOWED_LAYOVER_AIRPORTS == frozenset({"SIN", "BKK"})


def test_is_allowed_single_hub():
    assert is_allowed(["SIN"]) is True
    assert is_allowed(["BKK"]) is True
    assert is_allowed(["DXB"]) is False
    assert is_allowed(["DOH"]) is False


def test_is_allowed_multi_hub_all_must_pass():
    assert is_allowed(["SIN", "BKK"]) is True
    assert is_allowed(["SIN", "DXB"]) is False  # ein unzulässiger reicht zum Verwerfen


def test_case_and_whitespace_insensitive():
    assert is_allowed([" sin "]) is True
    assert is_allowed(["bkk"]) is True


def test_direct_flight_rejected_when_require_layover():
    assert is_allowed([], require_layover=True) is False
    assert is_allowed([], require_layover=False) is True


def test_layover_codes_from_flight_uses_layovers_field():
    entry = {"layovers": [{"id": "SIN"}, {"id": "BKK"}]}
    assert layover_codes_from_flight(entry) == ["SIN", "BKK"]


def test_layover_codes_fallback_from_segments():
    entry = {
        "flights": [
            {"arrival_airport": {"id": "SIN"}},
            {"arrival_airport": {"id": "MEL"}},
        ]
    }
    # letzter Ankunftsflughafen (Ziel) zählt nicht als Zwischenstopp
    assert layover_codes_from_flight(entry) == ["SIN"]


def test_fixture_filtering_excludes_cheaper_wrong_hubs():
    entries = _entries()
    passing = filter_flights(entries)
    prices = sorted(e["price"] for e in passing)
    # Nur SIN/BKK-Angebote bleiben übrig: Scoot(1620), SQ(1980), TG(2090).
    assert prices == [1620, 1980, 2090]
    # Die günstigeren DOH(1690) und DXB(1750) sind trotz niedrigerem Preis raus.
    for e in passing:
        assert flight_passes(e) is True
        for code in layover_codes_from_flight(e):
            assert code in ALLOWED_LAYOVER_AIRPORTS
