"""
trading/trade_metrics.py — Einstiegsbasierte Handelskennzahlen
Aktien-Scanner V1

WICHTIG — Abgrenzung zum Score-System:
  scoring/scorer.py + signals/risk.py berechnen 'crv' auf Basis des
  AKTUELLEN Kurses (last_close). Dieser Wert ist Teil des gesperrten
  100-Punkte-Score-Systems (Risiko/CRV: 15 Punkte) und darf NICHT
  verändert werden.

  Für die Handelsentscheidung (Hero-Box, Ampel, Phase 2-5) ist das aber
  der falsche Bezugspunkt: Bei einem Stop-Buy-Setup wird erst beim
  Erreichen des Stop-Buy-Kurses tatsächlich Kapital eingesetzt. Risiko,
  Chance und CRV müssen sich deshalb auf den EINSTIEGSPREIS (Stop-Buy)
  beziehen, nicht auf den aktuellen Kurs.

  Diese Datei berechnet daher eine zweite, unabhängige Kennzahlen-Familie
  ('trade_risk_pct', 'trade_chance_pct', 'trade_crv'), die ausschließlich
  für die Handelsentscheidung verwendet wird und keinerlei Einfluss auf
  score_total / score_risk hat.
"""

from typing import Optional


def calculate_trade_metrics(
    stop_buy: Optional[float],
    stop_loss: Optional[float],
    kursziel: Optional[float],
) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """
    Berechnet die einstiegsbasierten Handelskennzahlen.

    Args:
        stop_buy: geplanter Einstiegspreis (Widerstand × 1,01)
        stop_loss: Stop-Loss-Kurs (aus signals/risk.py, ATR-basiert)
        kursziel: Kursziel 1 (60-Tage-Hoch), None im ATH-Sonderfall

    Returns:
        (trade_risk_pct, trade_chance_pct, trade_crv)

        - Alle drei None, wenn stop_buy oder stop_loss fehlen, oder wenn
          stop_buy <= stop_loss (ungültiges Setup — Stop-Loss darf nicht
          über dem Einstieg liegen).
        - trade_chance_pct und trade_crv zusätzlich None, wenn kein
          kursziel vorliegt (ATH-Sonderfall — Chance nicht bestimmbar,
          Risiko aber sehr wohl).
    """
    if stop_buy is None or stop_loss is None or stop_buy <= 0:
        return None, None, None

    risiko_abs = stop_buy - stop_loss
    if risiko_abs <= 0:
        # Ungültiges Setup: Stop-Loss liegt auf/über dem Einstieg.
        return None, None, None

    trade_risk_pct = (risiko_abs / stop_buy) * 100

    if kursziel is None:
        return trade_risk_pct, None, None

    chance_abs = kursziel - stop_buy
    trade_chance_pct = (chance_abs / stop_buy) * 100
    trade_crv = chance_abs / risiko_abs

    return trade_risk_pct, trade_chance_pct, trade_crv
