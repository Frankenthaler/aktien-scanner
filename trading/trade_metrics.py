"""
trading/trade_metrics.py — Einstiegsbasierte Handelskennzahlen
Aktien-Scanner V1

FIX: Validierung kursziel > stop_buy
  Wenn kursziel <= stop_buy, sind trade_chance_pct und trade_crv None.
  Verhindert negative CRV-Werte und fehlerhafte STOP-BUY-Signale (AEE-Fall).
"""

from typing import Optional


def calculate_trade_metrics(
    stop_buy: Optional[float],
    stop_loss: Optional[float],
    kursziel: Optional[float],
) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """
    Berechnet die einstiegsbasierten Handelskennzahlen.

    Returns:
        (trade_risk_pct, trade_chance_pct, trade_crv)

        Alle drei None wenn stop_buy/stop_loss fehlen oder stop_buy <= stop_loss.
        trade_chance_pct und trade_crv None wenn:
          - kursziel fehlt (ATH-Sonderfall)
          - kursziel <= stop_buy (FIX: Kursziel unterhalb Einstieg — kein positives CRV)
    """
    if stop_buy is None or stop_loss is None or stop_buy <= 0:
        return None, None, None

    risiko_abs = stop_buy - stop_loss
    if risiko_abs <= 0:
        return None, None, None

    trade_risk_pct = (risiko_abs / stop_buy) * 100

    if kursziel is None:
        return trade_risk_pct, None, None

    if kursziel <= stop_buy:
        # FIX: Kursziel unterhalb des Einstiegspreises — kein positives CRV.
        return trade_risk_pct, None, None

    chance_abs = kursziel - stop_buy
    trade_chance_pct = (chance_abs / stop_buy) * 100
    trade_crv = chance_abs / risiko_abs

    return trade_risk_pct, trade_chance_pct, trade_crv
