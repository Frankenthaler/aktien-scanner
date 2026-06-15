# DEPLOYMENT.md
## Aktien-Scanner V1 — Deployment-Anleitung (Phase 6)

Dieses Dokument beschreibt, wie die App auf Streamlit Community Cloud
veröffentlicht wird, und welche Schritte du selbst manuell durchführen musst.

**Wichtiger Hinweis vorab:** Alle Schritte in diesem Dokument, die einen
GitHub-Account, einen Streamlit-Cloud-Account oder einen API-Schlüssel
erfordern, sind als **MANUELLER SCHRITT** markiert. Diese Schritte können
nicht automatisiert oder von hier aus durchgeführt werden — sie erfordern
deine Zugangsdaten.

---

## 1. Projektstruktur (Referenz)

Bevor du beginnst, stelle sicher, dass folgende Struktur vorliegt:

```
aktien-scanner/
├── app/
│   ├── __init__.py
│   └── streamlit_app.py
├── data/
│   ├── __init__.py
│   ├── calendar.py
│   ├── database.py
│   └── fetcher.py
├── signals/
│   ├── __init__.py
│   ├── filter_sma50.py
│   ├── sma200.py
│   ├── relative_strength.py
│   ├── breakout.py
│   ├── regime.py
│   └── risk.py
├── scoring/
│   ├── __init__.py
│   ├── scorer.py
│   └── ai_summary.py
├── utils/
│   ├── __init__.py
│   └── logging_config.py
├── tests/
│   └── ... (alle Testdateien)
├── config.py
├── scheduler.py
├── requirements.txt
└── DEPLOYMENT.md
```

Diese Struktur wurde in Phase 1-5 vollständig erstellt und getestet
(206/206 Tests bestanden, Stand Phase 5).

---

## 2. GitHub-Repository vorbereiten

### MANUELLER SCHRITT 2.1 — Repository erstellen

