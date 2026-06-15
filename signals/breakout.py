"""
signals/breakout.py — Signal 3: Breakout (inkl. Volumenbestätigung)
Aktien-Scanner V1

Widerstandsdefinition (Master-Spezifikation V1.1, korrigiert):
  Kandidaten = alle Schlusskurse der letzten BREAKOUT_LOOKBACK Handelstage
  Für jeden Kandidaten: Anzahl Schlusskurse im Band [Kandidat×(1-BAND), Kandidat×(1+BAND)] >= MIN_TESTS
  Widerstand = höchster Kandidat, der diese Bedingung erfüllt
  Wenn kein Kandidat erfüllt: kein Breakout möglich -> Signal = 0

Breakout-Bedingungen (alle 4 müssen erfüllt sein für vollen Breakout):
  B1: Schlusskurs heute > Widerstand × BREAKOUT_MIN_CLOSE
  B2: Volumen heute > Volumen_SMA20 × BREAKOUT_VOLUME_FACTOR
  B3: Schlusskurs heute > (Tageshoch + Tagestief) / 2
  B4: Widerstand wurde mind. BREAKOUT_MIN_TESTS getestet (per Definition oben erfüllt)
"""

import logging
import pandas as pd
import numpy as np

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    BREAKOUT_LOOKBACK, BREAKOUT_BAND, BREAKOUT_MIN_TESTS,
    BREAKOUT_MIN_CLOSE, BREAKOUT_VOLUME_FACTOR, BREAKOUT_MAX_AGE,
    BREAKOUT_POINTS,
)

logger = logging.getLogger(__name__)

# Mindestdaten: BREAKOUT_LOOKBACK für Widerstand + 20 für Volumen-SMA + Puffer für Alterssuche
MIN_ROWS = BREAKOUT_LOOKBACK + 20 + BREAKOUT_MAX_AGE + 5


def find_resistance(prices: pd.DataFrame) -> float | None:
    """
    Sucht Widerstand gemäß Spezifikation.

    Args:
        prices: DataFrame mit Spalte 'close' oder 'adj_close', aufsteigend sortiert.
                Es werden die letzten BREAKOUT_LOOKBACK Zeilen verwendet.

    Returns:
        Widerstandswert (float) oder None wenn keiner gefunden.
    """
    close_col = "adj_close" if "adj_close" in prices.columns else "close"
    window = prices[close_col].tail(BREAKOUT_LOOKBACK)
    window = np.asarray(window, dtype=float).flatten()

    if len(window) < BREAKOUT_LOOKBACK:
        return None

    candidates = []
    for kandidat in window:
        lower = kandidat * (1 - BREAKOUT_BAND)
        upper = kandidat * (1 + BREAKOUT_BAND)
        tests = int(np.sum((window >= lower) & (window <= upper)))
        if tests >= BREAKOUT_MIN_TESTS:
            candidates.append(float(kandidat))

    if not candidates:
        return None

    return max(candidates)


def _check_breakout_on_day(prices: pd.DataFrame, idx: int, resistance: float,
                            volume_sma20: pd.Series) -> dict:
    """
    Prüft die 4 Breakout-Bedingungen für einen einzelnen Handelstag (Index idx).

    Returns:
        dict mit b1, b2, b3 (bool) und 'all4' (bool, B4 ist durch Widerstandsfund bereits erfüllt)
    """
    close_col = "adj_close" if "adj_close" in prices.columns else "close"

    close = prices[close_col].iloc[idx]
    high = prices["high"].iloc[idx]
    low = prices["low"].iloc[idx]
    volume = prices["volume"].iloc[idx]
    vol_sma = volume_sma20.iloc[idx]

    b1 = close > resistance * BREAKOUT_MIN_CLOSE
    b2 = (not pd.isna(vol_sma)) and volume > vol_sma * BREAKOUT_VOLUME_FACTOR
    b3 = close > (high + low) / 2

    return {"b1": b1, "b2": b2, "b3": b3, "all4": b1 and b2 and b3}


def calc_breakout(prices: pd.DataFrame) -> tuple[int, bool, int | None]:
    """
    Berechnet Signal 3 (Breakout).

    Args:
        prices: DataFrame mit Spalten 'close'/'adj_close', 'high', 'low', 'volume',
                aufsteigend nach Datum sortiert

    Returns:
        (punkte: int, breakout_flag: bool, breakout_age: int | None)
        breakout_age: Handelstage seit Breakout (0 = heute), None wenn kein Breakout

    Mindestdaten: BREAKOUT_LOOKBACK + 20 + BREAKOUT_MAX_AGE + Puffer, sonst (0, False, None)
    """
    required_cols = {"close", "high", "low", "volume"}
    available_cols = set(prices.columns) | ({"close"} if "adj_close" in prices.columns else set())

    if prices is None or len(prices) < MIN_ROWS:
        logger.warning(f"calc_breakout: Zu wenig Daten ({0 if prices is None else len(prices)} Zeilen, "
                        f"benötigt >= {MIN_ROWS})")
        return 0, False, None

    if not {"high", "low", "volume"}.issubset(prices.columns):
        logger.warning("calc_breakout: Spalten 'high','low','volume' fehlen")
        return 0, False, None

    close_col = "adj_close" if "adj_close" in prices.columns else "close"

    # Volumen-SMA20 über den gesamten Datensatz berechnen
    volume_sma20 = prices["volume"].rolling(window=20).mean()

    # Widerstand basierend auf den letzten BREAKOUT_LOOKBACK Tagen VOR dem geprüften Tag
    # Wir prüfen die letzten (BREAKOUT_MAX_AGE + 1) Tage auf einen Breakout,
    # jeweils mit dem zu diesem Zeitpunkt gültigen Widerstand.
    n = len(prices)

    for age in range(0, BREAKOUT_MAX_AGE + 1):
        idx = n - 1 - age  # 0 = heute (letzte Zeile)

        # Widerstand aus den BREAKOUT_LOOKBACK Tagen VOR diesem Tag (exklusive aktueller Tag)
        window_start = idx - BREAKOUT_LOOKBACK
        window_end = idx
        if window_start < 0:
            continue

        resistance_window = prices.iloc[window_start:window_end]
        resistance = find_resistance(resistance_window)

        if resistance is None:
            continue

        checks = _check_breakout_on_day(prices, idx, resistance, volume_sma20)

        if checks["all4"]:
            punkte = BREAKOUT_POINTS["heute_vollstaendig"] if age == 0 \
                     else BREAKOUT_POINTS["alt_vollstaendig"]
            return punkte, True, age

    # Kein vollständiger Breakout in den letzten BREAKOUT_MAX_AGE+1 Tagen.
    # Prüfen ob heute zumindest teilweise (B1+B2) erfüllt ist.
    idx = n - 1
    window_start = idx - BREAKOUT_LOOKBACK
    resistance_window = prices.iloc[window_start:idx]
    resistance = find_resistance(resistance_window)

    if resistance is not None:
        checks = _check_breakout_on_day(prices, idx, resistance, volume_sma20)
        if checks["b1"] and checks["b2"]:
            return BREAKOUT_POINTS["teilweise"], False, None
        if checks["b1"]:
            return BREAKOUT_POINTS["nur_preis"], False, None

    return BREAKOUT_POINTS["kein_breakout"], False, None
