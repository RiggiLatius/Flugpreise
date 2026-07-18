"""SQLite-Persistenz für Abfragen und Angebote."""

from __future__ import annotations

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
    layover_details          TEXT,
    departure_airport        TEXT,
    departure_time           TEXT,
    arrival_airport          TEXT,
    arrival_time             TEXT,
    travel_class             TEXT,
    baggage_checked          TEXT,
    baggage_carry_on         TEXT,
    fare_summary             TEXT,
    segments                 TEXT,
    return_segments          TEXT,
    return_layover_airports  TEXT,
    booking_token            TEXT,
    carbon_emissions_g       INTEGER
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


def save_query(conn: sqlite3.Connection, result: QueryResult) -> int:
    """Speichert eine Abfrage inkl. ihrer Top-N-Angebote. Gibt query_id zurück."""
    import json

    cur = conn.execute(
        """
        INSERT INTO queries
            (queried_at_utc, route, outbound_date, return_date, trip_type,
             passengers, currency, total_results, filtered_results)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            result.queried_at_utc,
            result.route,
            result.outbound_date,
            result.return_date,
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
                 total_duration_min, stops, layover_airports, layover_details,
                 departure_airport, departure_time, arrival_airport, arrival_time,
                 travel_class, baggage_checked, baggage_carry_on, fare_summary,
                 segments, return_segments, return_layover_airports,
                 booking_token, carbon_emissions_g)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                query_id,
                rank,
                row["price"],
                row["currency"],
                offer.airline_label,
                row["airlines"],
                row["total_duration_min"],
                row["stops"],
                row["layover_airports"],
                row["layover_details"],
                row["departure_airport"],
                row["departure_time"],
                row["arrival_airport"],
                row["arrival_time"],
                row["travel_class"],
                row["baggage_checked"],
                row["baggage_carry_on"],
                offer.fare_summary(),
                row["segments"],
                row["return_segments"],
                row["return_layover_airports"],
                row["booking_token"],
                row["carbon_emissions_g"],
            ),
        )

    conn.commit()
    return query_id


def latest_offers(conn: sqlite3.Connection, limit_queries: int = 30) -> list[sqlite3.Row]:
    """Angebote der letzten Abfragen (für den Report), neueste zuerst."""
    return conn.execute(
        """
        SELECT q.queried_at_utc, q.route, q.outbound_date, q.return_date,
               q.trip_type, q.total_results, q.filtered_results,
               o.*
        FROM offers o
        JOIN queries q ON q.id = o.query_id
        WHERE q.id IN (SELECT id FROM queries ORDER BY id DESC LIMIT ?)
        ORDER BY q.id DESC, o.rank ASC
        """,
        (limit_queries,),
    ).fetchall()
