"""
scoring/scorer.py — Score-Aggregation
Aktien-Scanner V1

Berechnungsreihenfolge (Master-Spezifikation V1.1, Abschnitt 9):
  Schritt 1: Einzelsignale summieren
  Schritt 2: Sperrregel prüfen (Regime Neutral/Negativ -> Score = min(Score, REGIME_SCORE_CAP))
  Schritt 3: Bewertungsstufe zuweisen
"""

import logging
from datetime import date

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    SIGNAL_VERSION, REGIME_SCORE_CAP, RATING_THRESHOLDS,
    MIN_TRADING_DAYS, EMA20_PERIOD,
)
from data.database import get_prices, get_index_prices, save_score
from signals.filter_sma50 import check_sma50
from signals.sma200 import calc_sma200
from signals.relative_strength import calc_rs
from signals.breakout import calc_breakout
from signals.regime import calc_regime
from signals.risk import calc_risk
from trading.setup_generator import generate_trade_setup

logger = logging.getLogger(__name__)


def assign_rating(score: int) -> str:
    """
    Wandelt Gesamtscore in Bewertungsstufe um.

    Args:
        score: Gesamtscore 0-100

    Returns:
        Bewertungsstufe gemäß RATING_THRESHOLDS
        (sortiert von höchster zu niedrigster Schwelle)
    """
    # Schwellen absteigend sortieren und erste passende Stufe zurückgeben
    sorted_thresholds = sorted(RATING_THRESHOLDS.items(), key=lambda x: -x[1])
    for rating, threshold in sorted_thresholds:
        if score >= threshold:
            return rating
    return "Kein Kauf"


def calculate_score(ticker: str, target_date: date, index_name: str) -> dict | None:
    """
    Vollständige Score-Berechnung für eine Aktie.

    Args:
        ticker: Aktien-Ticker
        target_date: Datum, für das der Score berechnet wird (für DB-Speicherung)
        index_name: Referenzindex für RS und Regime ("DAX" oder "SP500")

    Returns:
        Score-Dict (siehe DB-Schema 'scores') oder None bei Datenfehler
        (z.B. zu wenig Kursdaten generell vorhanden)
    """
    # 1. Kursdaten laden
    days_needed = max(MIN_TRADING_DAYS + 10, 270)  # Puffer für alle Signale
    prices = get_prices(ticker, days_needed)
    index_prices = get_index_prices(index_name, days_needed)

    if prices is None or prices.empty:
        logger.error(f"{ticker}: Keine Kursdaten in DB vorhanden — Score nicht berechenbar")
        return None

    if len(prices) < MIN_TRADING_DAYS:
        logger.warning(f"{ticker}: Nur {len(prices)} Tage Historie (< {MIN_TRADING_DAYS}) — "
                        f"Aktie wird übersprungen")
        return None

    # 2. Hard Filter SMA50
    filter_ok, sma50 = check_sma50(prices)

    base_dict = {
        "ticker": ticker,
        "date": str(target_date),
        "signal_version": SIGNAL_VERSION,
        "data_source": "yfinance",
        "filter_sma50": int(filter_ok),
        "sma50": sma50,
    }

    if not filter_ok:
        # Hard Filter nicht bestanden -> kein Score, aber Eintrag für Backtest-Historie
        score_dict = {
            **base_dict,
            "score_sma200": None, "score_rs": None, "score_breakout": None,
            "score_regime": None, "score_risk": None,
            "score_total": None, "rating": None,
            "sma200": None, "rs_score": None,
            "breakout_flag": None, "breakout_age": None,
            "regime": None, "stop_loss": None, "crv": None,
            "atr14": None, "atr_ratio": None, "kursziel": None,
            "stop_buy": None, "trade_risk_pct": None,
            "trade_chance_pct": None, "trade_crv": None, "ema20": None,
            "setup_quality": None, "setup_quality_score": None,
        }
        save_score(score_dict)
        logger.info(f"{ticker}: Hard Filter SMA50 nicht bestanden — kein Score")
        return score_dict

    # 3. Alle 5 Signale berechnen
    score_sma200, sma200, status_sma200 = calc_sma200(prices)
    score_rs, rs_score = calc_rs(prices, index_prices)
    score_breakout, breakout_flag, breakout_age = calc_breakout(prices)
    score_regime, regime_status = calc_regime(index_prices)
    score_risk, stop_loss, crv, atr14, atr_ratio, kursziel = calc_risk(prices)

    # Stop-Buy (widerstandsbasiert, 20-Tage-Hoch × 1,01) — KEIN Einfluss auf
    # score_total/score_risk. Sowie die darauf basierenden Handelskennzahlen
    # (siehe trading/trade_metrics.py: Risiko/Chance/CRV relativ zum
    # Einstiegspreis statt zum aktuellen Kurs).
    stop_buy = calculate_stop_buy(prices, score_dict={})

    # EMA20 für Setup-Qualitätsprüfung (EMA20-Abstandsregel in trade_status.py)
    close_col = "adj_close" if "adj_close" in prices.columns else "close"
    ema20 = float(prices[close_col].ewm(span=EMA20_PERIOD, adjust=False).mean().iloc[-1])

    trade_risk_pct, trade_chance_pct, trade_crv = calculate_trade_metrics(
        stop_buy, stop_loss, kursziel
    )

    # 4. Schritt 1: Summe bilden
    score_total = score_sma200 + score_rs + score_breakout + score_regime + score_risk

    # 5. Schritt 2: Sperrregel anwenden
    if regime_status in ("neutral", "negativ"):
        score_total = min(score_total, REGIME_SCORE_CAP)

    # 6. Schritt 3: Bewertungsstufe zuweisen
    rating = assign_rating(score_total)

    score_dict = {
        **base_dict,
        "score_sma200": score_sma200,
        "score_rs": score_rs,
        "score_breakout": score_breakout,
        "score_regime": score_regime,
        "score_risk": score_risk,
        "score_total": score_total,
        "rating": rating,
        "sma200": sma200,
        "rs_score": rs_score,
        "breakout_flag": int(breakout_flag),
        "breakout_age": breakout_age,
        "regime": regime_status,
        "stop_loss": stop_loss,
        "crv": crv,
        "atr14": atr14,
        "atr_ratio": atr_ratio,
        "kursziel": kursziel,
        "stop_buy": stop_buy,
        "trade_risk_pct": trade_risk_pct,
        "trade_chance_pct": trade_chance_pct,
        "trade_crv": trade_crv,
        "ema20": ema20,
        "setup_quality": setup_quality,
        "setup_quality_score": setup_quality_score,
    }

    # 7. In DB speichern
    save_score(score_dict)

    logger.info(f"{ticker}: Score={score_total} ({rating}) | "
                f"SMA200={score_sma200} RS={score_rs} Breakout={score_breakout} "
                f"Regime={score_regime}({regime_status}) Risk={score_risk}")

    return score_dict
