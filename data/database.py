"""
data/database.py — Alle Datenbankoperationen zentral
Aktien-Scanner V1
"""

import sqlite3
import logging
from datetime import date, datetime
from contextlib import contextmanager

import pandas as pd

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DB_PATH

logger = logging.getLogger(__name__)


# =============================================================================
# Verbindung
# =============================================================================

@contextmanager
def get_connection():
    """Kontextmanager für SQLite-Verbindung."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Datenbankfehler: {e}")
        raise
    finally:
        conn.close()


# =============================================================================
# Initialisierung
# =============================================================================

def init_db() -> None:
    """Erstellt alle Tabellen falls nicht vorhanden."""
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS stocks (
                ticker          TEXT PRIMARY KEY,
                name            TEXT,
                index_name      TEXT,
                market          TEXT,
                currency        TEXT,
                active          INTEGER DEFAULT 1,
                created_at      TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS prices (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker          TEXT NOT NULL,
                date            TEXT NOT NULL,
                open            REAL,
                high            REAL,
                low             REAL,
                close           REAL,
                volume          INTEGER,
                adj_close       REAL,
                data_source     TEXT DEFAULT 'yfinance',
                created_at      TEXT DEFAULT (datetime('now')),
                UNIQUE(ticker, date)
            );

            CREATE TABLE IF NOT EXISTS index_prices (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                index_name      TEXT NOT NULL,
                date            TEXT NOT NULL,
                close           REAL,
                data_source     TEXT DEFAULT 'yfinance',
                created_at      TEXT DEFAULT (datetime('now')),
                UNIQUE(index_name, date)
            );

            CREATE TABLE IF NOT EXISTS scores (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker          TEXT NOT NULL,
                date            TEXT NOT NULL,
                signal_version  TEXT DEFAULT 'V1',
                data_source     TEXT DEFAULT 'yfinance',

                filter_sma50    INTEGER,

                score_sma200    INTEGER,
                score_rs        INTEGER,
                score_breakout  INTEGER,
                score_regime    INTEGER,
                score_risk      INTEGER,

                score_total     INTEGER,
                rating          TEXT,

                sma50           REAL,
                sma200          REAL,
                rs_score        REAL,
                breakout_flag   INTEGER,
                breakout_age    INTEGER,
                regime          TEXT,
                stop_loss       REAL,
                crv             REAL,
                atr14           REAL,
                atr_ratio       REAL,
                kursziel        REAL,

                created_at      TEXT DEFAULT (datetime('now')),
                UNIQUE(ticker, date, signal_version)
            );

            CREATE INDEX IF NOT EXISTS idx_prices_ticker_date
                ON prices(ticker, date);
            CREATE INDEX IF NOT EXISTS idx_scores_date
                ON scores(date);
            CREATE INDEX IF NOT EXISTS idx_scores_ticker
                ON scores(ticker);
        """)
    logger.info("Datenbank initialisiert.")


# =============================================================================
# Stocks
# =============================================================================

def upsert_stock(ticker: str, name: str, index_name: str,
                 market: str, currency: str) -> None:
    """Fügt Aktie ein oder aktualisiert sie."""
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO stocks (ticker, name, index_name, market, currency)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET
                name=excluded.name,
                index_name=excluded.index_name,
                market=excluded.market,
                currency=excluded.currency
        """, (ticker, name, index_name, market, currency))


def get_active_stocks(index_name: str = None) -> list[dict]:
    """Gibt alle aktiven Aktien zurück, optional gefiltert nach Index."""
    with get_connection() as conn:
        if index_name:
            rows = conn.execute(
                "SELECT * FROM stocks WHERE active=1 AND index_name=?",
                (index_name,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM stocks WHERE active=1"
            ).fetchall()
    return [dict(r) for r in rows]


# =============================================================================
# Prices
# =============================================================================

def save_prices(ticker: str, df: pd.DataFrame) -> int:
    """
    Speichert Kursdaten. Duplikate werden ignoriert.
    Gibt Anzahl neu eingefügter Zeilen zurück.
    """
    if df.empty:
        return 0

    inserted = 0
    with get_connection() as conn:
        for _, row in df.iterrows():
            try:
                conn.execute("""
                    INSERT OR IGNORE INTO prices
                    (ticker, date, open, high, low, close, volume, adj_close)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    ticker,
                    str(row.get("date", row.name)),
                    row.get("open"),
                    row.get("high"),
                    row.get("low"),
                    row.get("close"),
                    row.get("volume"),
                    row.get("adj_close"),
                ))
                inserted += 1
            except Exception as e:
                logger.warning(f"Preisfehler {ticker}: {e}")
    return inserted


def get_prices(ticker: str, days: int) -> pd.DataFrame:
    """Liest die letzten N Handelstage aus der DB."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT date, open, high, low, close, volume, adj_close
            FROM prices
            WHERE ticker = ?
            ORDER BY date DESC
            LIMIT ?
        """, (ticker, days)).fetchall()

    if not rows:
        return pd.DataFrame(columns=["date","open","high","low","close","volume","adj_close"])

    df = pd.DataFrame([dict(r) for r in rows])
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    return df


