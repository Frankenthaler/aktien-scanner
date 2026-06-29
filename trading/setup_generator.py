"""
trading/setup_generator.py — Integrierter Setup-Generator
Aktien-Scanner V1

Erzeugt Stop-Buy, Stop-Loss und TP1 als zusammenhängendes System.
CRV bezieht sich immer auf den Einstieg (Stop-Buy), nicht den aktuellen Kurs.
Score-System (score_total, score_risk, crv) bleibt vollständig unberührt.
"""

import logging
import pandas as pd
import numpy as np
from typing import Optional

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    ATR_PERIOD, SETUP_SB_ATR_FACTOR, SETUP_SL_ATR_FACTOR,
    SETUP_SL_SWING_BUFFER, SETUP_TP_ATR_FALLBACK, SETUP_LOOKBACK_SHORT,
    SETUP_LOOKBACK_LONG, SETUP_SWING_LOW_WINDOW, SETUP_MIN_RESISTANCE_TESTS,
    SETUP_QUALITY_THRESHOLDS,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Hilfsfunktionen
# =============================================================================

def _find_resistance_level(prices_close: np.ndarray, band: float = 0.015,
                            min_tests: int = 2) -> Optional[float]:
    """Sucht das meistgetestete Widerstandsniveau."""
    if len(prices_close) < min_tests:
        return None
    best_level = None
    best_tests = 0
    for kandidat in prices_close:
        lower = kandidat * (1 - band)
        upper = kandidat * (1 + band)
        tests = int(np.sum((prices_close >= lower) & (prices_close <= upper)))
        if tests >= min_tests and (tests > best_tests or
           (tests == best_tests and (best_level is None or kandidat > best_level))):
            best_tests = tests
            best_level = float(kandidat)
    return best_level


def _find_next_resistance_above(prices_close: np.ndarray, above: float,
                                 band: float = 0.015, min_tests: int = 2) -> Optional[float]:
    """Sucht den nächsten Widerstand mindestens 2% oberhalb von 'above'."""
    candidates_idx = prices_close > above * 1.02
    candidates = prices_close[candidates_idx]
    if len(candidates) < min_tests:
        return None
    tested_levels = []
    for kandidat in candidates:
        lower = kandidat * (1 - band)
        upper = kandidat * (1 + band)
        tests = int(np.sum((prices_close >= lower) & (prices_close <= upper)))
        if tests >= min_tests:
            tested_levels.append(float(kandidat))
    if not tested_levels:
        return None
    return min(tested_levels)


def _find_swing_low(
    prices: pd.DataFrame,
    window: int = 5,
    recency_days: int = 20,
    strength_factor: float = 1.5,
    max_atr_distance: float = 3.0,
) -> Optional[float]:
    """
    Verbesserter Swing-Low-Algorithmus mit Recency-Bevorzugung und Distanz-Cap.

    Logik:
    1. Bevorzuge Swing-Tiefs der letzten 'recency_days' Handelstage.
    2. Ältere Tiefs werden nur verwendet wenn sie charttechnisch noch
       maßgeblich sind — d.h. nicht durch nachfolgende Kurse signifikant
       unterschritten wurden UND nicht mehr als max_atr_distance × ATR
       vom aktuellen Kurs entfernt liegen.
    3. Kein passendes Tief → None → ATR-Fallback in generate_trade_setup.

    Args:
        window:           Halbfenster für lokales Minimum (Tage links/rechts)
        recency_days:     Bevorzugter Suchbereich in Handelstagen
        strength_factor:  Tief gilt als gebrochen wenn danach > X × ATR darunter
        max_atr_distance: Tief maximal X × ATR unter aktuellem Close entfernt
    """
    if "low" not in prices.columns or len(prices) < window * 2 + 1:
        return None

    lows = prices["low"].values
    close_col = "adj_close" if "adj_close" in prices.columns else "close"
    closes = prices[close_col].values if close_col in prices.columns else lows
    current_close = float(closes[-1])
    n = len(lows)

    # ATR der letzten 14 Tage für Relevanzschwellwert
    if "high" in prices.columns and len(prices) >= 15:
        h = prices["high"].values[-14:]
        l = lows[-14:]
        p = closes[-15:-1]
        tr = np.maximum(h - l, np.maximum(np.abs(h - p), np.abs(l - p)))
        atr = float(tr.mean())
    else:
        atr = float(np.std(lows[-20:])) if len(lows) >= 5 else 1.0
    if atr <= 0:
        atr = current_close * 0.02

    def is_swing_low(idx: int) -> bool:
        left = lows[max(0, idx - window):idx]
        right = lows[idx + 1:min(n, idx + window + 1)]
        if len(left) == 0 or len(right) == 0:
            return False
        return lows[idx] < left.min() and lows[idx] < right.min()

    def still_relevant(idx: int) -> bool:
        """Tief ist noch charttechnisch maßgeblich."""
        swing_val = lows[idx]
        # Distanz-Cap: Tief darf nicht mehr als max_atr_distance × ATR
        # unter aktuellem Close liegen (verhindert 40%-Stops bei AMAT etc.)
        if current_close - swing_val > max_atr_distance * atr:
            return False
        # Nicht danach signifikant unterschritten (Niveau gilt als gebrochen)
        subsequent = lows[idx + 1:]
        if len(subsequent) > 0 and subsequent.min() < swing_val - strength_factor * atr:
            return False
        return True

    # Schritt 1: Bevorzugter Suchbereich (letzte recency_days)
    recent_start = max(0, n - recency_days)
    for i in range(n - 1, recent_start - 1, -1):
        if is_swing_low(i) and still_relevant(i):
            return float(lows[i])

    # Schritt 2: Älterer Bereich — nur charttechnisch noch maßgebliche Tiefs
    for i in range(recent_start - 1, window - 1, -1):
        if is_swing_low(i) and still_relevant(i):
            return float(lows[i])

    return None


