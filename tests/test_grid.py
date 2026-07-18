"""Tests für Datums-Raster und Budget-/Cursor-Zustand."""

from datetime import date

from flugpreise import storage
from flugpreise.dates import daterange, date_in_window, parse_serpapi_datetime
from flugpreise.grid import build_grid, grid_signature


def test_daterange_includes_end():
    r = daterange(date(2027, 1, 20), date(2027, 2, 7), 4)
    assert r[0] == date(2027, 1, 20)
    assert r[-1] == date(2027, 2, 7)  # Enddatum immer enthalten
    assert all(r[i] < r[i + 1] for i in range(len(r) - 1))


def test_arrival_window():
    start, end = date(2027, 1, 20), date(2027, 2, 7)
    assert date_in_window(date(2027, 1, 21), start, end) is True
    assert date_in_window(date(2027, 3, 1), start, end) is False
    assert date_in_window(date(2027, 1, 19), start, end) is False


def test_parse_serpapi_datetime():
    dt = parse_serpapi_datetime("2027-01-21 06:35")
    assert dt is not None and dt.date() == date(2027, 1, 21)
    assert parse_serpapi_datetime("") is None


def test_build_grid_size_and_dates():
    combos = build_grid(
        arrival_start=date(2027, 1, 20),
        arrival_end=date(2027, 2, 7),
        stay_days=[18, 21, 25],
        arrival_step_days=4,
        outbound_offset_days=1,
    )
    arrivals = sorted({c.target_arrival for c in combos})
    # 20,24,28,Feb1,5 + Enddatum 7 -> 6 Ankunftstage x 3 Aufenthalte = 18 Kombis
    assert len(arrivals) == 6
    assert len(combos) == 18
    c = combos[0]
    # Abflug = Ankunft - offset; Rueckflug = Ankunft + stay
    assert (c.target_arrival - c.outbound_date).days == 1
    assert (c.return_date - c.target_arrival).days == c.stay_days


def test_cursor_resets_when_grid_changes(tmp_path):
    conn = storage.connect(tmp_path / "s.db")
    storage.init_db(conn)
    assert storage.get_cursor(conn, "sigA") == 0
    storage.set_cursor(conn, 5)
    assert storage.get_cursor(conn, "sigA") == 5
    # Neue Signatur -> Cursor zurueckgesetzt
    assert storage.get_cursor(conn, "sigB") == 0


def test_grid_signature_stable():
    kwargs = dict(
        arrival_start=date(2027, 1, 20), arrival_end=date(2027, 2, 7),
        stay_days=[18, 21, 25], arrival_step_days=4, outbound_offset_days=1,
    )
    assert grid_signature(build_grid(**kwargs)) == grid_signature(build_grid(**kwargs))