# =============================================================================
# Index Prices
# =============================================================================

def save_index_prices(index_name: str, df: pd.DataFrame) -> int:
    """Speichert Indexkurse. Duplikate werden ignoriert."""
    if df.empty:
        return 0

    inserted = 0
    with get_connection() as conn:
        for _, row in df.iterrows():
            try:
                conn.execute("""
                    INSERT OR IGNORE INTO index_prices (index_name, date, close)
                    VALUES (?, ?, ?)
                """, (
                    index_name,
                    str(row.get("date", row.name)),
                    row.get("close"),
                ))
                inserted += 1
            except Exception as e:
                logger.warning(f"Indexpreisfehler {index_name}: {e}")
    return inserted


def get_index_prices(index_name: str, days: int) -> pd.DataFrame:
    """Liest Indexkurse aus der DB."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT date, close
            FROM index_prices
            WHERE index_name = ?
            ORDER BY date DESC
            LIMIT ?
        """, (index_name, days)).fetchall()

    if not rows:
        return pd.DataFrame(columns=["date", "close"])

    df = pd.DataFrame([dict(r) for r in rows])
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    return df


# =============================================================================
# Scores
# =============================================================================

def save_score(score_dict: dict) -> None:
    """Speichert einen Score-Eintrag. Duplikate (ticker+date+version) werden ersetzt."""
    with get_connection() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO scores (
                ticker, date, signal_version, data_source,
                filter_sma50,
                score_sma200, score_rs, score_breakout, score_regime, score_risk,
                score_total, rating,
                sma50, sma200, rs_score,
                breakout_flag, breakout_age,
                regime, stop_loss, crv, atr14, atr_ratio, kursziel
            ) VALUES (
                :ticker, :date, :signal_version, :data_source,
                :filter_sma50,
                :score_sma200, :score_rs, :score_breakout, :score_regime, :score_risk,
                :score_total, :rating,
                :sma50, :sma200, :rs_score,
                :breakout_flag, :breakout_age,
                :regime, :stop_loss, :crv, :atr14, :atr_ratio, :kursziel
            )
        """, score_dict)


def get_latest_scores(target_date: str = None, min_score: int = 0) -> pd.DataFrame:
    """
    Liest alle Scores für ein Datum.
    Wenn kein Datum angegeben: neuestes verfügbares Datum.
    """
    with get_connection() as conn:
        if target_date is None:
            row = conn.execute(
                "SELECT MAX(date) as d FROM scores WHERE score_total IS NOT NULL"
            ).fetchone()
            if not row or not row["d"]:
                return pd.DataFrame()
            target_date = row["d"]

        rows = conn.execute("""
            SELECT s.*, st.name
            FROM scores s
            LEFT JOIN stocks st ON s.ticker = st.ticker
            WHERE s.date = ?
              AND s.score_total IS NOT NULL
              AND s.score_total >= ?
            ORDER BY s.score_total DESC
        """, (target_date, min_score)).fetchall()

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame([dict(r) for r in rows])


def get_score_detail(ticker: str, target_date: str = None) -> dict | None:
    """Liest vollständigen Score-Eintrag für eine Aktie + Kursdaten."""
    with get_connection() as conn:
        if target_date is None:
            row = conn.execute(
                "SELECT MAX(date) as d FROM scores WHERE ticker=?",
                (ticker,)
            ).fetchone()
            if not row or not row["d"]:
                return None
            target_date = row["d"]

        row = conn.execute("""
            SELECT s.*, st.name, p.close as price_close
            FROM scores s
            LEFT JOIN stocks st ON s.ticker = st.ticker
            LEFT JOIN prices p ON s.ticker = p.ticker AND s.date = p.date
            WHERE s.ticker = ? AND s.date = ?
        """, (ticker, target_date)).fetchone()

        if not row:
            return None
        
        detail = dict(row)
        
        # Berechne stop_buy und risiko
        stop_loss = detail.get("stop_loss")
        atr14 = detail.get("atr14")
        price_close = detail.get("price_close")
        
        if stop_loss and atr14:
            # stop_buy = stop_loss + (2 * ATR)
            detail["stop_buy"] = stop_loss + (2 * atr14)
        else:
            detail["stop_buy"] = None
        
        # Risiko in Prozent
        if price_close and stop_loss:
            detail["risk_pct"] = abs((price_close - stop_loss) / price_close * 100)
        else:
            detail["risk_pct"] = None

    return detail


def get_db_stats() -> dict:
    """Gibt Statistiken über die Datenbank zurück (für Logging)."""
    with get_connection() as conn:
        stats = {}
        for table in ["stocks", "prices", "scores", "index_prices"]:
            row = conn.execute(f"SELECT COUNT(*) as n FROM {table}").fetchone()
            stats[table] = row["n"]
    return stats
