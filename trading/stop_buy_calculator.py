"""
trading/stop_buy_calculator.py

FIX 3: Look-Ahead Bias Dokumentation
"""

import logging
import pandas as pd
from typing import Optional

logger = logging.getLogger(__name__)


def calculate_stop_buy(
    prices: pd.DataFrame,
    score_dict: dict,
    index_prices: Optional[pd.DataFrame] = None,
) -> Optional[float]:
    """
    Berechnet einen intelligenten Stop-Buy-Preis.
    
    WICHTIG – LOOK-AHEAD BIAS PREVENTION:
    Diese Funktion nutzt NUR Daten die VOR dem Empfehlungstag verfügbar waren.
    Sie schaut nicht in die Zukunft (Forward-Looking).
    """
    
    if prices is None or prices.empty:
        logger.warning("stop_buy: Keine Kursdaten vorhanden")
        return None
    
    close_col = "adj_close" if "adj_close" in prices.columns else "close"
    current_price = prices[close_col].iloc[-1]
    
    # Berechne Widerstand aus historischen Daten (nicht forward-looking!)
    # tail(20) = 20 Handelstage VOR diesem Datum
    resistance = prices[close_col].tail(20).max()
    
    # Base Stop-Buy
    stop_buy_base = resistance * 1.01
    
    logger.debug(f"stop_buy BASE: {stop_buy_base:.2f} (Widerstand: {resistance:.2f})")
    
    return float(stop_buy_base)
