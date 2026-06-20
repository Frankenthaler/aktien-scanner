"""
trading/recommendation_tracker.py – FINAL VERSION
Mit FIX 1-4 + Score-Versionierung integriert
"""

import logging
import pandas as pd
import sqlite3
from datetime import date
from typing import Optional, Dict

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
# SCORE VERSION (FIX 1 + SCORE-VERSION)
# ═══════════════════════════════════════════════════════════════════════════

SCORE_VERSION = "1.0"
SCORE_VERSION_DESCRIPTION = "Initial Release – keine Änderungen an Gewichten"


def init_swing_trading_schema(db_path: str = "aktien_scanner.db"):
    """Erstellt die Tracking-Tabellen mit Score-Versionierung."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Create Recommendations Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS swing_trade_recommendations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recommendation_date TEXT NOT NULL,
                ticker TEXT NOT NULL,
                
                score_total INTEGER,
                score_sma200 INTEGER,
                score_rs INTEGER,
                score_breakout INTEGER,
                score_regime INTEGER,
                score_risk INTEGER,
                rating TEXT,
                
                price_close REAL,
                stop_buy_price REAL,
                stop_loss_price REAL,
                
                sma200 REAL,
                rs_score REAL,
                breakout_flag INTEGER,
                breakout_age INTEGER,
                regime TEXT,
                atr14 REAL,
                atr_ratio REAL,
                crv REAL,
                kursziel REAL,
                
                score_version TEXT DEFAULT '1.0',
                
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(recommendation_date, ticker)
            )
        """)
        
        # Create Performance Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS swing_trade_performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recommendation_id INTEGER NOT NULL,
                recommendation_date TEXT NOT NULL,
                ticker TEXT NOT NULL,
                
                price_at_recommendation REAL,
                price_after_5d REAL,
                price_after_10d REAL,
                price_after_20d REAL,
                price_after_60d REAL,
                
                return_5d REAL,
                return_10d REAL,
                return_20d REAL,
                return_60d REAL,
                
                max_high_20d REAL,
                max_gain_20d REAL,
                max_low_20d REAL,
                max_loss_20d REAL,
                
                stop_buy_hit INTEGER,
                days_to_stop_buy_hit INTEGER,
                price_at_stop_buy_hit REAL,
                
                risk_amount REAL,
                risk_percent REAL,
                max_gain_r REAL,
                max_loss_r REAL,
                return_20d_r REAL,
                return_60d_r REAL,
                
                success_5d INTEGER,
                success_10d INTEGER,
                success_20d INTEGER,
                success_60d INTEGER,
                
                trade_triggered INTEGER,
                trade_success INTEGER,
                
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_complete INTEGER DEFAULT 0,
                
                FOREIGN KEY(recommendation_id) REFERENCES swing_trade_recommendations(id),
                UNIQUE(recommendation_id)
            )
        """)
        
        # Create Indices
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_swing_date ON swing_trade_recommendations(recommendation_date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_swing_ticker ON swing_trade_recommendations(ticker)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_swing_score ON swing_trade_recommendations(score_total)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_swing_score_version ON swing_trade_recommendations(score_version)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_perf_date ON swing_trade_performance(recommendation_date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_perf_ticker ON swing_trade_performance(ticker)")
        
        conn.commit()
        logger.info("✓ Swing-Trading Tabellen initialisiert")
    except Exception as e:
        logger.error(f"✗ Fehler beim Initialisieren: {e}")
        raise
    finally:
        conn.close()


def save_swing_trade_recommendation(
    score_dict: dict,
    stop_buy_price: Optional[float],
    stop_loss_price: Optional[float],
    score_version: str = SCORE_VERSION,
    db_path: str = "aktien_scanner.db"
) -> Optional[int]:
    """
    Speichert eine Empfehlung mit Score-Version.
    
    FIX 1: Dokumentation für statistische Signifikanz
    Scores >= 55 erforderlich
    """
    
    if score_dict.get("score_total") is None or score_dict.get("score_total") < 55:
        return None
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT OR REPLACE INTO swing_trade_recommendations (
                recommendation_date, ticker,
                score_total, score_sma200, score_rs, score_breakout, score_regime,
