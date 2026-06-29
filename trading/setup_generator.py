"""
trading/setup_generator.py — Integrierter Setup-Generator
Aktien-Scanner V1

ZWECK
-----
Ersetzt die bisherigen drei unabhängigen Berechnungen:
  - trading/stop_buy_calculator.py  (20-Tage-Hoch × 1.01)
  - signals/risk.py calc_risk()     (ATR × 1.5 Stop-Loss, 60-Tage-Hoch TP1)

Diese erzeugten drei Marken unabhängig voneinander. Das führte zu:
  - Negativem CRV wenn TP1 < Stop-Buy
  - Stop-Loss der sich auf aktuellen Kurs bezieht, nicht auf den Einstieg
  - Pauschalen 1%-Aufschlägen unabhängig von der Volatilität
  - Kurszielen die 30%+ entfernt liegen können

NEUE LOGIK
----------
Die drei Marken entstehen als zusammenhängendes System in dieser Reihenfolge:

  1. Widerstand identifizieren (20T für Stop-Buy, 60T für TP1)
  2. Stop-Buy = Widerstand + 0.5 × ATR14
  3. Stop-Loss = letztes Swing-Tief − 0.3 × ATR
                 (Fallback: Stop-Buy − 2.0 × ATR)
  4. TP1 = nächster Widerstand oberhalb Stop-Buy (60T-Lookback)
           (Fallback: Stop-Buy + 2.5 × ATR, KEINE Obergrenze)
  5. CRV = (TP1 − Stop-Buy) / (Stop-Buy − Stop-Loss)
  6. Konsistenzprüfung → iterative Anpassung
  7. Setup-Qualität A+/A/B/C

WICHTIGE DESIGNENTSCHEIDUNGEN
------------------------------
- TP1 hat KEINE Obergrenze in ATR-Einheiten. Wenn nach einem Basisausbruch
  der nächste Widerstand 6 ATR entfernt liegt, ist das ein hervorragendes
  Setup — keine künstliche Verkürzung.
- Risiko > 8% führt NICHT zum Ausschluss, sondern zur Abstufung der
  Setup-Qualität. Der Trader entscheidet selbst.
- Score-System (score_total, score_risk, crv) bleibt GESPERRT und
  unberührt. Nur die trade_* Felder werden durch dieses Modul befüllt.

SCORE-SYSTEM BLEIBT UNBERÜHRT
------------------------------
Das gesperrte 100-Punkte-System berechnet weiterhin seinen eigenen
'crv' (vom aktuellen Kurs) und 'stop_loss' (ATR × 1.5 vom Kurs).
Diese Felder dienen ausschließlich der Score-Berechnung.
Die trade_* Felder dieses Moduls sind die Handelsempfehlung.
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
    """
    Sucht das meistgetestete Widerstandsniveau in einem Preisarray.

    Methode: Für jeden Schlusskurs wird gezählt, wie viele andere
    Schlusskurse im Band [kurs*(1-band), kurs*(1+band)] liegen.
    Das Niveau mit den meisten Tests und dem höchsten Preis gewinnt.

    Args:
        prices_close: Numpy-Array von Schlusskursen (aufsteigend)
        band:         Toleranzband (default 1.5%)
        min_tests:    Mindestanzahl Tests für gültigen Widerstand

    Returns:
        Widerstandsniveau oder None
    """
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
                                 band: float = 0.015,
                                 min_tests: int = 2) -> Optional[float]:
    """
    Sucht den nächsten Widerstand OBERHALB eines Schwellenwerts.

    Verwendet dieselbe Logik wie _find_resistance_level, filtert aber
    nur Kandidaten die mindestens 1% über 'above' liegen.

    Args:
        prices_close: Numpy-Array von Schlusskursen
        above:        Untergrenze (Stop-Buy-Niveau)
        band/min_tests: wie _find_resistance_level

    Returns:
        Nächstgelegener Widerstand oberhalb 'above' oder None
    """
    # Nur Kurse betrachten die oberhalb des Stop-Buy liegen
    candidates_idx = prices_close > above * 1.02
    candidates = prices_close[candidates_idx]

    if len(candidates) < min_tests:
        return None

    # Unter allen getesteten Niveaus oberhalb stop_buy das NIEDRIGSTE wählen
    # (= nächster erreichbarer Widerstand, nicht das fernste)
    tested_levels = []
    for kandidat in candidates:
        lower = kandidat * (1 - band)
        upper = kandidat * (1 + band)
        tests = int(np.sum((prices_close >= lower) & (prices_close <= upper)))
        if tests >= min_tests:
            tested_levels.append((kandidat, tests))

    if not tested_levels:
        return None

    # Nächstgelegener Widerstand = kleinster Wert
    return float(min(t[0] for t in tested_levels))


def _find_swing_low(prices: pd.DataFrame, window: int = 10) -> Optional[float]:
    """
    Findet das letzte lokale Swing-Tief.

    Definition: Ein Tief gilt als Swing-Tief wenn der Low-Kurs dieses Tages
    kleiner ist als die Low-Kurse der 'window' umliegenden Tage.

    Args:
        prices: DataFrame mit 'low'-Spalte, aufsteigend sortiert
        window: Halbfenster in Handelstagen

    Returns:
        Letztes Swing-Tief (float) oder None
    """
    if "low" not in prices.columns or len(prices) < window * 2 + 1:
        return None

    lows = prices["low"].values
    n = len(lows)

    # Von heute rückwärts suchen
    for i in range(n - 1, window - 1, -1):
        left = lows[max(0, i - window):i]
        right = lows[i + 1:min(n, i + window + 1)]
        if len(left) == 0 or len(right) == 0:
            continue
        if lows[i] < left.min() and lows[i] < right.min():
            return float(lows[i])

    return None


# =============================================================================
# Setup-Qualität
# =============================================================================

def _calc_setup_quality(
    trade_crv: Optional[float],
    trade_risk_pct: Optional[float],
    atr_ratio: float,
    widerstand_hits: int,
    sl_typ: str,
    tp_typ: str,
    ema20_distance_pct: Optional[float],
    breakout_age: Optional[int],
) -> tuple[str, int]:
    """
    Bewertet die Qualität eines Setups unabhängig vom Aktien-Score.

    Kriterien (alle setup-spezifisch, nicht aktienspezifisch):
      - CRV (höchste Gewichtung)
      - Risiko in %
      - Qualität des Widerstands (wie oft getestet)
      - SL-Typ (Chartstruktur > ATR-Fallback)
      - TP-Typ (Widerstand > ATR-Fallback)
      - EMA20-Abstand
      - Frische des Breakouts

    Returns:
        (grade: "A+" | "A" | "B" | "C", score: 0-100)
    """
    score = 0

    # CRV (0–40 Punkte)
    if trade_crv is not None:
        if trade_crv >= 3.0:   score += 40
        elif trade_crv >= 2.5: score += 33
        elif trade_crv >= 2.0: score += 25
        elif trade_crv >= 1.5: score += 15
        else:                  score += 0

    # Risiko in % (0–20 Punkte) — kein Ausschluss, aber Abstufung
    if trade_risk_pct is not None:
        if trade_risk_pct <= 4.0:   score += 20
        elif trade_risk_pct <= 6.0: score += 14
        elif trade_risk_pct <= 8.0: score += 8
        elif trade_risk_pct <= 10.0: score += 4
        else:                        score += 0

    # Widerstandsqualität (0–15 Punkte)
    if widerstand_hits >= 5:   score += 15
    elif widerstand_hits >= 3: score += 10
    elif widerstand_hits >= 2: score += 5
    else:                      score += 0

    # SL-Typ (0–10 Punkte)
    score += 10 if sl_typ == "swing_low" else 4

    # TP-Typ (0–10 Punkte)
    score += 10 if tp_typ == "widerstand" else 4

    # EMA20-Abstand (0–5 Punkte)
    if ema20_distance_pct is not None:
        if ema20_distance_pct <= 2.0:   score += 5
        elif ema20_distance_pct <= 3.5: score += 3
        elif ema20_distance_pct <= 5.5: score += 1
        else:                           score += 0

    # Breakout-Frische (0–5 Punkte) — frischer = besser
    if breakout_age is not None:
        if breakout_age == 0:   score += 5
        elif breakout_age == 1: score += 4
        elif breakout_age == 2: score += 2
        else:                   score += 0

    # Grade ableiten
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

    Die drei Marken entstehen iterativ und werden auf Konsistenz geprüft.
    CRV bezieht sich immer auf den Einstieg (Stop-Buy), nicht den
    aktuellen Kurs.

    Args:
        prices:       DataFrame mit close/adj_close, high, low (aufsteigend)
        atr14:        Bereits berechneter ATR14-Wert
        ema20:        EMA20 für Setup-Qualitätsbewertung (optional)
        breakout_age: Alter des Breakouts in Tagen (optional)

    Returns:
        dict mit allen Setup-Feldern. Bei Fehler: leeres dict mit None-Werten.
        Schlüssel:
          stop_buy, stop_loss, tp1,
          trade_crv, trade_risk_pct, trade_chance_pct,
          setup_quality, setup_quality_score,
          widerstand_hits, sl_typ, tp_typ
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

    # ── Schritt 1: Widerstand für Stop-Buy (SETUP_LOOKBACK_SHORT Tage) ──────
    short_window = prices[close_col].tail(SETUP_LOOKBACK_SHORT).values
    resistance = _find_resistance_level(
        short_window,
        band=0.015,
        min_tests=SETUP_MIN_RESISTANCE_TESTS,
    )

    # Fallback: 20-Tage-Hoch wenn kein getesteter Widerstand gefunden
    if resistance is None:
        resistance = float(prices[close_col].tail(SETUP_LOOKBACK_SHORT).max())
        widerstand_hits = 1
        logger.debug(f"stop_buy: Kein getesteter Widerstand → Fallback 20T-Hoch={resistance:.2f}")
    else:
        # Wie oft wurde der Widerstand getestet?
        band = 0.015
        widerstand_hits = int(np.sum(
            (short_window >= resistance * (1 - band)) &
            (short_window <= resistance * (1 + band))
        ))

    # ── Schritt 2: Stop-Buy = Widerstand + 0.5 × ATR ────────────────────────
    stop_buy = resistance + SETUP_SB_ATR_FACTOR * atr14

    # Stop-Buy darf nicht unter aktuellem Kurs liegen
    if stop_buy <= current_price:
        stop_buy = current_price * 1.005  # minimal über Kurs

    # ── Schritt 3: Stop-Loss = Swing-Tief − 0.3 × ATR ───────────────────────
    swing_low = _find_swing_low(prices, window=SETUP_SWING_LOW_WINDOW)
    sl_typ = "swing_low"

    if swing_low is not None and swing_low < stop_buy:
        stop_loss = swing_low - SETUP_SL_SWING_BUFFER * atr14
    else:
        # Fallback: 2.0 × ATR unter Stop-Buy (nicht unter aktuellem Kurs!)
        stop_loss = stop_buy - SETUP_SL_ATR_FACTOR * atr14
        sl_typ = "atr_fallback"
        logger.debug(f"stop_loss: Kein Swing-Tief → ATR-Fallback={stop_loss:.2f}")

    # Stop-Loss muss unter Stop-Buy liegen
    if stop_loss >= stop_buy:
        stop_loss = stop_buy - SETUP_SL_ATR_FACTOR * atr14
        sl_typ = "atr_fallback"

    # ── Schritt 4: TP1 = nächster Widerstand oberhalb Stop-Buy ──────────────
    long_window = prices[close_col].tail(SETUP_LOOKBACK_LONG).values
    tp1 = _find_next_resistance_above(
        long_window,
        above=stop_buy,
        band=0.015,
        min_tests=SETUP_MIN_RESISTANCE_TESTS,
    )
    tp_typ = "widerstand"

    if tp1 is None:
        # Fallback: Stop-Buy + 2.5 × ATR — KEINE Obergrenze
        tp1 = stop_buy + SETUP_TP_ATR_FALLBACK * atr14
        tp_typ = "atr_fallback"
        logger.debug(f"tp1: Kein Widerstand oberhalb Stop-Buy → ATR-Fallback={tp1:.2f}")

    # ── Schritt 5: CRV vom Einstieg ─────────────────────────────────────────
    risiko_abs = stop_buy - stop_loss
    chance_abs = tp1 - stop_buy

    if risiko_abs <= 0:
        logger.warning("generate_trade_setup: risiko_abs <= 0, Setup ungültig")
        return _empty

    trade_crv = chance_abs / risiko_abs
    trade_risk_pct = (risiko_abs / stop_buy) * 100
    trade_chance_pct = (chance_abs / stop_buy) * 100

    # ── Schritt 6: Konsistenzprüfung — iterative Anpassung ──────────────────
    # Wenn CRV < 1.5: SL enger setzen (Swing-Tief-Suche mit kleinerem Fenster)
    if trade_crv < 1.5 and sl_typ == "swing_low":
        swing_low_narrow = _find_swing_low(prices, window=max(3, SETUP_SWING_LOW_WINDOW // 2))
        if swing_low_narrow is not None and swing_low_narrow < stop_buy:
            stop_loss_adj = swing_low_narrow - SETUP_SL_SWING_BUFFER * atr14
            risiko_adj = stop_buy - stop_loss_adj
            if risiko_adj > 0:
                crv_adj = chance_abs / risiko_adj
                if crv_adj > trade_crv:  # nur wenn es sich verbessert
                    stop_loss = stop_loss_adj
                    risiko_abs = risiko_adj
                    trade_crv = crv_adj
                    trade_risk_pct = (risiko_abs / stop_buy) * 100
                    logger.debug(f"iterativ: SL angepasst → CRV={trade_crv:.2f}")

    # TP1 muss über Stop-Buy liegen — sonst Setup ungültig
    if tp1 <= stop_buy:
        logger.warning("generate_trade_setup: tp1 <= stop_buy nach Iteration")
        return _empty

    # ── Schritt 7: Setup-Qualität ────────────────────────────────────────────
    ema20_dist = None
    if ema20 is not None and ema20 > 0:
        ema20_dist = ((current_price - ema20) / ema20) * 100

    atr_ratio = (atr14 / current_price) * 100
    quality, quality_score = _calc_setup_quality(
        trade_crv=trade_crv,
        trade_risk_pct=trade_risk_pct,
        atr_ratio=atr_ratio,
        widerstand_hits=widerstand_hits,
        sl_typ=sl_typ,
        tp_typ=tp_typ,
        ema20_distance_pct=ema20_dist,
        breakout_age=breakout_age,
    )

    logger.info(
        f"Setup: SB={stop_buy:.2f} SL={stop_loss:.2f} TP={tp1:.2f} "
        f"CRV={trade_crv:.2f} Risiko={trade_risk_pct:.1f}% "
        f"Qualität={quality}({quality_score}) "
        f"SL-Typ={sl_typ} TP-Typ={tp_typ}"
    )

        return {
            "stop_buy":           round(stop_buy, 2),
            "stop_loss":          round(stop_loss, 2),
            "tp1":                round(tp1, 2),
            "trade_crv":          round(trade_crv, 3),
            "trade_risk_pct":     round(trade_risk_pct, 2),
            "trade_chance_pct":   round(trade_chance_pct, 2),
            "setup_quality":      quality,
            "setup_quality_score": quality_score,
            "widerstand_hits":    widerstand_hits,
            "sl_typ":             sl_typ,
            "tp_typ":             tp_typ,
        }
    except Exception as e:
        logger.error(f"generate_trade_setup interner Fehler: {e}", exc_info=True)
        return _empty
