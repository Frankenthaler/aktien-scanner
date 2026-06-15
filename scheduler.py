"""
scheduler.py — Tägliche automatische Ausführung
Aktien-Scanner V1

Job 1 (job_europe):        täglich 18:30 MEZ — DAX-Aktien abrufen und speichern
Job 2 (job_usa_and_scores): täglich 23:00 MEZ — USA-Aktien + alle 3 Indizes
                            abrufen und speichern, danach alle Scores berechnen

Fehlerbehandlung (Pflichtenheft Abschnitt 6.11 / 8):
  Wenn ein einzelner Ticker fehlschlägt, wird geloggt und mit dem nächsten
  fortgefahren. Der gesamte Job bricht nicht ab.

Hinweis zur manuellen Aktualisierung (Master-Spezifikation V1.1):
  Die Funktionen run_europe_update() und run_usa_and_scores_update() können
  sowohl vom Scheduler als auch manuell (z.B. über die Streamlit-Schaltfläche
  "Daten aktualisieren" in Phase 4) aufgerufen werden. Der Scheduler ist
  Bestandteil der Architektur, aber nicht Voraussetzung für die
  Funktionsfähigkeit von Version 1.
"""

import logging
from datetime import date

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.schedulers.background import BackgroundScheduler

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (
    INDICES, MIN_TRADING_DAYS,
    SCHEDULE_EUROPE_HOUR, SCHEDULE_EUROPE_MINUTE,
    SCHEDULE_USA_HOUR, SCHEDULE_USA_MINUTE,
)
from data.database import (
    init_db, get_active_stocks, save_prices, save_index_prices, get_db_stats,
    upsert_stock,
)
from data.fetcher import fetch_ohlcv, fetch_index, validate_data
from data.calendar import get_last_trading_day
from data.index_constituents import get_index_constituents
from scoring.scorer import calculate_score

logger = logging.getLogger(__name__)

# Anzahl Tage, die pro Datenabruf geladen werden (Puffer über Mindesthistorie)
FETCH_DAYS = max(MIN_TRADING_DAYS + 20, 270)


# =============================================================================
# Job 1 — Europa-Daten
# =============================================================================

def job_europe() -> dict:
    """
    DAX-Aktien + DAX-Index abrufen und speichern.

    Fehlerbehandlung: Wenn ein Ticker fehlschlägt, wird geloggt und mit dem
    nächsten Ticker fortgefahren. Der Job bricht nicht ab.

    Returns:
        dict mit Statistik: {"erfolgreich": int, "fehlgeschlagen": int,
                              "fehlerhafte_ticker": list[str], "total": int}
    """
    logger.info("=== Job Europa gestartet ===")

    stats = {"erfolgreich": 0, "fehlgeschlagen": 0, "fehlerhafte_ticker": [], "total": 0}

    # Indexlisten synchronisieren (Phase-6-Nachtrag), damit die stocks-Tabelle
    # bei automatischen Läufen ebenfalls aktuell bleibt. Fehler hier sind
    # nicht fatal — bei Fehlschlag arbeitet der Job mit dem bestehenden
    # Inhalt der stocks-Tabelle weiter (sync_index_constituents() ändert
    # die Tabelle in diesem Fall nicht).
    sync_result = sync_index_constituents()
    stats["index_sync"] = sync_result

    # DAX-Index abrufen und speichern
    try:
        dax_index_ticker = INDICES["DAX"]["ticker"]
        df_index = fetch_index(dax_index_ticker, days=FETCH_DAYS)
        if validate_data(df_index, min_rows=50):
            n = save_index_prices("DAX", df_index)
            logger.info(f"DAX-Index: {n} Zeilen gespeichert")
        else:
            logger.error("DAX-Index: ungültige oder leere Daten")
    except Exception as e:
        logger.error(f"DAX-Index: Fehler beim Abruf: {e}")

    # DAX-Aktien abrufen und speichern
    dax_stocks = get_active_stocks("DAX")
    stats["total"] = len(dax_stocks)

    if not dax_stocks:
        logger.warning("job_europe: Keine aktiven DAX-Aktien in der Datenbank (stocks-Tabelle leer)")

    for stock in dax_stocks:
        ticker = stock["ticker"]
        try:
            df = fetch_ohlcv(ticker, days=FETCH_DAYS)
            if not validate_data(df, min_rows=50):
                logger.warning(f"{ticker}: Keine oder unzureichende Daten — überspringe")
                stats["fehlgeschlagen"] += 1
                stats["fehlerhafte_ticker"].append(ticker)
                continue

            n = save_prices(ticker, df)
            logger.info(f"{ticker}: {n} neue Zeilen gespeichert")
            stats["erfolgreich"] += 1

        except Exception as e:
            logger.error(f"{ticker}: Unerwarteter Fehler: {e}")
            stats["fehlgeschlagen"] += 1
            stats["fehlerhafte_ticker"].append(ticker)
            continue  # nächster Ticker, Job bricht nicht ab

    logger.info(f"=== Job Europa beendet: {stats['erfolgreich']}/{stats['total']} erfolgreich, "
                f"{stats['fehlgeschlagen']} fehlgeschlagen ===")
    if stats["fehlerhafte_ticker"]:
        logger.info(f"Fehlerhafte Ticker (Europa): {stats['fehlerhafte_ticker']}")

    return stats


