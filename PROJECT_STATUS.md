# PROJECT_STATUS.md — Aktien-Scanner V1
**Stand: 15. Juni 2026 | Letzter Arbeitsschritt: Phase 6 Nachtrag (Index-Universum)**

Dieses Dokument ist so geschrieben, dass ein neuer Claude-Chat das Projekt
ohne weitere mündliche Erklärungen übernehmen kann. Es beschreibt den
vollständigen Ist-Zustand nach Abschluss der Entwicklung — vor dem ersten
echten Cloud-Deployment.

---

## 1. Projektziel

Ein Streamlit-basierter Swing-Trading-Scanner für Semi-Amateuranleger.
Scannt DAX 40, S&P 500 und Nasdaq 100 täglich nach Aktien in Weinstein-Stage-2-
Konfiguration (Kurs > SMA50, SMA200 steigend, positive Relative Stärke,
Breakout aus Konsolidierung, positives Marktregime). Ergebnisse werden als
Rangliste (Top 20) mit Score 0–100 und vier Bewertungsstufen dargestellt.
Eine optionale KI-Komponente (Anthropic API) generiert Laientexte je Aktie.

**Betreiber:** Marco, Frankenthal (Pfalz), Deutschland. Semi-Amateur-Investor,
Swing-Trading auf DAX 40, S&P 500, Nasdaq 100. Broker: Trade Republic /
Scalable Capital. Gehostet auf Streamlit Community Cloud (kostenlos, öffentlich).

---

## 2. Architekturübersicht

```
Aktien-Scanner V1
├── config.py                  Alle Parameter (Schwellwerte, Zeitpläne, Pfade)
├── scheduler.py               Datenjobs + manueller Update-Trigger
├── app/
│   └── streamlit_app.py       Frontend (Startseite + Detailseite)
├── data/
│   ├── database.py            SQLite-Wrapper (stocks, prices, index_prices, scores)
│   ├── fetcher.py             yfinance-Abruf mit Retry-Logik
│   ├── calendar.py            Letzter Handelstag (pandas_market_calendars)
│   └── index_constituents.py  Laufzeit-Abruf der Ticker-Universen (Phase 6)
├── signals/
│   ├── filter_sma50.py        Hard Filter (Vorbedingung für Score)
│   ├── sma200.py              Signal 1: Langfristtrend (0/7/15 Punkte)
│   ├── relative_strength.py   Signal 2: Relative Stärke (0–25 Punkte)
│   ├── breakout.py            Signal 3: Ausbruch (0/12/24/30 Punkte)
│   ├── regime.py              Signal 4: Marktregime (0/7/15 Punkte, Sperrregel)
│   └── risk.py                Signal 5: CRV/ATR-Risiko (0–15 Punkte)
├── scoring/
│   ├── scorer.py              Orchestrierung aller Signale → Score 0–100
│   └── ai_summary.py          Anthropic-API-Anbindung (KI-Laientext)
├── utils/
│   └── logging_config.py      Logging-Konfiguration
├── tests/
│   ├── helpers.py             Synthetische OHLCV-Daten (make_price_series)
│   ├── seed_demo_db.py        Demo-DB für Frontend-Tests
│   ├── test_signals.py        42 Tests (Signallogik)
│   ├── test_scorer_e2e.py     18 Tests (Scorer End-to-End)
│   ├── test_scheduler.py      37 Tests (Jobs, Mocking)
│   ├── test_ai_summary.py     53 Tests (KI-Modul)
│   ├── test_index_constituents.py  72 Tests (Ticker-Universum)
│   ├── test_frontend.py       57 Tests (Streamlit AppTest)
│   └── test_deployment.py     50 Tests (Importe, requirements.txt, Docs)
├── requirements.txt
└── DEPLOYMENT.md              Detaillierte manuelle Deployment-Anleitung
```

**Datenbank:** SQLite, Pfad `aktien_scanner.db` (konfigurierbar via `config.DB_PATH`).
Tabellen: `stocks` (Ticker-Universum), `prices` (OHLCV je Ticker), `index_prices`
(Indexkurse für Regime + RS), `scores` (Tagesergebnisse mit allen Signalwerten).

**Datenabruf:** yfinance. Kein offizielles API — erwartet Stabilität, aber kein
SLA. HTTP 403 in der Entwicklungsumgebung (Container-Whitelist), auf Streamlit
Cloud funktionsfähig (noch nicht verifiziert, erster Test steht aus).

**Kein Hintergrund-Scheduler auf Streamlit Cloud.** `scheduler.py` enthält
APScheduler-Code für lokalen Betrieb, aber Streamlit Cloud beendet
Background-Threads. Datenaktualisierung erfolgt ausschließlich über den
manuellen Button „🔄 Daten aktualisieren" in der App.