# =============================================================================
# Setup-Qualität
# =============================================================================

def _calc_setup_quality(trade_crv, trade_risk_pct, atr_ratio,
                         widerstand_hits, sl_typ, tp_typ,
                         ema20_distance_pct, breakout_age):
    """Bewertet Setup-Qualität A+/A/B/C unabhängig vom Aktien-Score."""
    score = 0

    if trade_crv is not None:
        if trade_crv >= 3.0:   score += 40
        elif trade_crv >= 2.5: score += 33
        elif trade_crv >= 2.0: score += 25
        elif trade_crv >= 1.5: score += 15

    if trade_risk_pct is not None:
        if trade_risk_pct <= 4.0:    score += 20
        elif trade_risk_pct <= 6.0:  score += 14
        elif trade_risk_pct <= 8.0:  score += 8
        elif trade_risk_pct <= 10.0: score += 4

    if widerstand_hits >= 5:   score += 15
    elif widerstand_hits >= 3: score += 10
    elif widerstand_hits >= 2: score += 5

    score += 10 if sl_typ == "swing_low" else 4
    score += 10 if tp_typ == "widerstand" else 4

    if ema20_distance_pct is not None:
        if ema20_distance_pct <= 2.0:   score += 5
        elif ema20_distance_pct <= 3.5: score += 3
        elif ema20_distance_pct <= 5.5: score += 1

    if breakout_age is not None:
        if breakout_age == 0:   score += 5
        elif breakout_age == 1: score += 4
        elif breakout_age == 2: score += 2

    thresholds = SETUP_QUALITY_THRESHOLDS
    if score >= thresholds["A+"]:   grade = "A+"
    elif score >= thresholds["A"]:  grade = "A"
    elif score >= thresholds["B"]:  grade = "B"
    else:                           grade = "C"

    return grade, score


# =============================================================================
# Haupt-Funktion
# =============================================================================

