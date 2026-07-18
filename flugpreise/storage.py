"""SQLite-Persistenz: Abfragen, Angebote, Rotations-Cursor und Budget-Zähler."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .models import QueryResult

SCHEMA = """
CREATE TABLE IF NOT EXISTS queries (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    queried_at_utc    TEXT NOT NULL,
    route             TEXT NOT NULL,
    outbound_date     TEXT,
    return_date       TEXT,
    target_arrival    TEXT,
    stay_days         INTEGER,
    trip_type         TEXT,
    passengers        TEXT,
    currency          TEXT,
    total_results     INTEGER,
    filtered_results  INTEGER
);

CREATE TABLE IF NOT EXISTS offers (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    query_id                 INTEGER NOT NULL REFERENCES queries(id),
    rank                     INTEGER NOT NULL,
    price                    REAL,
    currency                 TEXT,
    airline                  TEXT,
    airlines                 TEXT,
    total_duration_min       INTEGER,
    stops                    INTEGER,
    layover_airports         TEXT,
    outbound_departure_time  TEXT,
    outbound_arrival_time    TEXT,
    outbound_hubs            TEXT,
    outbound_baggage_checked TEXT,
    outbound_baggage_carry_on TEXT,
    return_departure_time    TEXT,
    return_arrival_time      TEXT,
    return_hubs              TEXT,
    return_baggage_checked   TEXT,
    return_verified          INTEGER,
    fare_summary             TEXT,
    outbound_leg             TEXT,
    return_leg               TEXT,
    booking_token            TEXT,
    carbon_emissions_g       INTEGER
);

CREATE TABLE IF NOT EXISTS state (
    key    TEXT PRIMARY KEY,
    value  TEXT
);

CREATE INDEX IF NOT EXISTS idx_offers_query ON offers(query_id);
CREATE INDEX IF NOT EXISTS idx_queries_time ON queries(queried_at_utc);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


# --------------------------------------------------------------------------
# State (Cursor + Budget)
# --------------------------------------------------------------------------

def get_state(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = conn.execute("SELECT value FROM state WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_state(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO state(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, str(value)),
    )
    conn.commit()


def get_cursor(conn: sqlite3.Connection, signature: str) -> int:
    """Rotations-Cursor. Wird auf 0 zurückgesetzt, wenn sich das Raster ändert."""
    if get_state(conn, "grid_signature") != signature:
        set_state(conn, "grid_signature", signature)
        set_state(conn, "grid_cursor", "0")
        return 0
    return int(get_state(conn, "grid_cursor", "0") or "0")


def set_cursor(conn: sqlite3.Connection, index: int) -> None:
    set_state(conn, "grid_cursor", str(index))


def budget_used(conn: sqlite3.Connection, month: str) -> int:
    return int(get_state(conn, f"budget:{month}", "0") or "0")


def budget_add(conn: sqlite3.Connection, month: str, n: int) -> None:
    set_state(conn, f"budget:{month}", str(budget_used(conn, month) + n))


# --------------------------------------------------------------------------
# Queries + Offers
# --------------------------------------------------------------------------

def save_query(conn: sqlite3.Connection, result: QueryResult) -> int:
    cur = conn.execute(
        """
        INSERT INTO queries
            (queried_at_utc, route, outbound_date, return_date, target_arrival,
             stay_days, trip_type, passengers, currency, total_results, filtered_results)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            result.queried_at_utc,
            result.route,
            result.outbound_date,
            result.return_date,
            result.target_arrival,
            result.stay_days,
            result.trip_type,
            json.dumps(result.passengers, ensure_ascii=False),
            result.currency,
            result.total_results,
            result.filtered_results,
        ),
    )
    query_id = int(cur.lastrowid)

    for rank, offer in enumerate(result.offers, start=1):
        row = offer.to_row()
        conn.execute(
            """
            INSERT INTO offers
                (query_id, rank, price, currency, airline, airlines,
                 total_duration_min, stops, layover_airports,
                 outbound_departure_time, outbound_arrival_time, outbound_hubs,
                 outbound_baggage_checked, outbound_baggage_carry_on,
                 return_departure_time, return_arrival_time, return_hubs,
                 return_baggage_checked, return_verified, fare_summary,
                 outbound_leg, return_leg, booking_token, carbon_emissions_g)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                query_id, rank, row["price"], row["currency"],
                offer.airline_label, row["airlines"],
                row["total_duration_min"], row["stops"], row["layover_airports"],
                row["outbound_departure_time"], row["outbound_arrival_time"], row["outbound_hubs"],
                row["outbound_baggage_checked"], row["outbound_baggage_carry_on"],
                row["return_departure_time"], row["return_arrival_time"], row["return_hubs"],
                row["return_baggage_checked"], row["return_verified"], offer.fare_summary(),
                row["outbound_leg"], row["return_leg"], row["booking_token"],
                row["carbon_emissions_g"],
            ),
        )

    conn.commit()
    return query_id


def latest_offers(conn: sqlite3.Connection, limit_queries: int = 60) -> list[sqlite3.Row]:
    """Angebote der letzten Abfragen (für den Report), neueste zuerst."""
    return conn.execute(
        """
        SELECT q.queried_at_utc, q.route, q.outbound_date, q.return_date,
               q.target_arrival, q.stay_days, q.total_results, q.filtered_results,
               o.*
        FROM offers o
        JOIN queries q ON q.id = o.query_id
        WHERE q.id IN (SELECT id FROM queries ORDER BY id DESC LIMIT ?)
        ORDER BY q.id DESC, o.rank ASC
        """,
        (limit_queries,),
    ).fetchall()


def best_per_combo(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Günstigstes je gesehene Angebot pro Datumskombination (Ankunft + Aufenthalt)."""
    return conn.execute(
        """
        SELECT q.target_arrival, q.stay_days, q.outbound_date, q.return_date,
               MIN(o.price) AS best_price, o.currency,
               o.airline, o.outbound_hubs, o.return_hubs, o.total_duration_min,
               q.queried_at_utc AS cheapest_seen_at
        FROM offers o
        JOIN queries q ON q.id = o.query_id
        GROUP BY q.target_arrival, q.stay_days
        ORDER BY best_price ASC
        """
    ).fetchall()
