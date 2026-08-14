# Flugpreis-Tracker – Open-Jaw FRA → MEL … CHC → FRA

Automatisiertes Tool, das Flugpreise für eine **Open-Jaw-Reise** abfragt, hart nach dem
Umsteigeflughafen filtert und die besten Angebote protokolliert.

- **Hinflug:** Frankfurt (FRA) → Melbourne (MEL)
- **Rückflug:** Christchurch (CHC) → Frankfurt (FRA)
- **Passagiere:** 2 Erwachsene + 1 Kleinkind (Infant on lap), **Economy**
- **Ankunft in Melbourne:** flexibel im Fenster **20.01.–07.02.2027**
- **Aufenthalt:** **2,5–3,5 Wochen** (konfigurierbar, Standard 18 / 21 / 25 Tage)
- **Zwischenstopp-Regel:** grundsätzlich **alle Hubs erlaubt** (auch günstigere), **außer**
  Naher Osten + Istanbul und **visumpflichtige** Transit-Flughäfen. Nur **Economy**, beide Legs.
- **Betrieb:** komplett kostenlos (SerpApi Free-Tier + GitHub Actions + SQLite + GitHub Pages)

> Der Trans-Tasman-Flug **MEL → CHC** wird separat gebucht und hier bewusst **nicht** getrackt.

---

## Zwischenstopp-Filter (Ausschluss-Logik)

Ein Angebot wird verworfen, sobald **ein** Zwischenstopp in einer der Ausschlusslisten liegt:

- **`MIDDLE_EAST_ISTANBUL`** – Naher Osten (DXB, DOH, AUH, RUH, JED, TLV, IKA …) + Istanbul (IST, SAW).
- **`VISA_TRANSIT_REQUIRED`** – Transit-Hubs, für die (deutscher Pass) i. d. R. ein Visum nötig
  ist bzw. dessen Notwendigkeit unklar ist (USA, Festland-China, Indien, Russland).
  **Best-Effort-Liste** – Visaregeln lassen sich nicht aus Flugdaten ableiten, bitte selbst prüfen.

Beide Listen stehen in `flugpreise/filters.py` und lassen sich dort anpassen. Der Filter läuft
**programmatisch nach** der API-Antwort auf den Segment-/Layover-Daten und wird auf **beide** Legs
angewandt (Hinflug FRA→MEL und – über den Drill-down – Rückflug CHC→FRA). Zusätzlich greift ein
harter **Economy-Filter** (alle Segmente müssen Economy sein).

---

## Wie die flexiblen Datumsfenster funktionieren

Aus dem **Ankunftsfenster** (20.01.–07.02.) und den **Aufenthaltslängen** wird ein
**Datums-Raster** aus konkreten Kombinationen gebildet (`flugpreise/grid.py`):

```
Hinflug  FRA → MEL  am  (Ziel-Ankunft − outbound_offset_days)
Rückflug CHC → FRA  am  (Ziel-Ankunft + stay_days)
```

Die tatsächliche MEL-Ankunft wird zusätzlich per **Post-Filter** gegen das Fenster geprüft.
Mit den Standardwerten (Ankunft alle 4 Tage × 3 Aufenthaltslängen) entstehen **18 Kombinationen**.

### Budget-Strategie: „seltener, breiter"

SerpApi Free = **100 Requests/Monat**. Jede Kombination kostet mit Rückflug-Verifikation
**2 Requests** (Hinflug + Drill-down Rückflug). Deshalb:

- **1 Lauf/Tag** (statt mehrmals), dafür **mehrere Kombinationen pro Lauf**
  (`budget.searches_per_run`, Standard 2).
- Ein **rotierender Cursor** (in der DB) sorgt dafür, dass über mehrere Läufe das ganze
  Raster abgedeckt und dann von vorn aktualisiert wird.
- Ein **Budget-Wächter** zählt alle Requests pro Monat in der DB und stoppt **hart** unter
  dem Free-Tier (`budget.monthly_max_requests`, Standard 95) – **egal wie oft** der Cron läuft.

Beispiel-Rechnung: 2 Kombis/Lauf × 2 Requests × ~15 aktive Tage ≈ 60 Requests/Monat →
volles Raster ~alle 9 Tage neu. Grid-Dichte, Läufe und Budget sind frei konfigurierbar.

> Mehr Abdeckung gewünscht? `Amadeus for Developers` (2.000 Calls/Monat) ist als Datenquelle
> vorgesehen – nur `serpapi_client.py`/`parse.py` müssten angepasst werden, Filter & Speicherung bleiben.