def generate_trade_setup(
    prices: pd.DataFrame,
    atr14: Optional[float],
    ema20: Optional[float] = None,
    breakout_age: Optional[int] = None,
) -> dict:
    """
    Generiert Stop-Buy, Stop-Loss und TP1 als zusammenhängendes System.
    CRV bezieht sich immer auf den Einstieg (Stop-Buy).
    Gibt leeres dict mit None-Werten bei Fehler zurück.
    """
    _empty = {
        "stop_buy": None, "stop_loss": None, "tp1": None,
        "trade_crv": None, "trade_risk_pct": None, "trade_chance_pct": None,
        "setup_quality": None, "setup_quality_score": None,
        "widerstand_hits": 0, "sl_typ": None, "tp_typ": None,
    }

    if prices is None or prices.empty or atr14 is None or atr14 <= 0:
        return _empty

    try:
        close_col = "adj_close" if "adj_close" in prices.columns else "close"
        current_price = float(prices[close_col].iloc[-1])

        # Schritt 1: Widerstand für Stop-Buy (20 Tage)
        short_window = prices[close_col].tail(SETUP_LOOKBACK_SHORT).values
        resistance = _find_resistance_level(short_window, band=0.015,
                                            min_tests=SETUP_MIN_RESISTANCE_TESTS)
        if resistance is None:
            resistance = float(prices[close_col].tail(SETUP_LOOKBACK_SHORT).max())
            widerstand_hits = 1
        else:
            band = 0.015
            widerstand_hits = int(np.sum(
                (short_window >= resistance * (1 - band)) &
                (short_window <= resistance * (1 + band))
            ))

        # Schritt 2: Stop-Buy = Widerstand + 0.5 × ATR
        stop_buy = resistance + SETUP_SB_ATR_FACTOR * atr14
        if stop_buy <= current_price:
            stop_buy = current_price * 1.005

        # Schritt 3: Stop-Loss = Swing-Tief − 0.3 × ATR
        swing_low = _find_swing_low(
            prices,
            window=SETUP_SWING_LOW_WINDOW,
            recency_days=SETUP_SWING_LOW_RECENCY,
            strength_factor=SETUP_SWING_LOW_STRENGTH,
            max_atr_distance=SETUP_SWING_LOW_MAX_ATR,
        )
        sl_typ = "swing_low"
        if swing_low is not None and swing_low < stop_buy:
            stop_loss = swing_low - SETUP_SL_SWING_BUFFER * atr14
        else:
            stop_loss = stop_buy - SETUP_SL_ATR_FACTOR * atr14
            sl_typ = "atr_fallback"

        if stop_loss >= stop_buy:
            stop_loss = stop_buy - SETUP_SL_ATR_FACTOR * atr14
            sl_typ = "atr_fallback"

        # Schritt 4: TP1 = nächster Widerstand oberhalb Stop-Buy (60 Tage)
        long_window = prices[close_col].tail(SETUP_LOOKBACK_LONG).values
        tp1 = _find_next_resistance_above(long_window, above=stop_buy,
                                          band=0.015, min_tests=SETUP_MIN_RESISTANCE_TESTS)
        tp_typ = "widerstand"
        if tp1 is None:
            tp1 = stop_buy + SETUP_TP_ATR_FALLBACK * atr14
            tp_typ = "atr_fallback"

        # Schritt 5: CRV vom Einstieg
        risiko_abs = stop_buy - stop_loss
        chance_abs = tp1 - stop_buy

        if risiko_abs <= 0 or tp1 <= stop_buy:
            return _empty

        trade_crv = chance_abs / risiko_abs
        trade_risk_pct = (risiko_abs / stop_buy) * 100
        trade_chance_pct = (chance_abs / stop_buy) * 100

        # Schritt 6: Konsistenz — SL iterativ anpassen wenn CRV < 1.5
        if trade_crv < 1.5 and sl_typ == "swing_low":
            swing_low_narrow = _find_swing_low(prices, window=max(3, SETUP_SWING_LOW_WINDOW // 2))
            if swing_low_narrow is not None and swing_low_narrow < stop_buy:
                stop_loss_adj = swing_low_narrow - SETUP_SL_SWING_BUFFER * atr14
                risiko_adj = stop_buy - stop_loss_adj
                if risiko_adj > 0:
                    crv_adj = chance_abs / risiko_adj
                    if crv_adj > trade_crv:
                        stop_loss = stop_loss_adj
                        risiko_abs = risiko_adj
                        trade_crv = crv_adj
                        trade_risk_pct = (risiko_abs / stop_buy) * 100

        # Schritt 7: Setup-Qualität
        ema20_dist = None
        if ema20 is not None and ema20 > 0:
            ema20_dist = ((current_price - ema20) / ema20) * 100
        atr_ratio = (atr14 / current_price) * 100
        quality, quality_score = _calc_setup_quality(
            trade_crv=trade_crv, trade_risk_pct=trade_risk_pct,
            atr_ratio=atr_ratio, widerstand_hits=widerstand_hits,
            sl_typ=sl_typ, tp_typ=tp_typ,
            ema20_distance_pct=ema20_dist, breakout_age=breakout_age,
        )

        logger.info(
            f"Setup: SB={stop_buy:.2f} SL={stop_loss:.2f} TP={tp1:.2f} "
            f"CRV={trade_crv:.2f} Risiko={trade_risk_pct:.1f}% Q={quality}"
        )

        return {
            "stop_buy":            round(stop_buy, 2),
            "stop_loss":           round(stop_loss, 2),
            "tp1":                 round(tp1, 2),
            "trade_crv":           round(trade_crv, 3),
            "trade_risk_pct":      round(trade_risk_pct, 2),
            "trade_chance_pct":    round(trade_chance_pct, 2),
            "setup_quality":       quality,
            "setup_quality_score": quality_score,
            "widerstand_hits":     widerstand_hits,
            "sl_typ":              sl_typ,
            "tp_typ":              tp_typ,
        }

    except Exception as e:
        logger.error(f"generate_trade_setup Fehler: {e}", exc_info=True)
        return _empty
