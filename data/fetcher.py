"""
data/fetcher.py — Abstrakte Datenschicht
Aktien-Scanner V1

Kein anderes Modul importiert yfinance direkt.
Alle Datenabrufe laufen über dieses Modul.
"""

import time
import logging
from datetime import date

import pandas as pd
import yfinance as yf

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    FETCH_RETRY_COUNT,
    FETCH_RETRY_WAIT,
    FETCH_REQUEST_PAUSE,
    MIN_TRADING_DAYS,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Interne Hilfsfunktion
# =============================================================================

def _download(ticker: str, period: str = "2y") -> pd.DataFrame:
    """
    Interne Funktion: yfinance-Download mit Retry-Logik.
    Gibt normalisierten DataFrame zurück oder leeren DataFrame bei Fehler.
    """
    for attempt in range(1, FETCH_RETRY_COUNT + 1):
        try:
            time.sleep(FETCH_REQUEST_PAUSE)
            raw = yf.download(
                ticker,
                period=period,
                auto_adjust=True,
                progress=False,
                threads=False,
            )

            if raw.empty:
                logger.warning(f"{ticker}: Leerer DataFrame (Versuch {attempt})")
                if attempt < FETCH_RETRY_COUNT:
                    time.sleep(FETCH_RETRY_WAIT)
                continue

            # Spalten normalisieren
            raw.columns = [c[0].lower() if isinstance(c, tuple) else c.lower()
                           for c in raw.columns]
            raw = raw.rename(columns={"close": "close"})

            # adj_close = close (yfinance auto_adjust=True liefert bereits adjustierte Kurse)
            raw["adj_close"] = raw["close"]
            raw.index.name = "date"
            raw = raw.reset_index()
            raw["date"] = pd.to_datetime(raw["date"]).dt.date

            return raw

        except Exception as e:
            logger.warning(f"{ticker}: Fehler Versuch {attempt}: {e}")
            if attempt < FETCH_RETRY_COUNT:
                time.sleep(FETCH_RETRY_WAIT)

    logger.error(f"{ticker}: Alle {FETCH_RETRY_COUNT} Versuche fehlgeschlagen.")
    return _empty_ohlcv()


def _empty_ohlcv() -> pd.DataFrame:
    """Leerer DataFrame mit korrekten Spalten."""
    return pd.DataFrame(columns=["date","open","high","low","close","volume","adj_close"])


# =============================================================================
# Öffentliche Funktionen
# =============================================================================

def fetch_ohlcv(ticker: str, days: int = 250) -> pd.DataFrame:
    """
    Gibt OHLCV-Daten für die letzten N Handelstage zurück.

    Args:
        ticker: Aktien-Ticker (z.B. "SAP.DE", "AAPL")
        days: Gewünschte Anzahl Handelstage

    Returns:
        DataFrame mit Spalten: date, open, high, low, close, volume, adj_close
        Bei Fehler: leerer DataFrame mit korrekten Spalten
    """
    # 2 Jahre reichen für alle Signale (max. 210 Tage Mindesthistorie)
    df = _download(ticker, period="2y")

    if df.empty:
        return df

    # Auf gewünschte Anzahl Tage kürzen
    if len(df) > days:
        df = df.tail(days).reset_index(drop=True)

    return df


def fetch_index(index_ticker: str, days: int = 250) -> pd.DataFrame:
    """
    Wie fetch_ohlcv, aber für Indizes.

    Args:
        index_ticker: Index-Ticker (z.B. "^GDAXI", "^GSPC")
        days: Gewünschte Anzahl Handelstage

    Returns:
        DataFrame mit Spalten: date, close
    """
    df = _download(index_ticker, period="2y")

    if df.empty:
        return pd.DataFrame(columns=["date", "close"])

    df = df[["date", "close"]].copy()

    if len(df) > days:
        df = df.tail(days).reset_index(drop=True)

    return df


def validate_data(df: pd.DataFrame, min_rows: int) -> bool:
    """
    Prüft ob DataFrame ausreichend Daten enthält.

    Args:
        df: Zu prüfender DataFrame
        min_rows: Mindestanzahl Zeilen

    Returns:
        True wenn valide, False sonst
    """
    if df is None or df.empty:
        return False
    if len(df) < min_rows:
        return False
    # Pflichtfelder prüfen
    required = {"date", "close"}
    if not required.issubset(set(df.columns)):
        return False
    return True


# =============================================================================
# Ticker-Testlauf
# =============================================================================

def test_ticker(ticker: str) -> dict:
    """
    Testet ob ein Ticker abrufbar ist und ausreichend Daten hat.
    Für den Testlauf vor dem ersten echten Betrieb.

    Returns:
        dict mit keys: ticker, ok, rows, error
    """
    try:
        df = fetch_ohlcv(ticker, days=MIN_TRADING_DAYS + 20)
        if df.empty:
            return {"ticker": ticker, "ok": False, "rows": 0, "error": "Leerer DataFrame"}
        if len(df) < MIN_TRADING_DAYS:
            return {"ticker": ticker, "ok": False, "rows": len(df),
                    "error": f"Nur {len(df)} Tage (Minimum: {MIN_TRADING_DAYS})"}
        return {"ticker": ticker, "ok": True, "rows": len(df), "error": None}
    except Exception as e:
        return {"ticker": ticker, "ok": False, "rows": 0, "error": str(e)}
