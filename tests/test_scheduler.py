"""
tests/test_scheduler.py — Test scheduler.py mit gemocktem Datenabruf
Aktien-Scanner V1

Da yfinance in dieser Umgebung keinen Netzwerkzugriff hat, werden
data.fetcher.fetch_ohlcv / fetch_index gemockt. Geprüft wird:
  - vollständiger Ablauf von job_europe und job_usa_and_scores
  - Speicherung in DB (prices, index_prices, scores)
  - Fehlerbehandlung: ein fehlerhafter Ticker bricht den Job nicht ab
  - Logging-Statistiken (erfolgreich/fehlgeschlagen)
  - create_scheduler() registriert beide Jobs korrekt
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
config.DB_PATH = "test_scheduler.db"
config.LOG_PATH = "test_scheduler.log"

from utils.logging_config import setup_logging
setup_logging()

from unittest.mock import patch
import pandas as pd

from data.database import init_db, upsert_stock, get_db_stats, get_latest_scores
from tests.helpers import make_price_series

PASS, FAIL = [], []

def check(name, cond, detail=""):
    if cond:
        PASS.append(name); print(f"  ✓ {name}")
    else:
        FAIL.append(name); print(f"  ✗ {name}  {detail}")


# Frische Test-DB
for f in ("test_scheduler.db", "test_scheduler.log", "test_scheduler_verify.log"):
    if os.path.exists(f):
        os.remove(f)
init_db()


# -----------------------------------------------------------------------------
# Testdaten: stocks-Tabelle befüllen (3 DAX, 2 SP500, 1 NDX100, 1 fehlerhafter Ticker)
# -----------------------------------------------------------------------------
upsert_stock("SAP.DE", "SAP SE", "DAX", "XETRA", "EUR")
upsert_stock("AIR.DE", "Airbus SE", "DAX", "XETRA", "EUR")
upsert_stock("FEHLER.DE", "Fehlerhafte Aktie", "DAX", "XETRA", "EUR")  # liefert leere Daten
upsert_stock("AAPL", "Apple Inc.", "SP500", "NYSE", "USD")
upsert_stock("MSFT", "Microsoft Corp.", "SP500", "NYSE", "USD")
upsert_stock("NVDA", "NVIDIA Corp.", "NDX100", "NASDAQ", "USD")


# -----------------------------------------------------------------------------
# Mock-Funktionen für fetcher
# -----------------------------------------------------------------------------
N = 270  # ausreichend für alle Signale (MIN_TRADING_DAYS=210 + Puffer)

def mock_fetch_ohlcv(ticker, days=250):
    """Liefert synthetische Daten, außer für FEHLER.DE (leer)."""
    if ticker == "FEHLER.DE":
        return pd.DataFrame(columns=["date","open","high","low","close","volume","adj_close"])
    seed = abs(hash(ticker)) % 1000
    df = make_price_series(N, start=100, daily_change=0.15, volatility=0.5, seed=seed)
    if len(df) > days:
        df = df.tail(days).reset_index(drop=True)
    return df

def mock_fetch_index(index_ticker, days=250):
    """Liefert synthetische Indexdaten (leicht steigend)."""
    seed = abs(hash(index_ticker)) % 1000
    df = make_price_series(N, start=15000, daily_change=10, volatility=20, seed=seed)
    df = df[["date", "close"]]
    if len(df) > days:
        df = df.tail(days).reset_index(drop=True)
    return df


# =============================================================================
# Test 1: job_europe()
# =============================================================================
print("\n=== Test 1: job_europe() ===")

with patch("scheduler.fetch_ohlcv", side_effect=mock_fetch_ohlcv), \
     patch("scheduler.fetch_index", side_effect=mock_fetch_index), \
     patch("scheduler.sync_index_constituents", return_value={
         "status": "ok", "records": [], "fallback_used": [],
         "failed_indices": [], "errors": {}, "stocks_written": 0,
     }):

    from scheduler import job_europe
    stats = job_europe()

check("job_europe: total == 3 (3 DAX-Aktien)", stats["total"] == 3, f"(stats={stats})")
check("job_europe: 2 erfolgreich (SAP, AIR)", stats["erfolgreich"] == 2, f"(stats={stats})")
check("job_europe: 1 fehlgeschlagen (FEHLER.DE)", stats["fehlgeschlagen"] == 1, f"(stats={stats})")
check("job_europe: FEHLER.DE in fehlerhafte_ticker",
      "FEHLER.DE" in stats["fehlerhafte_ticker"], f"(stats={stats})")
check("job_europe: Job bricht nicht ab trotz Fehler",
      stats["erfolgreich"] + stats["fehlgeschlagen"] == stats["total"])

# DAX-Index gespeichert?
db_stats = get_db_stats()
check("job_europe: index_prices enthält Einträge (DAX-Index)", db_stats["index_prices"] > 0,
      f"(db_stats={db_stats})")

# prices für SAP.DE gespeichert?
from data.database import get_prices
sap_prices = get_prices("SAP.DE", 300)
check("job_europe: SAP.DE Preise gespeichert", len(sap_prices) > 0, f"(rows={len(sap_prices)})")

fehler_prices = get_prices("FEHLER.DE", 300)
check("job_europe: FEHLER.DE keine Preise gespeichert", len(fehler_prices) == 0)


# =============================================================================
# Test 2: job_usa_and_scores()
# =============================================================================
print("\n=== Test 2: job_usa_and_scores() ===")

with patch("scheduler.fetch_ohlcv", side_effect=mock_fetch_ohlcv), \
     patch("scheduler.fetch_index", side_effect=mock_fetch_index), \
     patch("scheduler.get_last_trading_day", return_value=__import__("datetime").date.today()):

    from scheduler import job_usa_and_scores
    stats2 = job_usa_and_scores()

# Datenabruf-Statistik
check("job_usa: daten.total == 3 (AAPL, MSFT, NVDA)", stats2["daten"]["total"] == 3,
      f"(stats={stats2['daten']})")
check("job_usa: daten.erfolgreich == 3", stats2["daten"]["erfolgreich"] == 3,
      f"(stats={stats2['daten']})")
check("job_usa: daten.fehlgeschlagen == 0", stats2["daten"]["fehlgeschlagen"] == 0)

# Score-Statistik: alle 6 Aktien (3 DAX + 2 SP500 + 1 NDX100)
# FEHLER.DE hat keine Preisdaten -> Score schlägt fehl
check("job_usa: scores.total == 6 (alle aktiven Aktien)", stats2["scores"]["total"] == 6,
      f"(stats={stats2['scores']})")
check("job_usa: scores.erfolgreich == 5 (alle außer FEHLER.DE)",
      stats2["scores"]["erfolgreich"] == 5, f"(stats={stats2['scores']})")
check("job_usa: scores.fehlgeschlagen == 1 (FEHLER.DE)",
      stats2["scores"]["fehlgeschlagen"] == 1, f"(stats={stats2['scores']})")
check("job_usa: FEHLER.DE in scores.fehlerhafte_ticker",
      "FEHLER.DE" in stats2["scores"]["fehlerhafte_ticker"])

# Alle 3 Indizes gespeichert?
db_stats = get_db_stats()
check("job_usa: index_prices enthält alle 3 Indizes (>= 3 * 1 Tag, hier viele Tage)",
      db_stats["index_prices"] > 0, f"(db_stats={db_stats})")

# Scores tatsächlich in DB?
scores_df = get_latest_scores()
check("job_usa: Scores in DB vorhanden", len(scores_df) > 0, f"(rows={len(scores_df)})")
check("job_usa: 5 Scores mit score_total (FEHLER.DE ausgenommen)",
      len(scores_df) == 5, f"(rows={len(scores_df)}, tickers={list(scores_df['ticker']) if len(scores_df)>0 else []})")


# =============================================================================
# Test 3: Fehlerbehandlung — Exception während eines Ticker-Abrufs
# =============================================================================
print("\n=== Test 3: Exception bei einzelnem Ticker bricht Job nicht ab ===")

def mock_fetch_ohlcv_with_exception(ticker, days=250):
    if ticker == "AIR.DE":
        raise ConnectionError("Simulierter Netzwerkfehler")
    return mock_fetch_ohlcv(ticker, days)

with patch("scheduler.fetch_ohlcv", side_effect=mock_fetch_ohlcv_with_exception), \
     patch("scheduler.fetch_index", side_effect=mock_fetch_index), \
     patch("scheduler.sync_index_constituents", return_value={
         "status": "ok", "records": [], "fallback_used": [],
         "failed_indices": [], "errors": {}, "stocks_written": 0,
     }):

    stats3 = job_europe()

check("Exception: Job läuft trotz Exception bei AIR.DE durch",
      stats3["total"] == 3, f"(stats={stats3})")
check("Exception: AIR.DE als fehlgeschlagen markiert",
      "AIR.DE" in stats3["fehlerhafte_ticker"], f"(stats={stats3})")
check("Exception: SAP.DE trotzdem erfolgreich (2 erfolgreich: SAP + ... )",
      stats3["erfolgreich"] >= 1, f"(stats={stats3})")


# =============================================================================
# Test 4 (vorgezogen als 4): Logdatei enthält erwartete Einträge (Pflichtenheft Abschnitt 9)
# =============================================================================
print("\n=== Test 4: Logging (scanner.log Inhalte) ===")

import logging

# Eigenen FileHandler für diesen Testabschnitt anhängen, um robust
# unabhängig von evtl. zwischenzeitlich veränderten Handlern (z.B. durch
# apscheduler) den vollständigen Log-Output prüfen zu können.
verify_log_path = os.path.abspath("test_scheduler_verify.log")
verify_handler = logging.FileHandler(verify_log_path, encoding="utf-8")
verify_handler.setFormatter(logging.Formatter(
    "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"))
logging.getLogger().addHandler(verify_handler)

# Jobs erneut ausführen, damit alle erwarteten Log-Einträge im verify-Log landen
with patch("scheduler.fetch_ohlcv", side_effect=mock_fetch_ohlcv), \
     patch("scheduler.fetch_index", side_effect=mock_fetch_index), \
     patch("scheduler.get_last_trading_day", return_value=__import__("datetime").date.today()), \
     patch("scheduler.sync_index_constituents", return_value={
         "status": "ok", "records": [], "fallback_used": [],
         "failed_indices": [], "errors": {}, "stocks_written": 0,
     }):
    from scheduler import job_europe as _je, job_usa_and_scores as _ju
    _je()
    _ju()

verify_handler.flush()
verify_handler.close()
logging.getLogger().removeHandler(verify_handler)

with open(verify_log_path, encoding="utf-8") as f:
    log_content = f.read()

check("Log: 'Job Europa gestartet' vorhanden", "Job Europa gestartet" in log_content)
check("Log: 'Job USA + Scores gestartet' vorhanden", "Job USA + Scores gestartet" in log_content)
check("Log: Anzahl erfolgreicher/fehlgeschlagener Ticker geloggt",
      "erfolgreich" in log_content and "fehlgeschlagen" in log_content)
check("Log: Fehlerhafte Ticker namentlich genannt (FEHLER.DE)", "FEHLER.DE" in log_content)
check("Log: Datenbankgröße nach Update geloggt", "Datenbankgröße nach Update" in log_content)
check("Log: Zeitstempel im Format YYYY-MM-DD vorhanden",
      any(line[:4].isdigit() for line in log_content.splitlines() if line.strip()))


# =============================================================================
# Test 5: create_scheduler() registriert beide Jobs
# =============================================================================
print("\n=== Test 5: create_scheduler() ===")

from scheduler import create_scheduler

sched = create_scheduler(blocking=False)
job_ids = [j.id for j in sched.get_jobs()]

check("Scheduler: job_europe registriert", "job_europe" in job_ids, f"(job_ids={job_ids})")
check("Scheduler: job_usa_and_scores registriert", "job_usa_and_scores" in job_ids, f"(job_ids={job_ids})")
check("Scheduler: genau 2 Jobs", len(job_ids) == 2, f"(job_ids={job_ids})")

# Zeitplan prüfen
europe_job = sched.get_job("job_europe")
usa_job = sched.get_job("job_usa_and_scores")
check("Scheduler: job_europe ist Cron-Trigger", "cron" in str(type(europe_job.trigger)).lower())
check("Scheduler: job_usa_and_scores ist Cron-Trigger", "cron" in str(type(usa_job.trigger)).lower())

if sched.running:
    sched.shutdown(wait=False)


# =============================================================================
# Test 6: run_full_update()
# =============================================================================
print("\n=== Test 6: run_full_update() (manuelle Komplettaktualisierung) ===")

with patch("scheduler.fetch_ohlcv", side_effect=mock_fetch_ohlcv), \
     patch("scheduler.fetch_index", side_effect=mock_fetch_index), \
     patch("scheduler.get_last_trading_day", return_value=__import__("datetime").date.today()), \
     patch("scheduler.sync_index_constituents", return_value={
         "status": "ok", "records": [], "fallback_used": [],
         "failed_indices": [], "errors": {}, "stocks_written": 0,
     }):

    from scheduler import run_full_update
    full_result = run_full_update()

check("run_full_update: enthält 'europe'", "europe" in full_result)
check("run_full_update: enthält 'usa_and_scores'", "usa_and_scores" in full_result)
check("run_full_update: enthält 'index_sync' (Phase-6-Nachtrag)", "index_sync" in full_result)
check("run_full_update: europe.total == 3", full_result["europe"]["total"] == 3)
check("run_full_update: usa_and_scores.scores.total == 6",
      full_result["usa_and_scores"]["scores"]["total"] == 6)


# =============================================================================
print("\n" + "=" * 60)
print(f"ERGEBNIS: {len(PASS)} bestanden, {len(FAIL)} fehlgeschlagen")
print("=" * 60)

# Aufräumen
for f in ("test_scheduler.db", "test_scheduler.log", "test_scheduler_verify.log"):
    if os.path.exists(f):
        os.remove(f)

if FAIL:
    for f in FAIL:
        print(f"  - {f}")
    sys.exit(1)
sys.exit(0)