1. Bei GitHub einloggen (oder Account erstellen: https://github.com/signup)
2. Neues Repository anlegen: https://github.com/new
   - Name: z.B. `aktien-scanner`
   - Sichtbarkeit: **Privat** empfohlen (siehe Hinweis unten)
   - Keine README/.gitignore/Lizenz automatisch erstellen lassen (falls du
     die Projektdateien direkt hochlädst)

**Hinweis zur Sichtbarkeit:** Streamlit Community Cloud kann auch private
Repositories verbinden. Da dieses Projekt keine Zugangsdaten im Code enthält
(API-Keys werden über Secrets verwaltet, siehe Abschnitt 5), ist ein
öffentliches Repository technisch unproblematisch — die Wahl ist aber deine
Entscheidung.

### MANUELLER SCHRITT 2.2 — .gitignore anlegen

Lege im Projekt-Wurzelverzeichnis eine Datei `.gitignore` mit folgendem
Inhalt an, damit lokale Datenbanken und Logs nicht versehentlich
hochgeladen werden:

```
*.db
*.log
__pycache__/
*.pyc
.venv/
venv/
```

**Begründung:** Die Datenbank (`aktien_scanner.db`) wird auf Streamlit
Cloud bei jedem Neustart der App neu erzeugt (siehe Abschnitt 6 zum
Scheduler-Verhalten). Sie muss nicht ins Repository.

---

## 3. Projektdateien hochladen

### MANUELLER SCHRITT 3.1 — Dateien committen und pushen

Lokal im Projektverzeichnis:

```bash
git init
git add .
git commit -m "Initial commit: Aktien-Scanner V1"
git branch -M main
git remote add origin https://github.com/DEIN-BENUTZERNAME/aktien-scanner.git
git push -u origin main
```

Ersetze `DEIN-BENUTZERNAME` durch deinen tatsächlichen GitHub-Benutzernamen.

**Alternative ohne Git-Kommandozeile:** Du kannst alle Dateien auch über
die GitHub-Web-Oberfläche hochladen ("Add file" → "Upload files"). Achte
darauf, die Ordnerstruktur (Unterordner `app/`, `data/`, `signals/` usw.)
dabei zu erhalten — beim Web-Upload müssen Unterordner einzeln per
Drag&Drop der jeweiligen Dateien erzeugt werden.

### Checkliste: vollständiger Upload

Prüfe nach dem Push auf GitHub, dass folgende Dateien vorhanden sind:

- [ ] `requirements.txt` (im Wurzelverzeichnis)
- [ ] `config.py`
- [ ] `app/streamlit_app.py`
- [ ] Alle Unterordner `data/`, `signals/`, `scoring/`, `utils/`
      inklusive `__init__.py`-Dateien
- [ ] `scheduler.py`

---

## 4. Streamlit Community Cloud verbinden

### MANUELLER SCHRITT 4.1 — Account und App anlegen

1. Gehe zu https://share.streamlit.io
2. Melde dich mit deinem GitHub-Account an (falls noch nicht geschehen,
   wird der Zugriff auf GitHub-Repositories angefragt — bestätigen)
3. Klicke auf **"New app"**
4. Wähle:
   - **Repository:** `DEIN-BENUTZERNAME/aktien-scanner`
   - **Branch:** `main`
   - **Main file path:** `app/streamlit_app.py`

   Dies ist der wichtigste Punkt: Die Startdatei muss exakt
   `app/streamlit_app.py` lauten (mit Pfad-Unterordner), nicht nur
   `streamlit_app.py`.

5. Klicke noch **nicht** auf "Deploy" — zuerst die Secrets konfigurieren
   (Abschnitt 5), da die App ohne `ANTHROPIC_API_KEY` zwar startet, die
   KI-Zusammenfassung aber nicht funktioniert.

---

## 5. Secrets konfigurieren

### MANUELLER SCHRITT 5.1 — ANTHROPIC_API_KEY setzen

1. Falls noch nicht vorhanden: API-Key erstellen unter
   https://console.anthropic.com/settings/keys
2. In Streamlit Cloud: beim App-Setup (oder später über
   "⋮" → "Settings" → "Secrets") folgenden Inhalt eintragen:

   ```toml
   ANTHROPIC_API_KEY = "sk-ant-..."
   ```

   Ersetze `sk-ant-...` durch deinen tatsächlichen Schlüssel.

**Wichtig:** Trage hier niemals den echten Schlüssel in eine Datei ein,
die ins GitHub-Repository hochgeladen wird. Streamlit Cloud Secrets sind
separat vom Code gespeichert und werden zur Laufzeit als Umgebungsvariable
bereitgestellt — `os.environ.get("ANTHROPIC_API_KEY")` in
`scoring/ai_summary.py` greift automatisch darauf zu.

### Verifikation der Implementierung (bereits umgesetzt, Phase 5)

`scoring/ai_summary.py` liest den Schlüssel ausschließlich über:

```python
api_key = os.environ.get("ANTHROPIC_API_KEY")
```

Ist die Variable nicht gesetzt, liefert die Funktion
`{"success": False, "error": "...kein API-Schlüssel konfiguriert..."}`
zurück — die App stürzt nicht ab (siehe Abschnitt 8.3 für den Test).

---

## 6. Scheduler-Fall: realistische Einschätzung

### 6.1 Kann ein dauerhaft laufender Scheduler auf Streamlit Community Cloud
betrieben werden?

**Nein, nicht zuverlässig.** Begründung:

- Streamlit Community Cloud führt **eine Streamlit-App** aus — keinen
  separaten Hintergrundprozess. `scheduler.main()` mit
  `BlockingScheduler` würde den gesamten App-Prozess blockieren und die
  Web-Oberfläche unbenutzbar machen.
- Ein `BackgroundScheduler` (Thread) innerhalb von `streamlit_app.py`
  würde zwar technisch starten, aber:
  - Streamlit Cloud kann Apps bei Inaktivität in einen Schlafzustand
    versetzen ("App put to sleep"). Ein Hintergrund-Thread läuft dann
    nicht mehr.
  - Bei jedem Neustart/Redeploy der App (z.B. nach Code-Änderungen)
    würde ein neuer Thread gestartet — bei mehreren gleichzeitigen
    Nutzersitzungen potenziell mehrfach, was zu doppelten Datenabrufen
    führen kann.
  - Es gibt keine Garantie, dass die App zur konfigurierten Uhrzeit
    (18:30 / 23:00 MEZ) überhaupt aktiv ist.

**Entscheidung für Version 1 (bereits in Phase 3/4 umgesetzt):**
`app/streamlit_app.py` startet **keinen Scheduler**. Es importiert nur
die Funktion `run_full_update()` aus `scheduler.py` und ruft sie
ausschließlich auf Knopfdruck auf (Schaltfläche "🔄 Daten aktualisieren").
Dies ist kein nachträglicher Workaround, sondern entspricht der
Master-Spezifikation V1.1, Abschnitt "Systemübersicht":

> "Der Scheduler ist Bestandteil der Architektur, aber nicht Voraussetzung
> für die Funktionsfähigkeit von Version 1."

### 6.2 Cloud-Fallback: manuelle Aktualisierung (bereits implementiert)

Die Schaltfläche "🔄 Daten aktualisieren" auf der Startseite ruft
`run_full_update()` synchron im Webserver-Prozess auf:

```python
if st.button("🔄 Daten aktualisieren", ...):
    with st.spinner("Daten werden aktualisiert …"):
        result = run_full_update()
```

**Praktische Konsequenz für den Cloud-Betrieb:**
- Der Nutzer (du) muss die App regelmäßig öffnen und den Button klicken,
  um aktuelle Daten zu erhalten.
- Ein vollständiger Durchlauf für ~540 Aktien kann je nach
  yfinance-Antwortzeiten mehrere Minuten dauern. Streamlit Cloud hat
  ein Standard-Timeout für einzelne Skriptausführungen — bei sehr vielen
  Tickern kann dies zum Problem werden (siehe Abschnitt 9, Fehlerdiagnose).

### 6.3 `scheduler.py` und `scheduler.main()` bleiben nutzbar

Für den **lokalen Betrieb** (z.B. auf einem eigenen Server oder Raspberry
Pi) bleibt `python scheduler.py` als eigenständiger, blockierender Prozess
voll funktionsfähig — dafür wurde er in Phase 3 entworfen und getestet
(36/36 Tests). Für Streamlit Community Cloud ist dieser Modus **nicht**
vorgesehen und wird dort **nicht** verwendet.

---

## 7. Lokalen Test durchführen

### 7.1 Vorbereitung

```bash
cd aktien-scanner
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 7.2 Datenbank initialisieren und Logging prüfen

```bash
python3 -c "
from utils.logging_config import setup_logging
setup_logging()
from data.database import init_db
init_db()
"
```

Erwartung: Datei `scanner.log` wird erstellt, Konsolenausgabe zeigt
"Datenbank initialisiert."

### 7.3 App lokal starten

```bash
streamlit run app/streamlit_app.py
```

Erwartung: Browser öffnet sich auf `http://localhost:8501`, Startseite
zeigt "Noch keine Daten vorhanden" mit Hinweis auf den
"Daten aktualisieren"-Button.

### 7.4 Manuelles Update mit echten Daten (lokal)

In der gestarteten App: Klick auf "🔄 Daten aktualisieren".

**Voraussetzung:** Die `stocks`-Tabelle muss zuvor mit Tickern befüllt
werden (siehe `tests/seed_demo_db.py` als Vorlage für `upsert_stock()`-
Aufrufe, oder eine eigene Seed-Datei mit den 540 Tickern aus DAX/S&P 500/
Nasdaq 100 — diese vollständige Tickerliste ist laut Master-Spezifikation
V1.1, Abschnitt 16, weiterhin ein offener Punkt).

---

## 8. Abschlusstest mit echten Daten

Dieser Abschnitt listet die Tests, die **du selbst** mit echtem
Internetzugang durchführen musst, da diese Entwicklungsumgebung keinen
Zugriff auf Yahoo Finance hat (HTTP 403 bei jedem yfinance-Aufruf, seit
Phase 1 dokumentiert).

### 8.1 Lokaler Test mit echtem yfinance-Zugriff

```bash
python3 -c "
from data.fetcher import test_ticker
print(test_ticker('SAP.DE'))
print(test_ticker('AAPL'))
print(test_ticker('^GDAXI'))
"
```

**Erwartetes Ergebnis:** `{'ticker': 'SAP.DE', 'ok': True, 'rows': >=210, 'error': None}`
für alle drei Aufrufe (Indizes benötigen ggf. weniger als
`MIN_TRADING_DAYS`, daher `test_ticker` für `^GDAXI` ggf. mit `ok=False`
aber `error` bzgl. Zeilenzahl — das ist für Indizes kein Problem, da
`fetch_index()` separat verwendet wird).

**Status: Noch nicht durchgeführt** — dieser Test erfordert echten
Internetzugang außerhalb dieser Umgebung.

### 8.2 Cloud-Test mit echten Daten

Nach erfolgreichem Deployment (Abschnitte 2-5):

1. App-URL öffnen (z.B. `https://DEIN-APP-NAME.streamlit.app`)
2. "🔄 Daten aktualisieren" klicken
3. Prüfen: Werden Scores berechnet und in der Rangliste angezeigt?

**Status: Noch nicht durchgeführt** — erfordert abgeschlossenes
Deployment (Abschnitte 2-5) und eine befüllte `stocks`-Tabelle.

### 8.3 Test mit gesetztem und fehlendem ANTHROPIC_API_KEY

**Mit Key (Cloud, nach Secret-Konfiguration):**
1. Eine Aktie in der Rangliste anklicken
2. Abschnitt "🤖 KI-Zusammenfassung" aufklappen
3. "Zusammenfassung erstellen" klicken
4. Erwartung: Nach kurzer Ladezeit (Spinner) erscheint ein Fließtext
   mit Chancen/Risiken in einfacher Sprache, keine Fehlermeldung

**Ohne Key (lokal, `ANTHROPIC_API_KEY` nicht gesetzt):**
1. Gleicher Ablauf wie oben
2. Erwartung: Es erscheint die Meldung "Die KI-Zusammenfassung ist
   derzeit nicht verfügbar (kein API-Schlüssel konfiguriert)." — kein
   Absturz, keine Exception

**Status:** Der Fehlerfall (fehlender Key) ist durch
`tests/test_ai_summary.py` (Test 3, gemockt) bereits automatisiert
verifiziert. Der Erfolgsfall mit echtem Key und echter API-Antwort ist
**noch nicht durchgeführt** — erfordert einen gültigen
`ANTHROPIC_API_KEY` und echten Netzwerkzugriff zu `api.anthropic.com`.

### 8.4 Test der KI-Zusammenfassung (inhaltlich)

Nach 8.3 (mit Key): Prüfe stichprobenartig für 2-3 Aktien mit
unterschiedlichen Bewertungen ("Starkes Kaufsignal", "Beobachten",
"Kein Kauf"), ob:

- [ ] der Text 3-4 Sätze umfasst (gemäß System-Prompt)
- [ ] keine konkreten Kurswerte genannt werden, die nicht im Prompt
      standen (Stichprobe gegen `score_dict` der jeweiligen Aktie)
- [ ] keine Kaufempfehlung ausgesprochen wird (z.B. "Sie sollten kaufen")
- [ ] Chancen UND Risiken erwähnt werden

**Status: Noch nicht durchgeführt** — Folgetest von 8.3.

### 8.5 Test des manuellen Daten-Updates (End-to-End)

```
1. App öffnen (lokal oder Cloud)
2. "🔄 Daten aktualisieren" klicken
3. Spinner "Daten werden aktualisiert …" sichtbar?
4. Nach Abschluss: Erfolgsmeldung mit Statistik sichtbar?
   "Europa-Daten: X/Y Aktien", "USA-Daten: X/Y Aktien",
   "Scores berechnet: X/Y Aktien"
5. Rangliste zeigt aktualisierte Scores mit aktuellem Datum?
6. scanner.log enthält "Job Europa gestartet/beendet" und
   "Job USA + Scores gestartet/beendet"?
```

**Status: Noch nicht durchgeführt** — erfordert befüllte `stocks`-Tabelle
und echten yfinance-Zugriff (siehe 8.1).

---

## 9. Fehlerdiagnose bei typischen Problemen

| Problem | Mögliche Ursache | Lösung |
|---|---|---|
| "ModuleNotFoundError" beim Deployment | `requirements.txt` fehlt oder unvollständig | Prüfen, dass `requirements.txt` im Wurzelverzeichnis liegt und alle Pakete aus Abschnitt "externe Imports" enthält |
| App startet, aber "Main file" nicht gefunden | Falscher Pfad bei "Main file path" | Muss exakt `app/streamlit_app.py` lauten |
| `ImportError: attempted relative import` o.ä. | `sys.path`-Einträge fehlen | Alle Module verwenden bereits `sys.path.insert(...)` relativ zum Modulpfad — prüfen, ob Ordnerstruktur exakt wie in Abschnitt 1 übernommen wurde, inkl. `__init__.py`-Dateien |
| KI-Zusammenfassung: "kein API-Schlüssel konfiguriert" | Secret nicht gesetzt oder falscher Name | In Streamlit Cloud: Settings → Secrets → Key muss exakt `ANTHROPIC_API_KEY` heißen |
| "Daten aktualisieren" läuft sehr lange / Timeout | Zu viele Ticker bei begrenzter Rechenzeit auf Cloud | Für ersten Test: `stocks`-Tabelle zunächst mit wenigen Tickern (z.B. 5-10) befüllen, nicht sofort mit allen 540 |
| Keine Aktien in der Rangliste nach Update | `stocks`-Tabelle leer (keine Ticker hinterlegt) | `upsert_stock()` für gewünschte Ticker aufrufen — vollständige 540er-Liste ist laut Master-Spezifikation noch zu erstellen |
| "Connection error" bei yfinance auf Cloud | Yahoo Finance blockt Anfragen von Cloud-IP-Bereichen (bekanntes, gelegentliches Problem bei yfinance + Cloud-Hosting) | In `data/fetcher.py` ist Retry-Logik vorhanden (`FETCH_RETRY_COUNT`); falls dauerhaft: alternative Datenquelle (Stooq/EODHD) gemäß Master-Spezifikation Version 2 prüfen |
| App fällt in Schlafzustand | Keine Aktivität >einige Tage (Streamlit Cloud Free Tier) | Beim nächsten Öffnen "wacht" die App automatisch auf (kurze Ladezeit); Daten müssen danach ggf. über "Daten aktualisieren" neu geladen werden |

---

## 10. Zusammenfassung: Status nach diesem Dokument

Dieses Dokument **bereitet** das Deployment vollständig vor (Code-Basis,
`requirements.txt`, Anleitung). Es führt **kein** Deployment durch.

Die in Abschnitt 8 aufgeführten Tests sind alle als **"noch nicht
durchgeführt"** markiert, da sie externen Internetzugang bzw. externe
Accounts erfordern, die in dieser Umgebung nicht verfügbar sind.