# =============================================================================
# Job 2 — USA-Daten + alle Scores
# =============================================================================

def job_usa_and_scores() -> dict:
    """
    1. S&P 500 + Nasdaq 100 Aktien abrufen und speichern
    2. Alle 3 Indizes (DAX, S&P 500, Nasdaq 100) als index_prices speichern
    3. Für alle aktiven Aktien (DAX, SP500, NDX100) Score berechnen
    4. Logging: Anzahl erfolgreicher/fehlgeschlagener Berechnungen

    Fehlerbehandlung: Wenn ein einzelner Ticker fehlschlägt, wird geloggt und
    mit dem nächsten fortgefahren. Der Job bricht nicht ab.

    Returns:
        dict mit Statistik zu Datenabruf und Score-Berechnung
    """
    logger.info("=== Job USA + Scores gestartet ===")

    stats = {
        "daten": {"erfolgreich": 0, "fehlgeschlagen": 0, "fehlerhafte_ticker": [], "total": 0},
        "scores": {"erfolgreich": 0, "fehlgeschlagen": 0, "fehlerhafte_ticker": [], "total": 0},
    }

    # -------------------------------------------------------------------
    # Schritt 1: Alle 3 Indizes abrufen und speichern
    # -------------------------------------------------------------------
    for index_name, index_info in INDICES.items():
        try:
            df_index = fetch_index(index_info["ticker"], days=FETCH_DAYS)
            if validate_data(df_index, min_rows=50):
                n = save_index_prices(index_name, df_index)
                logger.info(f"Index {index_name}: {n} Zeilen gespeichert")
            else:
                logger.error(f"Index {index_name}: ungültige oder leere Daten")
        except Exception as e:
            logger.error(f"Index {index_name}: Fehler beim Abruf: {e}")

    # -------------------------------------------------------------------
    # Schritt 2: S&P 500 + Nasdaq 100 Aktien abrufen und speichern
    # -------------------------------------------------------------------
    us_stocks = get_active_stocks("SP500") + get_active_stocks("NDX100")
    stats["daten"]["total"] = len(us_stocks)

    if not us_stocks:
        logger.warning("job_usa_and_scores: Keine aktiven US-Aktien in der Datenbank "
                        "(stocks-Tabelle leer)")

    for stock in us_stocks:
        ticker = stock["ticker"]
        try:
            df = fetch_ohlcv(ticker, days=FETCH_DAYS)
            if not validate_data(df, min_rows=50):
                logger.warning(f"{ticker}: Keine oder unzureichende Daten — überspringe")
                stats["daten"]["fehlgeschlagen"] += 1
                stats["daten"]["fehlerhafte_ticker"].append(ticker)
                continue

            n = save_prices(ticker, df)
            logger.info(f"{ticker}: {n} neue Zeilen gespeichert")
            stats["daten"]["erfolgreich"] += 1

        except Exception as e:
            logger.error(f"{ticker}: Unerwarteter Fehler: {e}")
            stats["daten"]["fehlgeschlagen"] += 1
            stats["daten"]["fehlerhafte_ticker"].append(ticker)
            continue  # nächster Ticker, Job bricht nicht ab

    logger.info(f"Datenabruf USA: {stats['daten']['erfolgreich']}/{stats['daten']['total']} "
                f"erfolgreich, {stats['daten']['fehlgeschlagen']} fehlgeschlagen")

    # -------------------------------------------------------------------
    # Schritt 3: Scores für ALLE aktiven Aktien berechnen (DAX, SP500, NDX100)
    # -------------------------------------------------------------------
    all_stocks = (
        get_active_stocks("DAX")
        + get_active_stocks("SP500")
        + get_active_stocks("NDX100")
    )
    stats["scores"]["total"] = len(all_stocks)

    # Datum für die Score-Berechnung: letzter abgeschlossener US-Handelstag
    # (konservativste Wahl, da Job nach US-Handelsschluss läuft)
    score_date = get_last_trading_day("NASDAQ")

    for stock in all_stocks:
        ticker = stock["ticker"]
        index_name = stock["index_name"]

        try:
            result = calculate_score(ticker, score_date, index_name)
            if result is None:
                logger.warning(f"{ticker}: Score konnte nicht berechnet werden (keine Daten)")
                stats["scores"]["fehlgeschlagen"] += 1
                stats["scores"]["fehlerhafte_ticker"].append(ticker)
                continue

            stats["scores"]["erfolgreich"] += 1

        except Exception as e:
            logger.error(f"{ticker}: Unerwarteter Fehler bei Score-Berechnung: {e}")
            stats["scores"]["fehlgeschlagen"] += 1
            stats["scores"]["fehlerhafte_ticker"].append(ticker)
            continue  # nächster Ticker, Job bricht nicht ab

    logger.info(f"Score-Berechnung: {stats['scores']['erfolgreich']}/{stats['scores']['total']} "
                f"erfolgreich, {stats['scores']['fehlgeschlagen']} fehlgeschlagen")
    if stats["scores"]["fehlerhafte_ticker"]:
        logger.info(f"Fehlerhafte Ticker (Scores): {stats['scores']['fehlerhafte_ticker']}")

    # Datenbankgröße nach Update loggen (Pflichtenheft Abschnitt 9)
    db_stats = get_db_stats()
    logger.info(f"Datenbankgröße nach Update: {db_stats}")

    logger.info("=== Job USA + Scores beendet ===")

    return stats


