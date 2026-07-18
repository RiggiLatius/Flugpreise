"""Erzeugt eine statische HTML-Seite aus der SQLite-Datenbank.

Die Seite (Standard: ``docs/index.html``) kann kostenlos via GitHub Pages
veröffentlicht werden -- gedacht für den privaten Gebrauch.
"""

from __future__ import annotations

import html
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from . import storage
from .config import Config
from .filters import ALLOWED_LAYOVER_AIRPORTS
from .normalize import INFANT_NOTE


def _fmt_duration(minutes) -> str:
    if not minutes:
        return "?"
    h, m = divmod(int(minutes), 60)
    return f"{h} h {m:02d} min"


def _fmt_price(price, currency) -> str:
    if price is None:
        return "-"
    return f"{price:,.0f} {currency}".replace(",", ".")


def _esc(value) -> str:
    return html.escape("" if value is None else str(value))


def _best_combo_section(conn: sqlite3.Connection) -> str:
    rows = storage.best_per_combo(conn)
    if not rows:
        return ""
    body = []
    for r in rows:
        ret_hubs = r["return_hubs"] or "–"
        body.append(f"""
          <tr>
            <td>{_esc(r['target_arrival'])}</td>
            <td>{_esc(r['stay_days'])} T</td>
            <td class="price">{_esc(_fmt_price(r['best_price'], r['currency']))}</td>
            <td>{_esc(r['airline'])}</td>
            <td><span class="hub">{_esc(r['outbound_hubs'])}</span> / <span class="hub">{_esc(ret_hubs)}</span></td>
            <td class="muted">{_esc(r['outbound_date'])} → {_esc(r['return_date'])}</td>
          </tr>""")
    return f"""
    <section class="query highlight">
      <h2>🏆 Bester bisher gesehener Preis je Datumskombination</h2>
      <p class="submeta">Ankunft in MEL × Aufenthaltsdauer – günstigste je beobachtete Open-Jaw-Kombination.</p>
      <div class="table-wrap">
      <table>
        <thead><tr><th>MEL-Ankunft</th><th>Aufenthalt</th><th>Bester Preis</th>
               <th>Airline</th><th>Hubs Hin/Rück</th><th>Flugdaten</th></tr></thead>
        <tbody>{''.join(body)}</tbody>
      </table>
      </div>
    </section>"""


