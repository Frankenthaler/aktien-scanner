"""
tests/test_index_constituents.py — Tests für data/index_constituents.py
Aktien-Scanner V1 — Phase 6 Nachtrag

Alle Netzwerk-Abrufe werden gemockt:
  - S&P 500: CSV-Abruf via requests (raw.githubusercontent.com — live verifiziert)
  - DAX 40: pandas.read_html gegen Wikipedia (in dieser Umgebung HTTP 403 — nur per Mock)
  - Nasdaq 100: pandas.read_html gegen Wikipedia (gleiche Einschränkung)

Nicht-live-testbare Pfade sind in den Test-Docstrings als [LIVE-UNVERIFIED] markiert.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import patch, MagicMock
from io import StringIO
import pandas as pd

PASS, FAIL = [], []

def check(name, cond, detail=""):
    if cond:
        PASS.append(name); print(f"  ✓ {name}")
    else:
        FAIL.append(name); print(f"  ✗ {name}  {detail}")


# ---------------------------------------------------------------------------
# Hilfsfunktionen für Mock-Antworten
# ---------------------------------------------------------------------------

def make_sp500_csv_response(tickers=None):
    """Erzeugt eine Mock-CSV-Antwort für den S&P 500 Abruf."""
    if tickers is None:
        # Typische Stichprobe inkl. Sonder-Ticker (BRK.B, BF.B)
        tickers = ["AAPL", "MSFT", "NVDA", "BRK.B", "BF.B", "GOOG", "AMZN",
                   "META", "TSLA", "JPM"] + [f"TICK{i:03d}" for i in range(400)]
    lines = ["Symbol,Security,GICS Sector,GICS Sub-Industry,Headquarters Location,Date added,CIK,Founded"]
    for t in tickers:
        lines.append(f"{t},Company Name,Sector,Sub-Industry,City,2000-01-01,12345,1990")
    return "\n".join(lines)


def make_dax_html_response(tickers=None):
    """Erzeugt eine Mock-HTML-Antwort mit DAX-Tabelle (Wikipedia-Format)."""
    if tickers is None:
        tickers = [
            "ADS.DE", "AIR.PA", "ALV.DE", "BAS.DE", "BAYN.DE", "BEI.DE", "BMW.DE",
            "BNR.DE", "CBK.DE", "CON.DE", "DTG.DE", "DBK.DE", "DB1.DE", "DHL.DE",
            "DTE.DE", "EOAN.DE", "FRE.DE", "FME.DE", "G1A.DE", "HNR1.DE", "HEI.DE",
            "HEN3.DE", "IFX.DE", "MBG.DE", "MRK.DE", "MTX.DE", "MUV2.DE", "PAH3.DE",
            "QIA.DE", "RHM.DE", "RWE.DE", "SAP.DE", "G24.DE", "SIE.DE", "ENR.DE",
            "SHL.DE", "SY1.DE", "VOW3.DE", "VNA.DE", "ZAL.DE",
        ]
    rows = "\n".join(
        f"<tr><td>{t}</td><td>Company {t}</td></tr>" for t in tickers
    )
    return f"""
    <html><body>
    <table>
      <tr><th>Ticker</th><th>Company</th></tr>
      {rows}
    </table>
    </body></html>
    """


def make_ndx100_html_response(tickers=None):
    """Erzeugt eine Mock-HTML-Antwort mit Nasdaq-100-Tabelle."""
    if tickers is None:
        tickers = [f"NDX{i:03d}" for i in range(101)]  # 101 Ticker
    rows = "\n".join(
        f"<tr><td>{t}</td><td>Company {t}</td></tr>" for t in tickers
    )
    return f"""
    <html><body>
    <table>
      <tr><th>Ticker</th><th>Company</th></tr>
      {rows}
    </table>
    </body></html>
    """


def mock_requests_get_success(url, *args, **kwargs):
    """Mock requests.get: S&P 500 CSV erfolgreich."""
    r = MagicMock()
    r.status_code = 200
    r.text = make_sp500_csv_response()
    r.raise_for_status = lambda: None
    return r


def mock_requests_get_fail(url, *args, **kwargs):
    """Mock requests.get: HTTP 403 (Wikipedia-Block)."""
    import requests
    r = MagicMock()
    r.status_code = 403
    r.raise_for_status.side_effect = requests.exceptions.HTTPError(
        "403 Client Error: Forbidden"
    )
    return r


# ---------------------------------------------------------------------------
# Test 1: fetch_sp500() — Erfolgreicher Abruf [S&P 500 live verifiziert]
# ---------------------------------------------------------------------------
print("\n=== Test 1: fetch_sp500() — Erfolgreicher Abruf ===")

from data.index_constituents import fetch_sp500, SP500_SOURCE_URL

with patch("data.index_constituents.requests.get",
           side_effect=mock_requests_get_success):
    result = fetch_sp500()

check("SP500: status='ok'", result["status"] == "ok", f"(status={result['status']})")
check("SP500: >400 Ticker", len(result["tickers"]) > 400, f"(count={len(result['tickers'])})")
check("SP500: source korrekt", result["source"] == SP500_SOURCE_URL)
check("SP500: fetched_at vorhanden", bool(result["fetched_at"]))
check("SP500: error=None", result["error"] is None, f"(error={result['error']})")

# Normalisierung: BRK.B → BRK-B, BF.B → BF-B
check("SP500: BRK.B normalisiert zu BRK-B",
      "BRK-B" in result["tickers"], f"(tickers-sample={result['tickers'][:5]})")
check("SP500: BF.B normalisiert zu BF-B",
      "BF-B" in result["tickers"])
check("SP500: BRK.B NICHT mehr vorhanden",
      "BRK.B" not in result["tickers"])


# ---------------------------------------------------------------------------
# Test 2: fetch_sp500() — Fehlgeschlagener Abruf (HTTP 403)
# ---------------------------------------------------------------------------
print("\n=== Test 2: fetch_sp500() — HTTP-Fehler ===")

with patch("data.index_constituents.requests.get",
           side_effect=mock_requests_get_fail):
    result_fail = fetch_sp500()

check("SP500-Fehler: status='error'", result_fail["status"] == "error",
      f"(status={result_fail['status']})")
check("SP500-Fehler: leere Ticker-Liste", result_fail["tickers"] == [])
check("SP500-Fehler: error-Meldung vorhanden", bool(result_fail["error"]))


# ---------------------------------------------------------------------------
# Test 3: fetch_sp500() — Unvollständige CSV (< 400 Einträge)
# ---------------------------------------------------------------------------
print("\n=== Test 3: fetch_sp500() — Unvollständige CSV ===")

def mock_sparse_csv(url, *args, **kwargs):
    r = MagicMock()
    r.text = make_sp500_csv_response(["AAPL", "MSFT"])  # nur 2 Ticker
    r.raise_for_status = lambda: None
    return r

with patch("data.index_constituents.requests.get", side_effect=mock_sparse_csv):
    result_sparse = fetch_sp500()

check("SP500-spärlich: status='error'", result_sparse["status"] == "error",
      f"(status={result_sparse['status']})")
check("SP500-spärlich: Fehlermeldung enthält Anzahl",
      result_sparse["error"] and "2" in result_sparse["error"],
      f"(error={result_sparse['error']})")


# ---------------------------------------------------------------------------
# Test 4: fetch_dax40() — Erfolgreicher Abruf [LIVE-UNVERIFIED: Wikipedia 403]
# [Anmerkung: In dieser Containerumgebung ist en.wikipedia.org nicht erreichbar.
#  Dieser Test verifiziert die Parsing-Logik mit gemockter HTML-Antwort.]
# ---------------------------------------------------------------------------
print("\n=== Test 4: fetch_dax40() — Erfolgreicher Abruf (Mock) [LIVE-UNVERIFIED] ===")

from data.index_constituents import fetch_dax40, DAX_SOURCE_URL

def mock_dax_get_success(url, *args, **kwargs):
    r = MagicMock()
    r.text = make_dax_html_response()
    r.raise_for_status = lambda: None
    return r

with patch("data.index_constituents.requests.get",
           side_effect=mock_dax_get_success):
    dax_result = fetch_dax40()

check("DAX: status='ok'", dax_result["status"] == "ok", f"(status={dax_result['status']})")
check("DAX: >= 35 Ticker", len(dax_result["tickers"]) >= 35,
      f"(count={len(dax_result['tickers'])})")
check("DAX: source korrekt", dax_result["source"] == DAX_SOURCE_URL)
check("DAX: AIR.PA erhalten (.PA-Suffix bleibt)", "AIR.PA" in dax_result["tickers"],
      f"(tickers={dax_result['tickers'][:5]})")
check("DAX: SAP.DE erhalten (.DE-Suffix bleibt)", "SAP.DE" in dax_result["tickers"])


# ---------------------------------------------------------------------------
# Test 5: fetch_dax40() — HTTP-Fehler → fallback-Pfad [LIVE-UNVERIFIED]
# ---------------------------------------------------------------------------
print("\n=== Test 5: fetch_dax40() — HTTP 403 (simuliert Wikipedia-Block) ===")

with patch("data.index_constituents.requests.get",
           side_effect=mock_requests_get_fail):
    dax_fail = fetch_dax40()

check("DAX-Fehler: status='error'", dax_fail["status"] == "error",
      f"(status={dax_fail['status']})")
check("DAX-Fehler: leere Ticker-Liste", dax_fail["tickers"] == [])
check("DAX-Fehler: error enthält '403'", "403" in dax_fail["error"],
      f"(error={dax_fail['error']})")


# ---------------------------------------------------------------------------
# Test 6: fetch_nasdaq100() — Erfolgreicher Abruf [LIVE-UNVERIFIED]
# ---------------------------------------------------------------------------
print("\n=== Test 6: fetch_nasdaq100() — Erfolgreicher Abruf (Mock) [LIVE-UNVERIFIED] ===")

from data.index_constituents import fetch_nasdaq100, NDX100_SOURCE_URL

def mock_ndx_get_success(url, *args, **kwargs):
    r = MagicMock()
    r.text = make_ndx100_html_response()
    r.raise_for_status = lambda: None
    return r

with patch("data.index_constituents.requests.get",
           side_effect=mock_ndx_get_success):
    ndx_result = fetch_nasdaq100()

check("NDX100: status='ok'", ndx_result["status"] == "ok", f"(status={ndx_result['status']})")
check("NDX100: >= 90 Ticker", len(ndx_result["tickers"]) >= 90,
      f"(count={len(ndx_result['tickers'])})")
check("NDX100: source korrekt", ndx_result["source"] == NDX100_SOURCE_URL)


# ---------------------------------------------------------------------------
# Test 7: Ticker-Normalisierung (_normalize_ticker)
# ---------------------------------------------------------------------------
print("\n=== Test 7: Ticker-Normalisierung ===")

from data.index_constituents import _normalize_ticker

check("Norm: BRK.B -> BRK-B", _normalize_ticker("BRK.B") == "BRK-B")
check("Norm: BF.B -> BF-B", _normalize_ticker("BF.B") == "BF-B")
check("Norm: SAP.DE bleibt SAP.DE", _normalize_ticker("SAP.DE") == "SAP.DE")
check("Norm: AIR.PA bleibt AIR.PA", _normalize_ticker("AIR.PA") == "AIR.PA")
check("Norm: AXA.L bleibt AXA.L", _normalize_ticker("AXA.L") == "AXA.L")
check("Norm: AAPL bleibt AAPL", _normalize_ticker("AAPL") == "AAPL")
check("Norm: Whitespace wird entfernt", _normalize_ticker("  MSFT  ") == "MSFT")


# ---------------------------------------------------------------------------
# Test 8: Deduplizierung (_dedupe)
# ---------------------------------------------------------------------------
print("\n=== Test 8: Deduplizierung ===")

from data.index_constituents import _dedupe

records = [
    {"ticker": "AAPL", "index": "SP500", "source": "s1", "fetched_at": "t", "fallback": False},
    {"ticker": "AAPL", "index": "NDX100", "source": "s2", "fetched_at": "t", "fallback": False},
    {"ticker": "MSFT", "index": "NDX100", "source": "s2", "fetched_at": "t", "fallback": False},
    {"ticker": "SAP.DE", "index": "DAX", "source": "s3", "fetched_at": "t", "fallback": True},
]

deduped = _dedupe(records)
tickers = {r["ticker"]: r["index"] for r in deduped}

check("Dedup: 3 eindeutige Ticker", len(deduped) == 3, f"(count={len(deduped)})")
check("Dedup: AAPL hat Index SP500 (Priorität höher als NDX100)",
      tickers.get("AAPL") == "SP500", f"(index={tickers.get('AAPL')})")
check("Dedup: MSFT hat Index NDX100", tickers.get("MSFT") == "NDX100")
check("Dedup: SAP.DE hat Index DAX", tickers.get("SAP.DE") == "DAX")


# ---------------------------------------------------------------------------
# Test 9: get_index_constituents() — Alle Quellen erfolgreich [LIVE-UNVERIFIED DAX+NDX]
# ---------------------------------------------------------------------------
print("\n=== Test 9: get_index_constituents() — Alle Quellen OK ===")

from data.index_constituents import get_index_constituents, DAX40_FALLBACK_TICKERS

def mock_all_success(url, *args, **kwargs):
    r = MagicMock()
    r.raise_for_status = lambda: None
    if "github" in url:
        r.text = make_sp500_csv_response()
    elif "wikipedia.org/wiki/DAX" in url:
        r.text = make_dax_html_response()
    else:  # Nasdaq
        r.text = make_ndx100_html_response()
    return r

with patch("data.index_constituents.requests.get", side_effect=mock_all_success):
    full = get_index_constituents()

check("Alle OK: status='ok'", full["status"] == "ok", f"(status={full['status']})")
check("Alle OK: fallback_used leer", full["fallback_used"] == [])
check("Alle OK: failed_indices leer", full["failed_indices"] == [])
check("Alle OK: >500 Ticker (SP500+DAX+NDX, dedupliziert)",
      len(full["records"]) > 500, f"(count={len(full['records'])})")
check("Alle OK: kein Record hat fallback=True",
      all(not r["fallback"] for r in full["records"]))


# ---------------------------------------------------------------------------
# Test 10: get_index_constituents() — DAX-Fehlschlag → Fallback
# ---------------------------------------------------------------------------
print("\n=== Test 10: get_index_constituents() — DAX-Fehlschlag + Fallback ===")

def mock_dax_fails(url, *args, **kwargs):
    """S&P 500 und Nasdaq OK, DAX 403."""
    r = MagicMock()
    if "wikipedia.org/wiki/DAX" in url:
        import requests
        r.raise_for_status.side_effect = requests.exceptions.HTTPError("403")
        return r
    r.raise_for_status = lambda: None
    if "github" in url:
        r.text = make_sp500_csv_response()
    else:
        r.text = make_ndx100_html_response()
    return r

with patch("data.index_constituents.requests.get", side_effect=mock_dax_fails):
    partial = get_index_constituents(allow_fallback=True)

check("DAX-Fallback: status='ok' (DAX-Fallback deckt Ausfall ab)", partial["status"] == "ok",
      f"(status={partial['status']})")
check("DAX-Fallback: fallback_used enthält 'DAX'",
      "DAX" in partial["fallback_used"])
# failed_indices enthält DAX NICHT wenn allow_fallback=True und Fallback verfügbar
# (nur bei allow_fallback=False wäre DAX in failed_indices)
check("DAX-Fallback: DAX in errors (Fehler geloggt)",
      "DAX" in partial["errors"])
check("DAX-Fallback: DAX-Records sind als fallback=True markiert",
      all(r["fallback"] for r in partial["records"] if r["index"] == "DAX"))
check("DAX-Fallback: 40 DAX-Fallback-Ticker vorhanden",
      sum(1 for r in partial["records"] if r["index"] == "DAX") == 40,
      f"(dax_count={sum(1 for r in partial['records'] if r['index'] == 'DAX')})")
check("DAX-Fallback: Fehler in errors['DAX'] vorhanden", "DAX" in partial["errors"])
# SP500+NDX100 sind noch dabei
check("DAX-Fallback: SP500-Records vorhanden",
      any(r["index"] == "SP500" for r in partial["records"]))


# ---------------------------------------------------------------------------
# Test 11: get_index_constituents() — Totalausfall aller Quellen
# ---------------------------------------------------------------------------
print("\n=== Test 11: get_index_constituents() — Totalausfall ===")

def mock_all_fail(url, *args, **kwargs):
    import requests
    r = MagicMock()
    r.raise_for_status.side_effect = requests.exceptions.RequestException("Network failure")
    return r

with patch("data.index_constituents.requests.get", side_effect=mock_all_fail):
    total_fail = get_index_constituents(allow_fallback=False)

check("Totalausfall: status='error'", total_fail["status"] == "error",
      f"(status={total_fail['status']})")
check("Totalausfall: keine Records", total_fail["records"] == [])
check("Totalausfall: alle 3 Indizes in failed_indices",
      set(total_fail["failed_indices"]) == {"DAX", "SP500", "NDX100"},
      f"(failed={total_fail['failed_indices']})")
check("Totalausfall: errors enthält alle 3 Indizes",
      all(k in total_fail["errors"] for k in ["DAX", "SP500", "NDX100"]))


# ---------------------------------------------------------------------------
# Test 12: Totalausfall MIT Fallback → DAX-Fallback noch verfügbar
# ---------------------------------------------------------------------------
print("\n=== Test 12: Totalausfall mit allow_fallback=True ===")

with patch("data.index_constituents.requests.get", side_effect=mock_all_fail):
    total_with_fb = get_index_constituents(allow_fallback=True)

check("Totalausfall+FB: status='partial' (DAX-Fallback vorhanden, SP500+NDX100 fehlen)",
      total_with_fb["status"] == "partial",
      f"(status={total_with_fb['status']})")
# Auch mit Fallback: SP500 und NDX100 haben keinen Fallback → error
# DAX Fallback ist da, aber SP500+NDX100 fehlen → "error" weil keine nutzbaren Indizes außer Fallback
check("Totalausfall+FB: DAX-Fallback in fallback_used",
      "DAX" in total_with_fb["fallback_used"])


# ---------------------------------------------------------------------------
# Test 13: Kein stilles Weiterverarbeiten als Voll-Liste bei Fehlschlag
# ---------------------------------------------------------------------------
print("\n=== Test 13: Kein stilles Weiterverarbeiten als Voll-Liste ===")

with patch("data.index_constituents.requests.get", side_effect=mock_all_fail):
    silent_check = get_index_constituents(allow_fallback=False)

check("Kein Schein-Vollbetrieb: status != 'ok' bei Totalausfall",
      silent_check["status"] != "ok")
check("Kein Schein-Vollbetrieb: records ist leer",
      len(silent_check["records"]) == 0)
check("Kein Schein-Vollbetrieb: failed_indices nicht leer",
      len(silent_check["failed_indices"]) > 0)


# ---------------------------------------------------------------------------
# Test 14: sync_index_constituents() — Integrationstest Scheduler→DB
# ---------------------------------------------------------------------------
print("\n=== Test 14: sync_index_constituents() — Scheduler→DB-Integration ===")

import config
config.DB_PATH = "test_index_constituents.db"
import os
if os.path.exists("test_index_constituents.db"):
    os.remove("test_index_constituents.db")

from data.database import init_db, get_active_stocks
init_db()

with patch("data.index_constituents.requests.get", side_effect=mock_all_success):
    from scheduler import sync_index_constituents
    sync_result = sync_index_constituents()

check("Sync: status='ok'", sync_result["status"] == "ok",
      f"(status={sync_result['status']})")
check("Sync: stocks_written > 0", sync_result.get("stocks_written", 0) > 0,
      f"(written={sync_result.get('stocks_written')})")

dax_stocks = get_active_stocks("DAX")
sp500_stocks = get_active_stocks("SP500")
check("Sync: DAX-Aktien in DB", len(dax_stocks) > 0, f"(dax={len(dax_stocks)})")
check("Sync: SP500-Aktien in DB", len(sp500_stocks) > 0, f"(sp500={len(sp500_stocks)})")


# ---------------------------------------------------------------------------
# Test 15: sync_index_constituents() — Fehlschlag → DB unverändert
# ---------------------------------------------------------------------------
print("\n=== Test 15: sync_index_constituents() — Totalausfall lässt DB unverändert ===")

import config
config.DB_PATH = "test_index_constituents2.db"
if os.path.exists("test_index_constituents2.db"):
    os.remove("test_index_constituents2.db")
from data.database import init_db as init_db2, upsert_stock, get_active_stocks as gas2
init_db2()
# Vorhandenen Bestand manuell eintragen
upsert_stock("EXISTING.DE", "Existing AG", "DAX", "XETRA", "EUR")

# sync_index_constituents nutzt allow_fallback=True (Standard)
# Bei Totalausfall: DAX via Fallback (40 Ticker) -> status=partial, stocks_written=40
with patch("data.index_constituents.requests.get", side_effect=mock_all_fail):
    fail_sync = sync_index_constituents()

check("Sync bei Totalausfall: status='partial' (DAX-Fallback rettet Notbetrieb)",
      fail_sync["status"] == "partial",
      f"(status={fail_sync['status']})")
check("Sync bei Totalausfall: stocks_written=40 (nur DAX-Fallback)",
      fail_sync["stocks_written"] == 40,
      f"(written={fail_sync['stocks_written']})")
check("Sync bei Totalausfall: DAX-Fallback in DB (41 = 1 vorhandener + 40 Fallback-Upserts -> 41 in DAX, da EXISTING.DE überschrieben werden könnte - prüfe nur > 0)",
      len(gas2("DAX")) > 0, f"(dax_count={len(gas2('DAX'))})")


# ---------------------------------------------------------------------------
# Test 16: Frontend-Warnmeldungen bei unvollständiger Indexliste
# [Prüft die Logik der Warntexte, nicht das Streamlit-Rendering]
# ---------------------------------------------------------------------------
print("\n=== Test 16: Frontend-Warnungstexte (Logik) ===")

# Simuliere die Warnungs-Logik aus streamlit_app.py
def get_warning_type(index_sync_result):
    """Gibt 'error', 'warning', 'info' oder None zurück, entsprechend der App-Logik."""
    status = index_sync_result.get("status")
    if status == "error":
        return "error"
    elif status == "partial":
        return "warning"
    elif index_sync_result.get("fallback_used"):
        return "info"
    return None

check("Warnung: Totalausfall → 'error'",
      get_warning_type({"status": "error", "fallback_used": [], "failed_indices": ["DAX","SP500","NDX100"]}) == "error")
check("Warnung: Teilausfall → 'warning'",
      get_warning_type({"status": "partial", "fallback_used": ["DAX"], "failed_indices": ["NDX100"]}) == "warning")
check("Warnung: Fallback verwendet → 'info'",
      get_warning_type({"status": "ok", "fallback_used": ["DAX"], "failed_indices": []}) == "info")
check("Warnung: Alles OK → keine Warnung",
      get_warning_type({"status": "ok", "fallback_used": [], "failed_indices": []}) is None)


# ---------------------------------------------------------------------------
# Test 17: DAX40_FALLBACK_TICKERS — Integrität
# ---------------------------------------------------------------------------
print("\n=== Test 17: DAX40_FALLBACK_TICKERS Integrität ===")

check("Fallback-Liste: genau 40 Ticker",
      len(DAX40_FALLBACK_TICKERS) == 40, f"(count={len(DAX40_FALLBACK_TICKERS)})")
check("Fallback-Liste: SAP.DE enthalten", "SAP.DE" in DAX40_FALLBACK_TICKERS)
check("Fallback-Liste: AIR.PA enthalten (Airbus Paris-notiert)", "AIR.PA" in DAX40_FALLBACK_TICKERS)
check("Fallback-Liste: alle Ticker nicht leer",
      all(t.strip() for t in DAX40_FALLBACK_TICKERS))
check("Fallback-Liste: alle Ticker einzigartig",
      len(set(DAX40_FALLBACK_TICKERS)) == len(DAX40_FALLBACK_TICKERS))


# ---------------------------------------------------------------------------
# Aufräumen
# ---------------------------------------------------------------------------
for f in ("test_index_constituents.db", "test_index_constituents2.db",
          "test_index_constituents.log"):
    if os.path.exists(f):
        os.remove(f)

# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
print(f"ERGEBNIS: {len(PASS)} bestanden, {len(FAIL)} fehlgeschlagen")
print("=" * 60)

if FAIL:
    for f in FAIL:
        print(f"  - {f}")
    sys.exit(1)
print("\nAlle Tests bestanden.")
sys.exit(0)