# =============================================================================
# Index-Universum synchronisieren (Phase 6 Nachtrag)
# =============================================================================

# Markt/Währung je Index für upsert_stock() (Aktien selbst tragen ihre
# Börse über das yfinance-Ticker-Suffix, market/currency hier sind
# Metadaten-Defaults für die stocks-Tabelle).
_INDEX_MARKET_CURRENCY = {
    "DAX":    {"market": "XETRA",  "currency": "EUR"},
    "SP500":  {"market": "NYSE/NASDAQ", "currency": "USD"},
    "NDX100": {"market": "NASDAQ", "currency": "USD"},
}


def sync_index_constituents() -> dict:
    """
    Lädt die aktuellen Indexbestandteile (DAX 40, S&P 500, Nasdaq 100) über
    data.index_constituents.get_index_constituents() und schreibt sie in die
    stocks-Tabelle (upsert_stock je Ticker).

    Wird von run_full_update() vor den eigentlichen Datenabruf-Jobs
    aufgerufen, damit die stocks-Tabelle nach dem Deployment nicht leer
    bleibt (Pflichtenheft-Nachtrag, Phase 6).

    Fehlerbehandlung gemäß Vorgabe:
      - Bei status="error" (keine einzige Quelle lieferte Daten) wird die
        stocks-Tabelle NICHT verändert und kein "Erfolg" suggeriert.
      - Bei status="partial" werden nur die erfolgreichen Indizes
        geschrieben; die fehlenden Indizes werden klar im Rückgabewert
        ausgewiesen, damit das Frontend warnen kann.
      - Bei status="ok" inkl. DAX-Fallback wird trotzdem geschrieben, aber
        fallback_used wird durchgereicht.

    Returns:
        dict — identische Struktur wie get_index_constituents(), zusätzlich:
          - "stocks_written": int — Anzahl geschriebener/aktualisierter
                Ticker in der stocks-Tabelle
    """
    result = get_index_constituents()

    if result["status"] == "error":
        logger.error(
            "sync_index_constituents: Keine Indexliste konnte geladen "
            f"werden. Fehler: {result['errors']}. stocks-Tabelle bleibt "
            "unverändert."
        )
        result["stocks_written"] = 0
        return result

    if result["status"] == "partial":
        logger.warning(
            "sync_index_constituents: Unvollständige Indexliste — "
            f"fehlende Indizes: {result['failed_indices']} "
            f"(Fehler: {result['errors']}). Schreibe nur verfügbare "
            "Indizes in stocks-Tabelle."
        )

    if result["fallback_used"]:
        logger.warning(
            f"sync_index_constituents: Fallback-Liste verwendet für: "
            f"{result['fallback_used']}"
        )

    written = 0
    for rec in result["records"]:
        index_name = rec["index"]
        meta = _INDEX_MARKET_CURRENCY.get(index_name, {"market": "", "currency": ""})
        try:
            upsert_stock(
                ticker=rec["ticker"],
                name=rec["ticker"],  # Name nicht aus dieser Quelle verfügbar;
                                      # Anzeige-Name wird beim Datenabruf nicht
                                      # benötigt (Frontend nutzt Ticker als
                                      # Fallback-Name, siehe app/streamlit_app.py)
                index_name=index_name,
                market=meta["market"],
                currency=meta["currency"],
            )
            written += 1
        except Exception as e:
            logger.error(f"sync_index_constituents: {rec['ticker']}: Fehler beim Schreiben: {e}")

    logger.info(
        f"sync_index_constituents: {written} Ticker in stocks-Tabelle "
        f"aktualisiert (status={result['status']})"
    )

    result["stocks_written"] = written
    return result


