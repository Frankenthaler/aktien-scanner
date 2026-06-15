"""
signals/sma200.py — Signal 1: Langfristiger Trend (SMA200)
Aktien-Scanner V1
"""

import logging
import pandas as pd

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    SMA200_PERIOD, SMA200_DATA_DAYS,
    SMA200_POSITIVE, SMA200_NEGATIVE, SMA200_POINTS,
)

logger = logging.getLogger(__name__)


def calc_sma200(prices: pd.DataFrame) -> tuple[int, float, str]:
    """
    Berechnet Signal 1 (SMA200).

    Args:
        prices: DataFrame mit Spalte 'close'/'adj_close', aufsteigend sortiert

    Returns:
        (punkte: int, sma200_wert: float | None, status: str)
        status: "positiv" | "neutral" | "negativ" | "keine_daten"
        Mindestdaten: 205 Zeilen (SMA200_DATA_DAYS)
    """
    if prices is None or len(prices) < SMA200_DATA_DAYS:
        logger.warning(f"calc_sma200: Zu wenig Daten ({0 if prices is None else len(prices)} Zeilen, "
                        f"benötigt >= {SMA200_DATA_DAYS})")
        return 0, None, "keine_daten"

    close_col = "adj_close" if "adj_close" in prices.columns else "close"
    closes = prices[close_col]

    sma200 = closes.tail(SMA200_PERIOD).mean()
    last_close = closes.iloc[-1]
    ratio = last_close / sma200

    if ratio > SMA200_POSITIVE:
        status = "positiv"
    elif ratio < SMA200_NEGATIVE:
        status = "negativ"
    else:
        status = "neutral"

    punkte = SMA200_POINTS[status]

    return punkte, float(sma200), status