def build_html(conn: sqlite3.Connection, cfg: Config) -> str:
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    hubs = " / ".join(sorted(ALLOWED_LAYOVER_AIRPORTS))
    rows = storage.latest_offers(conn, limit_queries=60)

    # nach Abfrage gruppieren (neueste zuerst)
    groups: list[tuple[str, list[sqlite3.Row]]] = []
    current_key = None
    for row in rows:
        key = (row["queried_at_utc"], row["target_arrival"], row["stay_days"])
        if key != current_key:
            groups.append((key, []))
            current_key = key
        groups[-1][1].append(row)

    sections = [_best_combo_section(conn)]
    for (queried_at, arrival, stay), offers in groups:
        meta = offers[0] if offers else None
        offer_rows = []
        for o in offers:
            ret_ok = "✓" if o["return_verified"] else "–"
            ret_hub = o["return_hubs"] or "–"
            offer_rows.append(f"""
              <tr>
                <td class="rank">#{_esc(o['rank'])}</td>
                <td class="price">{_esc(_fmt_price(o['price'], o['currency']))}</td>
                <td>{_esc(o['airline'])}</td>
                <td>{_esc(o['outbound_departure_time'])}<br>
                    <span class="muted">→ {_esc(o['outbound_arrival_time'])}</span></td>
                <td><span class="hub">{_esc(o['outbound_hubs'])}</span></td>
                <td>{_esc(o['return_departure_time'])}<br>
                    <span class="muted">→ {_esc(o['return_arrival_time'])}</span></td>
                <td><span class="hub">{_esc(ret_hub)}</span><br>
                    <span class="muted">verif. {ret_ok}</span></td>
                <td class="bag">Aufg.: {_esc(o['outbound_baggage_checked'])}<br>
                    Handg.: {_esc(o['outbound_baggage_carry_on'])}</td>
              </tr>""")

        sections.append(f"""
        <section class="query">
          <h2>{_esc(queried_at)}</h2>
          <p class="submeta">MEL-Ankunft {_esc(arrival)} · Aufenthalt {_esc(stay)} Tage ·
             gefiltert: {_esc(meta['filtered_results']) if meta else '?'} von
             {_esc(meta['total_results']) if meta else '?'} · Hinflug {_esc(meta['outbound_date']) if meta else ''}
             → Rückflug CHC {_esc(meta['return_date']) if meta else ''}</p>
          <div class="table-wrap">
          <table>
            <thead>
              <tr><th>#</th><th>Preis (gesamt)</th><th>Airline</th>
                  <th>Hinflug FRA→MEL</th><th>Hub</th>
                  <th>Rückflug CHC→FRA</th><th>Hub</th><th>Gepäck (Economy)</th></tr>
            </thead>
            <tbody>{''.join(offer_rows)}</tbody>
          </table>
          </div>
        </section>""")

    body = "\n".join(s for s in sections if s) or "<p>Noch keine Daten vorhanden.</p>"

    p = cfg.passengers
    passengers = (
        f"{p['adults']} Erwachsene + {p['infants_on_lap']} Kleinkind(er) · "
        f"{cfg.travel_class.replace('_', ' ').title()}"
    )
    window = f"{cfg.arrival_start.isoformat()} – {cfg.arrival_end.isoformat()}"
    stays = " / ".join(str(s) for s in cfg.stay_days)

    return f"""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Flugpreise FRA → MEL … CHC → FRA</title>
<style>
  :root {{ color-scheme: light dark; }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
         margin: 0; background: #0f1216; color: #e7ecf3; line-height: 1.5; }}
  header.top {{ padding: 1.6rem 1.2rem; background: linear-gradient(120deg,#12324a,#0f1216);
                border-bottom: 1px solid #21303c; }}
  h1 {{ margin: 0 0 .3rem; font-size: 1.45rem; }}
  .badge {{ display:inline-block; background:#153b2b; color:#7ee2ab; border:1px solid #1f6b47;
            padding:.15rem .6rem; border-radius:999px; font-size:.8rem; margin-top:.4rem;}}
  main {{ max-width: 1150px; margin: 0 auto; padding: 1.2rem; }}
  .submeta, .muted {{ color:#9fb0c0; font-size:.85rem; }}
  section.query {{ margin: 1.4rem 0; background:#151a21; border:1px solid #222c37;
                   border-radius:12px; padding:1rem 1rem .4rem; }}
  section.highlight {{ border-color:#1f6b47; }}
  section.query h2 {{ font-size:1rem; margin:.2rem 0 .1rem; color:#cfe0f0; }}
  .table-wrap {{ overflow-x:auto; }}
  table {{ width:100%; border-collapse:collapse; font-size:.9rem; margin-top:.6rem; }}
  th, td {{ text-align:left; padding:.5rem .55rem; border-bottom:1px solid #222c37; vertical-align:top; }}
  th {{ color:#9fb0c0; font-weight:600; font-size:.75rem; text-transform:uppercase; letter-spacing:.03em; }}
  td.price {{ font-weight:700; color:#7ee2ab; white-space:nowrap; }}
  td.rank {{ color:#9fb0c0; }}
  .hub {{ color:#ffd479; font-weight:600; }}
  .bag {{ font-size:.8rem; color:#c3d0dd; }}
  footer {{ padding:1.5rem 1.2rem; color:#7d8a97; font-size:.8rem; max-width:1150px; margin:0 auto; }}
  @media (prefers-color-scheme: light) {{
    body {{ background:#f6f8fb; color:#182430; }}
    header.top {{ background:linear-gradient(120deg,#dbeafe,#f6f8fb); border-bottom:1px solid #d5deea; }}
    section.query {{ background:#fff; border-color:#e2e8f0; }}
    th, td {{ border-color:#e6ebf1; }}
    .submeta,.muted {{ color:#5a6b7b; }}
  }}
</style>
</head>
<body>
<header class="top">
  <h1>Flugpreise FRA → MEL … CHC → FRA (Open-Jaw)</h1>
  <div class="submeta">{passengers} · MEL-Ankunft {window} · Aufenthalt {stays} Tage</div>
  <span class="badge">Harter Filter aktiv: nur Umstieg über {_esc(hubs)} (Hin- & Rückflug)</span>
</header>
<main>
  {body}
</main>
<footer>
  <p>Zuletzt aktualisiert: {generated}. Preise sind Gesamtpreise der Open-Jaw-Kombination
     (Hinflug FRA→MEL + Rückflug CHC→FRA). „verif. ✓" = Rückflug wurde ebenfalls hart auf
     {_esc(hubs)} geprüft.</p>
  <p>{INFANT_NOTE} Gepäckangaben sind normalisierte Orientierungswerte je Airline.
     Der Flug MEL→CHC wird separat gebucht und hier nicht getrackt.</p>
</footer>
</body>
</html>
"""


def write_report(conn: sqlite3.Connection, cfg: Config) -> None:
    out = Path(cfg.output_html)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_html(conn, cfg), encoding="utf-8")