# =============================================================================
# Manuelle Komplettaktualisierung (für Phase 4 / Streamlit-Schaltfläche)
# =============================================================================

def run_full_update() -> dict:
    """
    Führt die Indexlisten-Synchronisierung und beide Datenjobs nacheinander
    manuell aus. Wird von der Streamlit-Schaltfläche "Daten aktualisieren"
    (Phase 4) genutzt und kann auch unabhängig vom Scheduler verwendet werden.

    Ablauf:
      1. sync_index_constituents() — stocks-Tabelle aus aktuellen
         Indexlisten befüllen/aktualisieren (siehe Phase-6-Nachtrag)
      2. job_europe()
      3. job_usa_and_scores()

    Returns:
        dict mit:
          - "index_sync": Ergebnis von sync_index_constituents()
          - "europe": Ergebnis von job_europe()
          - "usa_and_scores": Ergebnis von job_usa_and_scores()
    """
    logger.info("### Manuelle Komplettaktualisierung gestartet ###")
    index_sync_result = sync_index_constituents()
    europe_result = job_europe()
    usa_result = job_usa_and_scores()
    logger.info("### Manuelle Komplettaktualisierung beendet ###")
    return {
        "index_sync": index_sync_result,
        "europe": europe_result,
        "usa_and_scores": usa_result,
    }


# =============================================================================
# Scheduler-Setup
# =============================================================================

def create_scheduler(blocking: bool = True):
    """
    Erstellt und konfiguriert den Scheduler mit beiden täglichen Jobs.

    Args:
        blocking: True für BlockingScheduler (eigener Prozess),
                  False für BackgroundScheduler (z.B. innerhalb Streamlit)

    Returns:
        Konfigurierter, aber noch nicht gestarteter Scheduler.
    """
    scheduler_cls = BlockingScheduler if blocking else BackgroundScheduler
    scheduler = scheduler_cls(timezone="Europe/Berlin")

    scheduler.add_job(
        job_europe,
        trigger="cron",
        hour=SCHEDULE_EUROPE_HOUR,
        minute=SCHEDULE_EUROPE_MINUTE,
        id="job_europe",
        name="Europa-Datenabruf (DAX)",
        misfire_grace_time=3600,
    )

    scheduler.add_job(
        job_usa_and_scores,
        trigger="cron",
        hour=SCHEDULE_USA_HOUR,
        minute=SCHEDULE_USA_MINUTE,
        id="job_usa_and_scores",
        name="USA-Datenabruf + Score-Berechnung",
        misfire_grace_time=3600,
    )

    logger.info(
        f"Scheduler konfiguriert: Europa täglich {SCHEDULE_EUROPE_HOUR:02d}:{SCHEDULE_EUROPE_MINUTE:02d} MEZ, "
        f"USA+Scores täglich {SCHEDULE_USA_HOUR:02d}:{SCHEDULE_USA_MINUTE:02d} MEZ"
    )

    return scheduler


# =============================================================================
# Einstiegspunkt
# =============================================================================

def main():
    """Startet den Scheduler als eigenständigen, blockierenden Prozess."""
    from utils.logging_config import setup_logging
    setup_logging()

    init_db()

    scheduler = create_scheduler(blocking=True)
    logger.info("Scheduler wird gestartet (blockierend). Beenden mit Strg+C.")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler beendet.")


if __name__ == "__main__":
    main()
