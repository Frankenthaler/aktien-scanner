"""
signals/risk.py — Signal 5: Risiko / Chance-Risiko-Verhältnis (ATR-basiert)
Aktien-Scanner V1
"""

import logging
import pandas as pd
import numpy as np

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    ATR_PERIOD, ATR_DATA_DAYS, ATR_MULTIPLIER,
    CRV_LOOKBACK, CRV_FALLBACK_POINTS, RISK_POINTS,
)

logger = logging.getLogger(__name__)

MIN_ROWS_RISK = max(ATR_DATA_DAYS, CRV_LOOKBACK + 1)


def calc_atr(prices: pd.DataFrame) -> float | None:
    """
    Berechnet ATR14 (Average True Range über ATR_PERIOD Tage).

    Args:
        prices: DataFrame mit Spalten 'high', 'low', 'close'/'adj_close',
                aufsteigend sortiert. Mindestdaten: ATR_DATA_DAYS Zeilen.

    Returns:
        ATR-Wert (float) oder None bei zu wenig Daten.
    """
    if prices is None or len(prices) < ATR_DATA_DAYS:
        logger.warning(f"calc_atr: Zu wenig Daten ({0 if prices is None else len(prices)} Zeilen, "
                        f"benötigt >= {ATR_DATA_DAYS})")
        return None

    if not {"high", "low"}.issubset(prices.columns):
        logger.warning("calc_atr: Spalten 'high','low' fehlen")
        return None

    close_col = "adj_close" if "adj_close" in prices.columns else "close"

    high = prices["high"]
    low = prices["low"]
    close = prices[close_col]
    prev_close = close.shift(1)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()

    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = true_range.tail(ATR_PERIOD).mean()

    return float(atr)


def calc_risk(prices: pd.DataFrame) -> tuple[int, float | None, float | None,
                                              float | None, float | None, float | None]:
    """
    Berechnet Signal 5 (Risiko/CRV).

    Args:
        prices: DataFrame mit Spalten 'high', 'low', 'close'/'adj_close',
                aufsteigend sortiert.

    Returns:
        (punkte, stop_loss, crv, atr14, atr_ratio, kursziel)
        Bei zu wenig Daten: (0, None, None, None, None, None)
        Sonderfall kein Kursziel (60-Tage-Hoch <= aktueller Kurs):
            crv = None, punkte = CRV_FALLBACK_POINTS
    """
    if prices is None or len(prices) < MIN_ROWS_RISK:
        logger.warning(f"calc_risk: Zu wenig Daten ({0 if prices is None else len(prices)} Zeilen, "
                        f"benötigt >= {MIN_ROWS_RISK})")
        return 0, None, None, None, None, None

    close_col = "adj_close" if "adj_close" in prices.columns else "close"
    last_close = prices[close_col].iloc[-1]

    atr14 = calc_atr(prices)
    if atr14 is None or atr14 <= 0:
        logger.warning("calc_risk: ATR konnte nicht berechnet werden")
        return 0, None, None, None, None, None

    stop_loss = last_close - (atr14 * ATR_MULTIPLIER)
    risiko = atr14 * ATR_MULTIPLIER
    atr_ratio = (atr14 / last_close) * 100

    # Kursziel: höchster Kurs der letzten CRV_LOOKBACK Tage (exkl. heute), falls > aktueller Kurs
    lookback_window = prices[close_col].iloc[-(CRV_LOOKBACK + 1):-1]
    hoechstkurs_60 = lookback_window.max() if len(lookback_window) > 0 else None

    if hoechstkurs_60 is None or hoechstkurs_60 <= last_close:
        # Sonderfall: kein Kursziel definierbar (z.B. Allzeithoch)
        return CRV_FALLBACK_POINTS, float(stop_loss), None, float(atr14), float(atr_ratio), None

    kursziel = float(hoechstkurs_60)
    crv = (kursziel - last_close) / risiko

    punkte = _crv_to_points(crv, atr_ratio)

    return punkte, float(stop_loss), float(crv), float(atr14), float(atr_ratio), kursziel


def _crv_to_points(crv: float, atr_ratio: float) -> int:
    """Wandelt CRV + ATR-Ratio in Punkte um anhand RISK_POINTS Stufenmodell."""
    for stufe in RISK_POINTS:
        crv_min = stufe["crv_min"]
        atr_max = stufe["atr_max"]

        if crv_min is None:
            return stufe["points"]

        crv_ok = crv >= crv_min
        atr_ok = (atr_max is None) or (atr_ratio <= atr_max)

        if crv_ok and atr_ok:
            return stufe["points"]

    return 0
