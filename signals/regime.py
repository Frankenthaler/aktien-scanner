"""
signals/regime.py — Signal 4: Marktregime
Aktien-Scanner V1
"""

import logging
import pandas as pd

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    REGIME_SMA_PERIOD, REGIME_DATA_DAYS,
    REGIME_POSITIVE, REGIME_NEGATIVE, REGIME_POINTS,
)

logger = logging.getLogger(__name__)


def calc_regime(index_prices: pd.DataFrame) -> tuple[int, str]:
    """
    Berechnet Signal 4 (Marktregime).

    Args:
        index_prices: DataFrame mit Spalte 'close' des Referenzindex, aufsteigend sortiert

    Returns:
        (punkte: int, regime_status: str)
        regime_status: "positiv" | "neutral" | "negativ" | "keine_daten"
        Mindestdaten: REGIME_DATA_DAYS Zeilen, sonst (0, "keine_daten")
    """
    if index_prices is None or len(index_prices) < REGIME_DATA_DAYS:
        logger.warning(f"calc_regime: Zu wenig Indexdaten "
                        f"({0 if index_prices is None else len(index_prices)} Zeilen, "
                        f"benötigt >= {REGIME_DATA_DAYS})")
        return 0, "keine_daten"

    closes = index_prices["close"]
    sma200 = closes.tail(REGIME_SMA_PERIOD).mean()
    last_close = closes.iloc[-1]
    ratio = last_close / sma200

    if ratio > REGIME_POSITIVE:
        status = "positiv"
    elif ratio < REGIME_NEGATIVE:
        status = "negativ"
    else:
        status = "neutral"

    punkte = REGIME_POINTS[status]

    return punkte, status
