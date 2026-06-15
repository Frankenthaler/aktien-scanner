"""
signals/filter_sma50.py — Hard Filter SMA50
Aktien-Scanner V1

Aktien unter SMA50 × Buffer werden nicht bewertet.
"""

import logging
import pandas as pd

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import SMA50_PERIOD, SMA50_BUFFER

logger = logging.getLogger(__name__)


def check_sma50(prices: pd.DataFrame) -> tuple[bool, float]:
    """
    Berechnet SMA50 und prüft Hard Filter.

    Args:
        prices: DataFrame mit Spalte 'close' oder 'adj_close', aufsteigend nach Datum sortiert

    Returns:
        (bestanden: bool, sma50_wert: float | None)
        Bedingung: letzter Kurs > SMA50 × SMA50_BUFFER
        Mindestdaten: 52 Zeilen, sonst (False, None)
    """
    if prices is None or len(prices) < (SMA50_PERIOD + 2):
        logger.warning(f"check_sma50: Zu wenig Daten ({0 if prices is None else len(prices)} Zeilen, "
                        f"benötigt >= {SMA50_PERIOD + 2})")
        return False, None

    close_col = "adj_close" if "adj_close" in prices.columns else "close"
    closes = prices[close_col]

    sma50 = closes.tail(SMA50_PERIOD).mean()
    last_close = closes.iloc[-1]

    bestanden = bool(last_close > (sma50 * SMA50_BUFFER))

    return bestanden, float(sma50)