---

## 3. Abgeschlossene Phasen

### Phase 1 — Datenfundament
`config.py`, `data/database.py`, `data/calendar.py`, `data/fetcher.py`,
`utils/logging_config.py`. SQLite-Schema, yfinance-Wrapper mit Retry,
Kalender-Logik für letzten Handelstag.

### Phase 2 — Signale und Scorer
`signals/filter_sma50.py`, `sma200.py`, `relative_strength.py`,
`breakout.py`, `regime.py`, `risk.py`, `scoring/scorer.py`.
5 Signale, Sperrregel (Score-Cap 69 bei neutralem/negativem Marktregime).

### Phase 3 — Scheduler
`scheduler.py` mit `job_europe()` (18:30 MEZ, DAX-Daten),
`job_usa_and_scores()` (23:00 MEZ, US-Daten + alle Scores),
`run_full_update()` (manueller Trigger).

### Phase 4 — Frontend
`app/streamlit_app.py`. Startseite mit Marktstatus-Ampel, Übersicht
(4 Bewertungsstufen als Metriken), Top-20-Rangliste mit Index/Bewertungs-Filter.
Detailseite mit drei aufklappbaren Ebenen: Laientext / technische Details /
Chart-Endkontrolle (6 Ja/Nein-Fragen).

### Phase 5 — KI-Komponente
`scoring/ai_summary.py`. Anthropic-API-Anbindung mit striktem System-Prompt
(keine erfundenen Kurse, keine Kaufempfehlung). Lazy-Generierung + Session-
State-Cache. Ebene 4 im Frontend (KI-Zusammenfassung), Button „Zusammenfassung
erstellen".

### Phase 6 — Deployment-Vorbereitung
`requirements.txt`, `DEPLOYMENT.md` (10 Abschnitte, 5 MANUELLER-SCHRITT-Blöcke),
`tests/test_deployment.py`.

### Phase 6 Nachtrag — Index-Universum (letzter abgeschlossener Schritt)
`data/index_constituents.py`. Laufzeit-Abruf der Ticker-Listen statt
Hardcode-Liste. Vollständige Integration in Scheduler und Frontend-Warnungen.

---

## 4. Neue und geänderte Dateien (Phase 6 Nachtrag)

### Neu erstellt

**`data/index_constituents.py`** (490 Zeilen)
- `fetch_sp500()` — CSV von `raw.githubusercontent.com/datasets/s-and-p-500-companies`
- `fetch_dax40()` — `pandas.read_html()` gegen `en.wikipedia.org/wiki/DAX`
- `fetch_nasdaq100()` — `pandas.read_html()` gegen `en.wikipedia.org/wiki/Nasdaq-100`
- `get_index_constituents(allow_fallback=True)` — orchestriert alle drei, dedupliziert
- `_normalize_ticker()` — BRK.B → BRK-B, .DE/.PA-Suffixe bleiben erhalten
- `_dedupe()` — DEDUP_PRIORITY: SP500 > NDX100 > DAX
- `DAX40_FALLBACK_TICKERS` — 40 verifizierte DAX-Ticker (Notbetrieb, immer `fallback=True`)

Rückgabestruktur von `get_index_constituents()`:
```python
{
    "status": "ok" | "partial" | "error",
    "records": [{"ticker", "index", "source", "fetched_at", "fallback": bool}],
    "fallback_used": ["DAX"],   # wenn Wikipedia-Fallback verwendet
    "failed_indices": ["NDX100"],  # Indizes ohne jede Datenquelle
    "errors": {"NDX100": "Netzwerkfehler: ..."}
}
```

**`tests/test_index_constituents.py`** (522 Zeilen, 72 Tests)
17 Testgruppen: erfolgreicher Abruf je Index (mit Mock), Normalisierung,
Deduplizierung, Teilausfall, Totalausfall, Fallback-Status-Markierung,
Frontend-Warnungslogik, DB-Integration via sync_index_constituents().

### Geändert

**`scheduler.py`**
- `sync_index_constituents()` ergänzt: ruft `get_index_constituents()` auf,
  schreibt Ergebnis via `upsert_stock()` in `stocks`-Tabelle
- `_INDEX_MARKET_CURRENCY` dict für market/currency-Metadaten je Index
- `run_full_update()` gibt jetzt `{"index_sync": ..., "europe": ..., "usa_and_scores": ...}`
  zurück (vorher ohne `index_sync`)
- `job_europe()` ruft am Anfang `sync_index_constituents()` auf (Scheduler-Pfad)

