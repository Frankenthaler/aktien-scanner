"""
tests/seed_demo_db.py — Erzeugt eine Demo-Datenbank für den Frontend-Test
Aktien-Scanner V1

Erzeugt synthetische Aktien mit unterschiedlichen Score-Konstellationen,
damit alle UI-Zustände (alle Bewertungsstufen, Hard-Filter-Fall,
Allzeithoch-Sonderfall, verschiedene Regimes) sichtbar sind.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
config.DB_PATH = "demo.db"

from utils.logging_config import setup_logging
setup_logging()

from datetime import date
import numpy as np

from data.database import init_db, upsert_stock, save_prices, save_index_prices
from scoring.scorer import calculate_score
from tests.helpers import make_price_series

if os.path.exists("demo.db"):
    os.remove("demo.db")
init_db()

N = 270

# -----------------------------------------------------------------------------
# Indizes: DAX positiv, SP500 neutral (für unterschiedliche Sperrregel-Demo)
# -----------------------------------------------------------------------------
dax_index = make_price_series(N, start=18000, daily_change=15, volatility=50, seed=1)[["date", "close"]]
sp500_index = make_price_series(N, start=5000, daily_change=0.3, volatility=15, seed=2)[["date", "close"]]
ndx_index = make_price_series(N, start=18000, daily_change=0.5, volatility=40, seed=3)[["date", "close"]]

save_index_prices("DAX", dax_index)
save_index_prices("SP500", sp500_index)
save_index_prices("NDX100", ndx_index)

print("Indizes gespeichert.")
print(f"  DAX letzter Kurs: {dax_index['close'].iloc[-1]:.0f}, SMA200: {dax_index['close'].tail(200).mean():.0f}")
print(f"  SP500 letzter Kurs: {sp500_index['close'].iloc[-1]:.0f}, SMA200: {sp500_index['close'].tail(200).mean():.0f}")

# -----------------------------------------------------------------------------
# Aktien-Szenarien
# -----------------------------------------------------------------------------

szenarien = [
    # (ticker, name, index_name, daily_change, volatility, seed, mit_breakout)
    ("SAP.DE",  "SAP SE",          "DAX",  0.35, 0.6, 100, True),
    ("AIR.DE",  "Airbus SE",       "DAX",  0.20, 0.8, 101, False),
    ("VOW3.DE", "Volkswagen AG",   "DAX", -0.30, 0.7, 102, False),  # Hard Filter
    ("AAPL",    "Apple Inc.",      "SP500", 0.40, 0.5, 103, True),
    ("MSFT",    "Microsoft Corp.", "SP500", 0.15, 0.4, 104, False),
    ("NVDA",    "NVIDIA Corp.",    "NDX100", 0.10, 0.5, 105, False),
    ("JPM",     "JPMorgan Chase",  "SP500", 0.05, 0.6, 106, False),
]

for ticker, name, index_name, daily_change, vola, seed, want_breakout in szenarien:
    upsert_stock(ticker, name, index_name if index_name != "NDX100" else "NDX100",
                  "XETRA" if ticker.endswith(".DE") else "NASDAQ",
                  "EUR" if ticker.endswith(".DE") else "USD")

    start = 100
    df = make_price_series(N, start=start, daily_change=daily_change, volatility=vola, seed=seed)

    if want_breakout:
        # Letzten Tag als Breakout konstruieren
        df = df.copy()
        prev_max = df["close"].iloc[-21:-1].max()
        df.loc[df.index[-1], "close"] = prev_max * 1.02
        df.loc[df.index[-1], "adj_close"] = prev_max * 1.02
        df.loc[df.index[-1], "high"] = prev_max * 1.025
        df.loc[df.index[-1], "low"] = prev_max * 1.015
        df["volume"] = df["volume"].astype(float)
        df.loc[df.index[-1], "volume"] = df["volume"].iloc[-21:-1].mean() * 2

    save_prices(ticker, df)

    # Score berechnen — Deduplizierungsregel: NDX100 -> SP500 als Referenzindex
    ref_index = "SP500" if index_name == "NDX100" else index_name
    result = calculate_score(ticker, date.today(), ref_index)

    if result:
        print(f"{ticker:10s} ({name:18s}) Score={result['score_total']!s:>4} "
              f"Rating={result['rating']!s:18s} Regime={result['regime']}")
    else:
        print(f"{ticker:10s}: kein Ergebnis")

print("\nDemo-Datenbank 'demo.db' erstellt.")
