"""
tests/test_scorer_e2e.py — End-to-End-Test scoring/scorer.py mit DB
Aktien-Scanner V1

Erzeugt synthetische Kursdaten, speichert sie in eine Test-DB,
ruft calculate_score() auf und prüft das Ergebnis inkl. Sperrregel.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
from datetime import date

# Test-DB verwenden (nicht die Produktions-DB überschreiben)
import config
config.DB_PATH = "test_scorer.db"

from utils.logging_config import setup_logging
setup_logging()

from data.database import init_db, save_prices, save_index_prices, get_score_detail
from scoring.scorer import calculate_score
from tests.helpers import make_price_series

PASS, FAIL = [], []

def check(name, cond, detail=""):
    if cond:
        PASS.append(name); print(f"  ✓ {name}")
    else:
        FAIL.append(name); print(f"  ✗ {name}  {detail}")


# Frische Test-DB
if os.path.exists("test_scorer.db"):
    os.remove("test_scorer.db")
init_db()

# -----------------------------------------------------------------------------
print("\n=== E2E-Test: calculate_score() ===")

# Szenario A: Aktie mit starkem Aufwärtstrend + Index positiv -> hoher Score
n = 270
df_stock = make_price_series(n, start=150, daily_change=0.30, volatility=0.5, seed=10)
df_index = make_price_series(n, start=15000, daily_change=15, volatility=20, seed=20)
df_index = df_index.rename(columns={"close": "close"})[["date", "close"]]

save_prices("TESTAG.DE", df_stock)
save_index_prices("DAX", df_index)

result = calculate_score("TESTAG.DE", date.today(), "DAX")

check("Szenario A: Ergebnis nicht None", result is not None)
check("Szenario A: filter_sma50 == 1", result["filter_sma50"] == 1)
check("Szenario A: score_total ist int", isinstance(result["score_total"], int))
check("Szenario A: score_total zwischen 0 und 100",
      result["score_total"] is not None and 0 <= result["score_total"] <= 100,
      f"(score_total={result['score_total']})")
check("Szenario A: rating gesetzt", result["rating"] in
      ("Starkes Kaufsignal", "Interessant", "Beobachten", "Kein Kauf"),
      f"(rating={result['rating']})")
check("Szenario A: regime == 'positiv' (Index steigt deutlich)",
      result["regime"] == "positiv", f"(regime={result['regime']})")

print(f"    -> Score={result['score_total']}, Rating={result['rating']}, "
      f"Regime={result['regime']}, SMA200={result['score_sma200']}, "
      f"RS={result['score_rs']}, Breakout={result['score_breakout']}, "
      f"Risk={result['score_risk']}")

# In DB gespeichert?
detail = get_score_detail("TESTAG.DE")
check("Szenario A: in DB gespeichert (get_score_detail)", detail is not None)
check("Szenario A: DB-Score == Rückgabewert",
      detail is not None and detail["score_total"] == result["score_total"])


# -----------------------------------------------------------------------------
print("\n=== E2E-Test: Hard Filter greift (Abwärtstrend) ===")

df_stock_down = make_price_series(n, start=150, daily_change=-0.30, volatility=0.5, seed=30)
save_prices("FALLAG.DE", df_stock_down)

result = calculate_score("FALLAG.DE", date.today(), "DAX")

check("Hard Filter: Ergebnis nicht None", result is not None)
check("Hard Filter: filter_sma50 == 0", result["filter_sma50"] == 0)
check("Hard Filter: score_total is None", result["score_total"] is None)
check("Hard Filter: rating is None", result["rating"] is None)

detail = get_score_detail("FALLAG.DE")
check("Hard Filter: trotzdem in DB (score_total NULL)", detail is not None and detail["score_total"] is None)


# -----------------------------------------------------------------------------
print("\n=== E2E-Test: Sperrregel bei negativem Marktregime ===")

# Aktie stark im Aufwärtstrend, aber Index fällt -> Regime negativ -> Score gekappt bei 69
df_stock_strong = make_price_series(n, start=100, daily_change=0.40, volatility=0.3, seed=40)
df_index_falling = make_price_series(n, start=20000, daily_change=-25, volatility=20, seed=50)
df_index_falling = df_index_falling[["date", "close"]]

save_prices("STARKAG.DE", df_stock_strong)
save_index_prices("DAX2", df_index_falling)

result = calculate_score("STARKAG.DE", date.today(), "DAX2")

check("Sperrregel: Ergebnis nicht None", result is not None)
check("Sperrregel: regime == 'negativ'", result["regime"] == "negativ", f"(regime={result['regime']})")
if result["regime"] in ("neutral", "negativ"):
    check("Sperrregel: score_total <= 69", result["score_total"] <= 69,
          f"(score_total={result['score_total']})")
    check("Sperrregel: rating in ('Beobachten','Kein Kauf')",
          result["rating"] in ("Beobachten", "Kein Kauf"), f"(rating={result['rating']})")

print(f"    -> Score={result['score_total']}, Rating={result['rating']}, Regime={result['regime']}")


# -----------------------------------------------------------------------------
print("\n=== E2E-Test: Fehlerfall — keine Daten in DB ===")

result = calculate_score("UNBEKANNT.DE", date.today(), "DAX")
check("Kein Daten: Rückgabe None", result is None)


# =============================================================================
print("\n" + "=" * 60)
print(f"ERGEBNIS: {len(PASS)} bestanden, {len(FAIL)} fehlgeschlagen")
print("=" * 60)

# Aufräumen
if os.path.exists("test_scorer.db"):
    os.remove("test_scorer.db")

if FAIL:
    for f in FAIL:
        print(f"  - {f}")
    sys.exit(1)
sys.exit(0)
