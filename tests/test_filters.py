"""Tests für den Zwischenstopp-Filter (Ausschluss Naher Osten/Istanbul + Visum)
und den Kabinenklassen-Filter."""

import json
from pathlib import Path

from flugpreise.filters import (
    EXCLUDED_LAYOVER_AIRPORTS,
    MIDDLE_EAST_ISTANBUL,
    VISA_TRANSIT_REQUIRED,
    cabin_ok,
    filter_flights,
    flight_passes,
    is_allowed,
    layover_codes_from_flight,
)

FIXTURE = Path(__file__).parent / "fixtures" / "serpapi_sample.json"


def _entries():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return (data.get("best_flights") or []) + (data.get("other_flights") or [])


def test_excluded_set_covers_me_istanbul_and_visa():
    # Naher Osten + Istanbul
    for code in ("DXB", "DOH", "AUH", "IST", "SAW", "TLV", "IKA"):
        assert code in EXCLUDED_LAYOVER_AIRPORTS
    # Visumpflichtige Transit-Hubs (deutscher Pass, Best-Effort)
    for code in ("JFK", "PEK", "PVG", "DEL", "SVO"):
        assert code in EXCLUDED_LAYOVER_AIRPORTS
    assert EXCLUDED_LAYOVER_AIRPORTS == MIDDLE_EAST_ISTANBUL | VISA_TRANSIT_REQUIRED


def test_other_hubs_now_allowed():
    # Jeder Hub ist erlaubt, sofern nicht ausgeschlossen -- auch bisher gesperrte.
    assert is_allowed(["SIN"]) is True
    assert is_allowed(["BKK"]) is True
    assert is_allowed(["HKG"]) is True   # Hongkong: erlaubt
    assert is_allowed(["KUL"]) is True   # Kuala Lumpur: erlaubt
    assert is_allowed(["SYD"]) is True   # Sydney: erlaubt


def test_excluded_hubs_rejected():
    assert is_allowed(["DXB"]) is False  # Middle East
    assert is_allowed(["DOH"]) is False  # Middle East
    assert is_allowed(["IST"]) is False  # Istanbul
    assert is_allowed(["DEL"]) is False  # Visum (Indien)
    assert is_allowed(["PVG"]) is False  # Visum (China)


def test_one_excluded_hub_rejects_whole_itinerary():
    assert is_allowed(["SIN", "BKK"]) is True
    assert is_allowed(["SIN", "DXB"]) is False  # ein ausgeschlossener reicht


def test_case_and_whitespace_insensitive():
    assert is_allowed([" sin "]) is True
    assert is_allowed(["dxb"]) is False


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
    assert layover_codes_from_flight(entry) == ["SIN"]


def test_cabin_filter_requires_all_segments_economy():
    all_eco = {"flights": [
        {"travel_class": "Economy"}, {"travel_class": "Economy"}]}
    mixed = {"flights": [
        {"travel_class": "Business Class"}, {"travel_class": "Economy"}]}
    assert cabin_ok(all_eco, "economy") is True
    assert cabin_ok(mixed, "economy") is False          # ein Business-Segment reicht
    assert cabin_ok(all_eco, "business") is False
    assert cabin_ok({"flights": []}, "economy") is False  # ohne Segmente ungueltig


def test_fixture_filtering_excludes_middle_east_hubs():
    entries = _entries()
    passing = filter_flights(entries)
    prices = sorted(e["price"] for e in passing)
    # DXB(1750) und DOH(1690) sind Naher Osten -> raus, trotz niedrigerem Preis.
    assert prices == [1620, 1980, 2090]
    for e in passing:
        assert flight_passes(e) is True
        for code in layover_codes_from_flight(e):
            assert code not in EXCLUDED_LAYOVER_AIRPORTS