**`app/streamlit_app.py`**
- Update-Button zeigt nach `run_full_update()` je nach `index_sync.status`:
  - `"error"` → `st.error("Indexliste konnte nicht vollständig geladen werden...")`
  - `"partial"` → `st.warning("Folgende Indizes fehlen: ...")`
  - `fallback_used` → `st.info("Reserveliste verwendet für: ...")`

**`tests/helpers.py`**
- `pd.date_range(freq="B")` ersetzt durch robuste Formel (pandas 3.0 lieferte
  manchmal n-1 statt n Einträge; Fix: 2× Kalenderraum, Werktage filtern)

**`tests/test_signals.py`**
- Gleicher `date_range`-Bug an 3 Stellen behoben

**`tests/test_scheduler.py`**
- `sync_index_constituents` in Tests 1, 3, 4, 6 gemockt (verhindert echte
  Netzwerkzugriffe und DB-Kontamination zwischen Tests)
- Test 6: Prüft jetzt auch `"index_sync"` in `run_full_update()`-Rückgabe

---

## 5. Aktuelle Testergebnisse

Alle Tests lokal ausgeführt am 15. Juni 2026. Alle bestanden.

| Test-Suite | Datei | Tests | Status |
|---|---|---|---|
| Signale | tests/test_signals.py | 42 | ✓ 42/42 |
| Scorer E2E | tests/test_scorer_e2e.py | 18 | ✓ 18/18 |
| Scheduler | tests/test_scheduler.py | 37 | ✓ 37/37 |
| KI-Zusammenfassung | tests/test_ai_summary.py | 53 | ✓ 53/53 |
| Index-Universum | tests/test_index_constituents.py | 72 | ✓ 72/72 |
| Frontend | tests/test_frontend.py | 57 | ✓ 57/57 |
| Deployment | tests/test_deployment.py | 50 | ✓ 50/50 |
| **Gesamt** | | **329** | **✓ 329/329** |

**Hinweise zu Testeinschränkungen:**
- yfinance: HTTP 403 in Containerumgebung → alle Datenabruf-Tests gemockt
- Wikipedia: HTTP 403 in Containerumgebung → DAX/NDX100-Abruf nur per Mock testbar
- S&P 500 (raw.githubusercontent.com): live verifiziert, HTTP 200, 503 Ticker
- Frontend-Tests benötigen vorbereitete `aktien_scanner.db` (via `python tests/seed_demo_db.py; cp demo.db aktien_scanner.db`)

**Test-Runner-Reihenfolge (aus Projekt-Root):**
```bash
python tests/seed_demo_db.py && cp demo.db aktien_scanner.db
python tests/test_signals.py
python tests/test_scorer_e2e.py
python tests/test_scheduler.py
python tests/test_ai_summary.py
python tests/test_index_constituents.py
python tests/test_frontend.py
python tests/test_deployment.py
```

---

## 6. Bekannte Restrisiken

### R1 — yfinance-Verfügbarkeit (HOCH, unverifiziert)
yfinance ist kein offizielles API. Auf Streamlit Community Cloud sollte
es funktionieren, wurde aber noch nicht getestet. Mögliche Symptome:
HTTP 403, Rate-Limiting, geänderte Tabellen-Struktur. Wenn `job_europe()`
nach dem ersten echten Update-Klick `erfolgreich: 0` zurückgibt, liegt
es wahrscheinlich hieran.

### R2 — Wikipedia-Struktur (MITTEL)
DAX-40- und Nasdaq-100-Tabellen auf Wikipedia können sich strukturell ändern.
Der Fetcher sucht Spalten "Ticker"/"Company" — ändert sich das, greift der
DAX-Fallback (40 Ticker), Nasdaq 100 fällt komplett aus → `st.warning` im
Frontend. Workaround: Fallback-Liste manuell aktualisieren.

### R3 — DAX-Fallback-Aktualität (NIEDRIG, schleichend)
`DAX40_FALLBACK_TICKERS` in `data/index_constituents.py` entspricht dem
Stand der Verifikation (Juni 2025 laut Wikipedia). DAX-Änderungen
(Aufnahme/Abstieg von Titeln) werden erst bei Live-Wikipedia-Abruf
sichtbar. Im Notbetrieb (Fallback) könnten 1-2 Ticker veraltet sein.

### R4 — run_full_update() Rückgabeformat geändert (NIEDRIG)
Vorher: `{"europe": ..., "usa_and_scores": ...}`
Jetzt: `{"index_sync": ..., "europe": ..., "usa_and_scores": ...}`
Falls eigene Skripte außerhalb der App diesen Return-Wert parsen,
müssen sie angepasst werden.

