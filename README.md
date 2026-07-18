# Flugpreis-Tracker FRA → MEL

Automatisiertes Tool, das mehrmals täglich Flugpreise für **Frankfurt (FRA) → Melbourne (MEL)**
abfragt, hart nach dem Umsteigeflughafen filtert und die besten Angebote protokolliert.

- **Passagiere:** 2 Erwachsene + 1 Kleinkind (Infant on lap)
- **Kabine:** Economy
- **Harte Bedingung (nicht verhandelbar):** Umstieg **ausschließlich über Singapur (SIN)
  oder Bangkok (BKK)**. Jedes andere Angebot wird verworfen – egal wie günstig.
- **Betrieb:** komplett kostenlos (SerpApi Free-Tier + GitHub Actions + SQLite + GitHub Pages)

---

## Der harte SIN/BKK-Filter

Die zentrale Regel ist bewusst so implementiert, dass sie **nicht umgangen werden kann**:

- Die Liste der erlaubten Flughäfen (`{"SIN", "BKK"}`) steht als Konstante direkt im Code
  (`flugpreise/filters.py`, `ALLOWED_LAYOVER_AIRPORTS`) und wird **nicht** aus der Config gelesen.
- Der Filter läuft **programmatisch nach** der API-Antwort auf den Segment-/Layover-Daten –
  nicht als Suchparameter (die Flug-APIs bieten keinen „nur über Hub X"-Parameter).
- Ein Angebot besteht den Filter nur, wenn **alle** Zwischenstopps in `{SIN, BKK}` liegen.
  Ein einziger anderer Stopp (z. B. DXB, DOH) führt zum Verwerfen.
- Echte Direktflüge (0 Umstiege) werden bei `require_layover: true` ebenfalls verworfen.

Das Verhalten ist durch Tests abgesichert (`tests/test_filters.py`): dort wird geprüft, dass
selbst *günstigere* Angebote über falsche Hubs zuverlässig ausgeschlossen werden.

---

## Architektur

```
flugpreise/
  filters.py       # HARTER SIN/BKK-Filter (Konstante im Code)
  config.py        # config.yaml laden, SerpApi-Parameter bauen
  serpapi_client.py# SerpApi Google-Flights-Aufruf (nur requests)
  parse.py         # SerpApi-Antwort -> Offer-Objekte
  normalize.py     # Freigepäck-/Tarif-Normalisierung je Airline
  models.py        # Datenmodelle (Segment, Offer, QueryResult)
  storage.py       # SQLite-Persistenz (queries + offers)
  report.py        # statische HTML-Seite (docs/index.html)
  tracker.py       # Orchestrierung + CLI
.github/workflows/track.yml  # Scheduler (2-3x täglich, mit Zeit-Variation)
config.yaml        # Reisedaten, Passagiere, Optionen
data/flugpreise.db # SQLite-Datenbank (wird von der Action commitet)
docs/index.html    # veröffentlichbare Ergebnisseite (GitHub Pages)
```

**Ablauf je Abfrage:** SerpApi-Suche → harter SIN/BKK-Filter → nach Preis sortieren →
Top-3 in SQLite schreiben → HTML-Report neu erzeugen.

Pro Angebot werden gespeichert: Abfragezeitpunkt, Airline(s), Preis, Ab-/Ankunftszeiten,
Anzahl Umstiege + Umsteigeflughafen (SIN/BKK), Gesamtreisedauer, normalisiertes Freigepäck
(aufgegeben + Handgepäck), Tarif-/Klassen-Zusammenfassung, Segmentdetails, Buchungs-Token
und CO₂-Schätzung.

---

## Einrichtung

### 1. SerpApi-Key besorgen (kostenlos)

1. Account auf <https://serpapi.com> anlegen (Free-Tier: **100 Requests/Monat**).
2. API-Key aus dem Dashboard kopieren.

> 2–3 Abfragen/Tag ≈ 60–90 Requests/Monat → passt in den Free-Tier.
> (Achtung: `verify_return_leg: true` verbraucht **zusätzliche** Requests, siehe unten.)

### 2. Key als GitHub-Secret hinterlegen

Repo → **Settings → Secrets and variables → Actions → New repository secret**
- Name: `SERPAPI_KEY`
- Wert: dein SerpApi-Key

### 3. Reisedaten anpassen

In `config.yaml` `outbound_date` / `return_date` und ggf. Passagiere/Optionen setzen.

### 4. GitHub Pages aktivieren (Veröffentlichung für dich & Partnerin)

Repo → **Settings → Pages** → Source: *Deploy from a branch* → Branch: `main`, Ordner `/docs`.
Danach ist die Ergebnisseite unter `https://<user>.github.io/<repo>/` erreichbar.
Die Seite trägt `noindex`, ist also nicht für Suchmaschinen bestimmt.

### 5. Scheduler

`.github/workflows/track.yml` läuft per Cron 3×/Tag (Zeiten in **UTC**). Die tatsächliche
Abfragezeit variiert zusätzlich durch einen zufälligen Jitter (`schedule.max_jitter_minutes`),
sodass nie exakt zur selben Uhrzeit abgefragt wird.

> Hinweis: Geplante Actions laufen nur auf dem **Default-Branch** (`main`). Erst nach dem
> Merge dieses Branches startet der Zeitplan automatisch.

Manuell testen: Repo → **Actions → Flugpreis-Tracker → Run workflow**.

---

## Lokal ausführen

```bash
pip install -r requirements.txt

# Offline-Demo ohne API-Key (nutzt die mitgelieferte Beispielantwort):
python -m flugpreise.tracker --fixture tests/fixtures/serpapi_sample.json --no-jitter

# Echte Abfrage:
export SERPAPI_KEY=dein_key
python -m flugpreise.tracker --no-jitter

# Tests (inkl. Filter-Absicherung):
python -m pytest -q
```

Ergebnis: Einträge in `data/flugpreise.db` und aktualisierte `docs/index.html`.

---

## Preis-Vergleichbarkeit & Gepäck

Damit Preise je Airline fair vergleichbar sind, werden **Kabinenklasse** (nur Economy) und
**Freigepäck** (aufgegeben + Handgepäck) mitgeführt. Da Google Flights die Freigepäckmenge
nicht zuverlässig strukturiert liefert, pflegt `flugpreise/normalize.py` eine
**Normalisierungstabelle je Airline** (Orientierungswerte, bitte gelegentlich prüfen).
Für das Kleinkind gelten abweichende Regeln – siehe Hinweis im Report.

---

## Round-Trip-Hinweis (wichtig)

Google Flights liefert bei Hin-/Rückflug zunächst die **Hinflüge**; der Gesamtpreis ist der
Round-Trip-Preis. Der Standardfilter prüft die Umsteige-Hubs auf dem **Hinflug**.

Wer auch den **Rückflug** streng auf SIN/BKK prüfen will, setzt `filter.verify_return_leg: true`.
Dann wird pro Top-Kandidat der Rückflug nachgeladen und ebenfalls gefiltert – das kostet
**zusätzliche SerpApi-Requests** (Budget beachten!). Angebote ohne gültigen Rückflug-Hub
werden dann verworfen.

---

## Alternativen zur Datenquelle

Der Code ist um SerpApi herum gebaut (einfachster, stabiler Self-Service-Zugang). Alternativen
mit Free-Tier: **Amadeus for Developers** (2.000 Calls/Monat, Testumgebung ggf. mit leicht
abweichenden Preisen) oder **Kiwi.com Tequila** (Freigabe nötig). Für einen Wechsel müssten
`serpapi_client.py` + `parse.py` angepasst werden; der harte Filter (`filters.py`) und die
Speicherung bleiben unverändert.

---

## Kosten

| Baustein          | Kosten                                   |
|-------------------|------------------------------------------|
| SerpApi Free-Tier | 0 € (100 Requests/Monat)                 |
| GitHub Actions    | 0 € (öffentliche Repos unbegrenzt)       |
| GitHub Pages      | 0 €                                       |
| SQLite            | 0 € (Datei im Repo)                       |