---

## Architektur

```
flugpreise/
  filters.py       # HARTER SIN/BKK-Filter (Konstante im Code, beide Legs)
  dates.py         # Datums-Utilities (Fenster, Parsing)
  grid.py          # Datums-Raster aus Ankunftsfenster × Aufenthaltslaengen
  config.py        # config.yaml laden, Multi-City-Parameter bauen
  serpapi_client.py# SerpApi Google-Flights-Aufruf (nur requests)
  provider.py      # Live-/Fixture-Datenquelle + Monats-Budget-Waechter
  parse.py         # SerpApi-Antwort -> Leg-Objekte
  normalize.py     # Freigepaeck-/Tarif-Normalisierung je Airline
  models.py        # Datenmodelle (Segment, Leg, Offer, QueryResult)
  storage.py       # SQLite (queries, offers, state: Cursor + Budget)
  report.py        # statische HTML-Seite (docs/index.html)
  tracker.py       # Orchestrierung + CLI
.github/workflows/track.yml  # Scheduler (1x taeglich, Jitter)
config.yaml        # Reisedaten, Raster, Budget, Optionen
data/flugpreise.db # SQLite-Datenbank (wird von der Action commitet)
docs/index.html    # veroeffentlichbare Ergebnisseite (GitHub Pages)
```

**Ablauf je Kombination:** Multi-City-Suche (`type=3`) → SIN/BKK-Filter Hinflug →
Ankunftsfenster-Post-Filter → Rückflug via `departure_token` nachladen → SIN/BKK-Filter Rückflug →
Top-3 günstigste vollständige Open-Jaw-Angebote in SQLite.

Pro Angebot gespeichert: Abfragezeit, Airline(s), **Gesamtpreis**, Ab-/Ankunftszeiten beider Legs,
Umsteige-Hubs (SIN/BKK) je Leg, Flugdauer, normalisiertes Freigepäck, ob der Rückflug verifiziert
wurde, Segmentdetails, Buchungs-Token und CO₂-Schätzung.

---

## Einrichtung

### 1. SerpApi-Key (kostenlos)
Account auf <https://serpapi.com> (Free-Tier: 100 Requests/Monat), API-Key kopieren.

### 2. Key als GitHub-Secret
Repo → **Settings → Secrets and variables → Actions → New repository secret**
→ Name `SERPAPI_KEY`.

### 3. Reisedaten prüfen
In `config.yaml`: `arrival_window`, `stay_days`, `grid` und `budget` nach Bedarf anpassen.

### 4. GitHub Pages aktivieren (Veröffentlichung für dich & Partnerin)
Repo → **Settings → Pages** → Source: *Deploy from a branch* → Branch `main`, Ordner `/docs`.
Ergebnisseite: `https://<user>.github.io/<repo>/` (trägt `noindex`).

### 5. Scheduler
`.github/workflows/track.yml` läuft per Cron **1×/Tag** (Zeit in UTC) + Jitter.
Geplante Actions laufen nur auf dem **Default-Branch** (`main`) – erst nach dem Merge aktiv.
Manuell: **Actions → Run workflow**.

---

## Lokal ausführen

```bash
pip install -r requirements.txt

# Offline-Demo ohne API-Key (Open-Jaw-Fixture):
python -m flugpreise.tracker --fixture tests/fixtures/open_jaw_sample.json --no-jitter

# Echte Abfrage:
export SERPAPI_KEY=dein_key
python -m flugpreise.tracker --no-jitter

# Tests (Filter, Grid, Pipeline):
python -m pytest -q
```

---

## Preis-Vergleichbarkeit & Gepäck

Kabinenklasse (nur Economy) und **Freigepäck** (aufgegeben + Handgepäck) werden je Leg mitgeführt.
Da Google Flights die Freigepäckmenge nicht zuverlässig liefert, pflegt `flugpreise/normalize.py`
eine **Normalisierungstabelle je Airline** (Orientierungswerte). Für das Kleinkind gelten
abweichende Regeln (Hinweis im Report).

---

## Kosten

| Baustein          | Kosten                                   |
|-------------------|------------------------------------------|
| SerpApi Free-Tier | 0 € (100 Requests/Monat, Budget-Wächter hält < 100) |
| GitHub Actions    | 0 € (öffentliche Repos unbegrenzt)       |
| GitHub Pages      | 0 €                                       |
| SQLite            | 0 € (Datei im Repo)                       |