### R5 — Kein Hintergrundscheduler (BEKANNT, by design)
APScheduler läuft auf Streamlit Cloud nicht zuverlässig als Background-Thread.
Alle Aktualisierungen sind manuell (Button „Daten aktualisieren"). Täglich
ein manueller Klick ist die erwartete Betriebsweise in Version 1.

### R6 — stocks-Tabelle beim ersten Start leer (BEKANNT)
Nach dem allerersten Deployment ist die `stocks`-Tabelle leer. Der erste
Klick auf „Daten aktualisieren" füllt sie via `sync_index_constituents()`.
Erst der zweite Klick ruft dann tatsächlich Kursdaten ab (weil erst jetzt
Ticker in der Tabelle stehen). Das ist korrekt — DEPLOYMENT.md, Abschnitt 9
„Abschlusstest" erläutert das.

---

## 7. Offene Punkte

Alle Entwicklungsaufgaben (Phasen 1–6 inkl. Nachtrag) sind abgeschlossen.
Es gibt keine offenen Code-Änderungen.

**Nicht implementiert (bewusst zurückgestellt für V2):**
- Automatischer Scheduler auf Cloud (z.B. via GitHub Actions Cron)
- Firmen-Namen aus CSV/Wikipedia in `stocks`-Tabelle (aktuell: Ticker als Name-Placeholder)
- Chart-Anzeige direkt im Frontend (aktuell: Verweis auf externes Chart-Tool)
- Alerting / E-Mail-Benachrichtigung bei neuen Signalen
- Backtesting-Modul

**Einzige offene Aufgabe: erstes echtes Deployment** (Abschnitt 9).

---

## 8. Deployment-Status

| Schritt | Status |
|---|---|
| Lokale Entwicklung abgeschlossen | ✓ |
| Alle 329 Tests bestanden | ✓ |
| `requirements.txt` erstellt | ✓ |
| `DEPLOYMENT.md` erstellt | ✓ |
| GitHub-Repository erstellt | ✗ Ausstehend |
| Code auf GitHub gepusht | ✗ Ausstehend |
| Streamlit Community Cloud verbunden | ✗ Ausstehend |
| `ANTHROPIC_API_KEY` als Secret eingetragen | ✗ Ausstehend |
| App erstmalig gestartet | ✗ Ausstehend |
| Erster echter yfinance-Abruf verifiziert | ✗ Ausstehend |
| Erster echter KI-Text generiert | ✗ Ausstehend |

---

## 9. Exakte Schritte für den ersten Cloud-Test

Diese Schritte erfordern menschliche Interaktion (GitHub-Account, Browser).
Claude kann dabei unterstützen, wenn ein Fehler auftritt.

### Schritt 1 — GitHub-Repository anlegen

1. https://github.com/new aufrufen
2. Repository-Name: z.B. `aktien-scanner` (oder beliebig)
3. Sichtbarkeit: Public (für kostenloses Streamlit-Hosting erforderlich)
4. README: Nein (Projekt hat eigene Doku)
5. Repository erstellen

### Schritt 2 — .gitignore anlegen

Im Projekt-Root (lokal) Datei `.gitignore` erstellen:
```
aktien_scanner.db
demo.db
test_*.db
*.log
scanner.log
__pycache__/
*.pyc
.env
```

### Schritt 3 — Code pushen

```bash
cd /pfad/zum/aktien-scanner   # lokales Verzeichnis
git init
git add .
git commit -m "Initial commit: Aktien-Scanner V1 (alle Phasen 1-6)"
git branch -M main
git remote add origin https://github.com/DEIN-USERNAME/aktien-scanner.git
git push -u origin main
```

### Schritt 4 — Streamlit Community Cloud verbinden

1. https://share.streamlit.io aufrufen
2. Mit GitHub-Account anmelden
3. „New app" → Repository auswählen → Branch: `main`
4. Main file path: `app/streamlit_app.py`
5. App-URL wählen (z.B. `aktien-scanner.streamlit.app`)
6. „Deploy!" klicken
7. Warten bis Deployment abgeschlossen (2–5 Minuten, Build-Log beobachten)

### Schritt 5 — ANTHROPIC_API_KEY eintragen

1. API-Key erstellen (falls noch keiner vorhanden):
   https://console.anthropic.com/settings/keys
2. In Streamlit Cloud: App-Dashboard → „⋮" (drei Punkte) → „Settings" → „Secrets"
3. Eintragen:
   ```toml
   ANTHROPIC_API_KEY = "sk-ant-..."
   ```
4. Speichern → App neu starten

### Schritt 6 — Erster Funktionstest

**Test A: Index-Sync und Datenabruf**
1. App-URL im Browser öffnen
2. „🔄 Daten aktualisieren" klicken
3. Spinner beobachten (kann mehrere Minuten dauern: ~543 Ticker × Datenabruf)
4. Erwartetes Ergebnis nach dem ersten Klick:
   - Grüne Erfolgsmeldung mit Statistik (z.B. „Europa-Daten: 38/40 Aktien")
   - Oder: orange/rote Index-Warnung wenn Wikipedia blockiert ist
   - Hinweis: Rangliste bleibt beim ersten Klick ggf. noch leer (stocks-Tabelle
     wird befüllt, aber Preisdaten werden erst ab dem zweiten Klick vollständig)
5. Zweiten Klick auf „Daten aktualisieren" machen
6. Jetzt sollte die Rangliste Aktien anzeigen

**Falls der erste Klick `erfolgreich: 0` meldet:**
- yfinance-Problem: App-Logs prüfen (Streamlit Cloud → App → „Manage app" → Logs)
- Häufig ein temporäres Problem; nach einigen Minuten erneut versuchen

**Test B: KI-Zusammenfassung**
1. Eine Aktie aus der Rangliste anklicken
2. Detailseite öffnet sich
3. Abschnitt „🤖 KI-Zusammenfassung (Ebene 4)" aufklappen
4. „Zusammenfassung erstellen" klicken
5. Erwartetes Ergebnis: Nach 3–10 Sekunden erscheint ein Fließtext mit
   Chancen/Risiken in einfacher Sprache — keine Preise, keine Empfehlungen

**Falls KI-Fehler erscheint:**
- Prüfen ob `ANTHROPIC_API_KEY` korrekt eingetragen ist (kein Leerzeichen, kein Anführungszeichen-Fehler)
- `ANTHROPIC_API_KEY` fehlt → rote Fehlermeldung mit Hinweis auf fehlenden Key (kein App-Crash)

**Test C: Indexlisten-Warnung verifizieren**
Nach dem Update-Klick prüfen:
- Keine Warnung = alle drei Quellen erfolgreich (S&P 500 + Wikipedia DAX + Wikipedia NDX100)
- Orange Warnung „Für DAX wurde eine interne Reserveliste verwendet" = Wikipedia auf Cloud blockiert (DAX-Fallback aktiv, S&P 500 und NDX100 live)
- Rote Warnung = mindestens S&P 500 nicht erreichbar (kritischer Fehler)

### Schritt 7 — Claude einschalten wenn Fehler auftreten

Relevante Informationen beim Fehler-Report an Claude:
- Genaue Fehlermeldung aus dem Streamlit-Log
- Was genau war das Verhalten? (Spinner hängt / Fehlermeldung im UI / App startet nicht)
- Wurde `ANTHROPIC_API_KEY` korrekt gesetzt?
- Welche Python-Version verwendet Streamlit Cloud? (steht im Build-Log)

---

## Technische Schlüsselentscheidungen (Kontext für neue Claude-Instanz)

**Keine 540-Ticker-Hardcodeliste.** Das war eine explizite Pflichtenheft-Vorgabe.
`data/index_constituents.py` ruft Live-Daten ab. Fallback-Ticker sind immer als
`fallback=True` markiert und im Frontend sichtbar gewarnt.

**S&P 500 via GitHub-CSV, DAX/NDX100 via Wikipedia.**
`raw.githubusercontent.com` ist in der Entwicklungsumgebung erreichbar und live
verifiziert. Wikipedia ist aus dem Claude-Container blockiert (HTTP 403), wird
aber auf Streamlit Cloud erwartet. Falls Wikipedia auf Cloud auch blockiert:
DAX nutzt Fallback-Liste, NDX100 fällt aus → `st.warning`.

**Keine Kaufempfehlungen im KI-Text.**
Der System-Prompt in `scoring/ai_summary.py` verbietet explizit das Erfinden
von Kursen und Kaufempfehlungen. Das ist Teil des Pflichtenhefts.

**Sperrregel (Score-Cap 69).**
Bei neutralem oder negativem Marktregime wird der Score auf maximal 69 gekappt,
sodass kein Titel über die Schwelle „Interessant" (70+) kommt. Dies verhindert
Fehlsignale in Bärenmärkten. Implementiert in `scoring/scorer.py`.

**yfinance nicht live testbar in Containerumgebung.**
Seit Phase 1 bekannt und dokumentiert. Alle Datenabruf-Tests sind gemockt.
Erster echter Test = erster Cloud-Deploy.
