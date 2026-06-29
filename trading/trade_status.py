"""
trading/trade_status.py — Handelsstatus-Entscheidungsebene
Aktien-Scanner V1

FIX 1: CRV-Validierung — STOP-BUY erfordert trade_crv >= STOPBUY_MIN_CRV.
FIX 2: EMA20-Abstandsregel — STOP-BUY nur wenn Kurs <= EMA20 + MAX_DISTANCE_EMA20_PCT.
"""

from typing import Optional

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    TRADE_STATUS_KAUFEN_MIN_SCORE, TRADE_STATUS_KAUFEN_MAX_SIGNALALTER,
    TRADE_STATUS_KAUFEN_MIN_CRV, TRADE_STATUS_STOPBUY_MIN_SCORE,
    TRADE_STATUS_STOPBUY_MIN_CRV,
    TRADE_STATUS_BEOBACHTEN_MIN_SCORE, TRADE_STATUS_VERPASST_BUFFER_PCT,
    TRADE_STATUS_AMPEL, TRADE_STATUS_RANK, TRADE_CRV_COLOR_STUFEN,
    MAX_DISTANCE_EMA20_PCT, SETUP_SB_MAX_ABSTAND_PCT,
)

VERWERFEN = "VERWERFEN"
BEOBACHTEN = "BEOBACHTEN"
STOP_BUY = "STOP-BUY"
KAUFEN = "KAUFEN"
VERPASST = "VERPASST"


def has_required_trade_fields(detail: dict) -> bool:
    """Prüft ob Pflichfelder für Handelsentscheidung vorhanden sind."""
    return (
        detail.get("price_close") is not None
        and detail.get("stop_buy") is not None
        and detail.get("stop_loss") is not None
    )


def is_valid_stopbuy_setup(detail: dict) -> bool:
    """
    FIX 1+2: Prüft Mindestanforderungen für STOP-BUY.

    1. Stop-Buy > aktueller Kurs (nicht getriggert)
    2. trade_crv nicht None
    3. trade_crv >= TRADE_STATUS_STOPBUY_MIN_CRV
    4. EMA20-Abstand <= MAX_DISTANCE_EMA20_PCT (fail-open wenn ema20 fehlt)
    """
    price_close = detail.get("price_close")
    stop_buy = detail.get("stop_buy")
    trade_crv = detail.get("trade_crv")

    if price_close is None or stop_buy is None:
        return False
    if stop_buy <= price_close:
        return False

    # Stop-Buy darf nicht mehr als SETUP_SB_MAX_ABSTAND_PCT über aktuellem Kurs liegen
    # (verhindert unrealistische Einstiegsniveaus bei weit gelaufenen Aktien)
    sb_abstand_pct = (stop_buy - price_close) / price_close * 100
    if sb_abstand_pct > SETUP_SB_MAX_ABSTAND_PCT:
        return False
    if trade_crv is None:
        return False
    if trade_crv < TRADE_STATUS_STOPBUY_MIN_CRV:
        return False

    # EMA20-Abstandsregel (FIX 2) — fail-open wenn ema20 nicht berechnet
    ema20 = detail.get("ema20")
    if ema20 is not None and ema20 > 0:
        distance_pct = ((price_close - ema20) / ema20) * 100
        if distance_pct > MAX_DISTANCE_EMA20_PCT:
            return False

    return True


def ema20_distance_pct(detail: dict) -> Optional[float]:
    """Prozentualer Abstand Kurs zu EMA20. Positiv = Kurs über EMA20."""
    price_close = detail.get("price_close")
    ema20 = detail.get("ema20")
    if price_close is None or ema20 is None or ema20 <= 0:
        return None
    return ((price_close - ema20) / ema20) * 100


def determine_trade_status(detail: dict) -> str:
    """
    Bestimmt den Handelsstatus.

    Priorität:
      1. VERWERFEN  — score < Mindest
      2. VERPASST   — Kurs >= Stop-Buy + Buffer
      3. KAUFEN     — Top-Score, frischer Breakout, gutes CRV, getriggert
      4. STOP-BUY   — guter Score, gültiges Setup (CRV+EMA20), nicht getriggert
      5. BEOBACHTEN — alles Übrige mit Mindest-Score
    """
    score_total = detail.get("score_total")
    breakout_age = detail.get("breakout_age")
    trade_crv = detail.get("trade_crv")
    price_close = detail.get("price_close")
    stop_buy = detail.get("stop_buy")

    if score_total is None or score_total < TRADE_STATUS_BEOBACHTEN_MIN_SCORE:
        return VERWERFEN

    triggered: Optional[bool] = None
    if price_close is not None and stop_buy is not None and stop_buy > 0:
        triggered = price_close >= stop_buy
        ueberschreitung_pct = (price_close - stop_buy) / stop_buy * 100
        if triggered and ueberschreitung_pct >= TRADE_STATUS_VERPASST_BUFFER_PCT:
            return VERPASST

    if (
        score_total >= TRADE_STATUS_KAUFEN_MIN_SCORE
        and breakout_age is not None
        and breakout_age <= TRADE_STATUS_KAUFEN_MAX_SIGNALALTER
        and trade_crv is not None
        and trade_crv >= TRADE_STATUS_KAUFEN_MIN_CRV
        and triggered is True
    ):
        return KAUFEN

    if (
        score_total >= TRADE_STATUS_STOPBUY_MIN_SCORE
        and triggered is False
        and is_valid_stopbuy_setup(detail)
    ):
        return STOP_BUY

    return BEOBACHTEN


def ampel_for_status(status: str) -> str:
    return TRADE_STATUS_AMPEL.get(status, "gelb")


def rank_for_status(status: str) -> int:
    return TRADE_STATUS_RANK.get(status, 99)


def crv_color(trade_crv: Optional[float]) -> dict:
    if trade_crv is None:
        return {"farbe": "#95a5a6", "label": "Nicht bestimmbar"}
    for stufe in TRADE_CRV_COLOR_STUFEN:
        if stufe["crv_min"] is None or trade_crv >= stufe["crv_min"]:
            return {"farbe": stufe["farbe"], "label": stufe["label"]}
    return {"farbe": "#95a5a6", "label": "Nicht bestimmbar"}
