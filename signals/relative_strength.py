"""
signals/relative_strength.py — Signal 2: Relative Stärke gegenüber Index
Aktien-Scanner V1
"""

import logging
import pandas as pd

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import RS_PERIOD, RS_DATA_DAYS, RS_POINTS

logger = logging.getLogger(__name__)


def calc_rs(prices: pd.DataFrame, index_prices: pd.DataFrame) -> tuple[int, float]:
    """
    Berechnet Signal 2 (Relative Stärke).

    Args:
        prices: DataFrame mit Spalte 'close'/'adj_close' der Aktie, aufsteigend sortiert
        index_prices: DataFrame mit Spalte 'close' des Referenzindex, aufsteigend sortiert

    Returns:
        (punkte: int, rs_score: float | None)
        rs_score = Veränderung Aktie (RS_PERIOD Tage) − Veränderung Index (RS_PERIOD Tage), in %
        Mindestdaten: RS_DATA_DAYS Zeilen für Aktie UND Index, sonst (0, None)
    """
    if prices is None or len(prices) < RS_DATA_DAYS:
        logger.warning(f"calc_rs: Zu wenig Aktiendaten ({0 if prices is None else len(prices)} Zeilen, "
                        f"benötigt >= {RS_DATA_DAYS})")
        return 0, None

    if index_prices is None or len(index_prices) < RS_DATA_DAYS:
        logger.warning(f"calc_rs: Zu wenig Indexdaten ({0 if index_prices is None else len(index_prices)} Zeilen, "
                        f"benötigt >= {RS_DATA_DAYS})")
        return 0, None

    close_col = "adj_close" if "adj_close" in prices.columns else "close"
    stock_closes = prices[close_col]
    index_closes = index_prices["close"]

    # Veränderung über RS_PERIOD Handelstage
    stock_change = (stock_closes.iloc[-1] - stock_closes.iloc[-(RS_PERIOD + 1)]) \
                    / stock_closes.iloc[-(RS_PERIOD + 1)] * 100

    index_change = (index_closes.iloc[-1] - index_closes.iloc[-(RS_PERIOD + 1)]) \
                    / index_closes.iloc[-(RS_PERIOD + 1)] * 100

    rs_score = stock_change - index_change

    punkte = _score_to_points(rs_score)

    return punkte, float(rs_score)


def _score_to_points(rs_score: float) -> int:
    """Wandelt RS-Score in Punkte um anhand RS_POINTS Stufenmodell."""
    for stufe in RS_POINTS:
        if stufe["min"] is None or rs_score >= stufe["min"]:
            return stufe["points"]
    # Sollte nie erreicht werden, da letzte Stufe min=None hat
    return 0
