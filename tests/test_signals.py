"""
tests/test_signals.py — Unit-Tests für Phase 2 (Signalberechnung)
Aktien-Scanner V1

Ausführung: python tests/test_signals.py
Verwendet synthetische Beispieldaten, kein Internetzugang nötig.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd

from utils.logging_config import setup_logging
setup_logging()

from signals.filter_sma50 import check_sma50
from signals.sma200 import calc_sma200
from signals.relative_strength import calc_rs
from signals.breakout import calc_breakout, find_resistance
from signals.regime import calc_regime
from signals.risk import calc_atr, calc_risk
from scoring.scorer import assign_rating


# =============================================================================
# Hilfsfunktionen: synthetische Daten erzeugen
# =============================================================================

from tests.helpers import make_price_series


# =============================================================================
# Tests
# =============================================================================

PASS = []
FAIL = []


def check(name: str, condition: bool, detail: str = ""):
    if condition:
        PASS.append(name)
        print(f"  ✓ {name}")
    else:
        FAIL.append(name)
        print(f"  ✗ {name}  {detail}")


# -----------------------------------------------------------------------------
print("\n=== Test 1: Hard Filter SMA50 ===")

# Aktie deutlich über SMA50 -> sollte bestehen
# Starker, klarer Aufwärtstrend: aktueller Kurs muss > SMA50 * 0.98 sein
df_up = make_price_series(60, start=100, daily_change=0.8, volatility=0.2)
ok, sma50 = check_sma50(df_up)
check("SMA50: Aufwärtstrend -> Filter bestanden", ok is True, f"(ok={ok}, sma50={sma50})")

# Aktie deutlich unter SMA50 -> sollte nicht bestehen
df_down = make_price_series(60, start=100, daily_change=-0.8, volatility=0.2)
ok, sma50 = check_sma50(df_down)
check("SMA50: Abwärtstrend -> Filter nicht bestanden", ok is False, f"(ok={ok}, sma50={sma50})")

# Zu wenig Daten
df_short = make_price_series(30, start=100)
ok, sma50 = check_sma50(df_short)
check("SMA50: Zu wenig Daten -> (False, None)", ok is False and sma50 is None)


# -----------------------------------------------------------------------------
print("\n=== Test 2: Signal 1 — SMA200 ===")

# Aktie 13% über SMA200 (Beispiel aus Spezifikation: SAP 182 vs SMA200 161 -> +13%)
df_sma200_pos = make_price_series(210, start=161, daily_change=0.10)
punkte, sma200, status = calc_sma200(df_sma200_pos)
check("SMA200: Positiver Trend -> 15 Punkte", punkte == 15, f"(punkte={punkte}, status={status})")
check("SMA200: status == 'positiv'", status == "positiv")

# Aktie 13% unter SMA200 -> negativ
df_sma200_neg = make_price_series(210, start=200, daily_change=-0.10)
punkte, sma200, status = calc_sma200(df_sma200_neg)
check("SMA200: Negativer Trend -> 0 Punkte", punkte == 0, f"(punkte={punkte}, status={status})")

# Zu wenig Daten
df_short = make_price_series(100, start=100)
punkte, sma200, status = calc_sma200(df_short)
check("SMA200: Zu wenig Daten -> (0, None, 'keine_daten')",
      punkte == 0 and sma200 is None and status == "keine_daten")


# -----------------------------------------------------------------------------
print("\n=== Test 3: Signal 2 — Relative Stärke ===")

# Aktie +8,57% in 20 Tagen, Index +3,85% -> RS = +4,72% -> 18 Punkte (Beispiel Adidas/DAX)
n = 30
_all_d = pd.date_range(end=pd.Timestamp.today(), periods=n*2, freq="D"); dates = _all_d[_all_d.day_of_week < 5][-n:]

stock_closes = np.linspace(210, 228, n)  # +8,57% über die Periode
index_closes = np.linspace(18200, 18900, n)  # +3,85%

df_stock = pd.DataFrame({"date": dates, "close": stock_closes, "adj_close": stock_closes,
                         "open": stock_closes, "high": stock_closes, "low": stock_closes,
                         "volume": 1_000_000})
df_index = pd.DataFrame({"date": dates, "close": index_closes})

punkte, rs_score = calc_rs(df_stock, df_index)
check("RS: rs_score im Bereich 2-5% (stark)", rs_score is not None and 2.0 < rs_score < 5.0, f"(rs_score={rs_score:.2f})")
check("RS: 18 Punkte für 'stark' (2-5%)", punkte == 18, f"(punkte={punkte})")

# Aktie schwächer als Index -> niedrige Punkte
df_stock_weak = pd.DataFrame({"date": dates, "close": np.linspace(100, 95, n),
                               "adj_close": np.linspace(100, 95, n),
                               "open": 100, "high": 100, "low": 100, "volume": 1_000_000})
punkte, rs_score = calc_rs(df_stock_weak, df_index)
check("RS: Schwache Aktie -> 0 Punkte", punkte == 0, f"(rs_score={rs_score:.2f}, punkte={punkte})")

# Zu wenig Daten
punkte, rs_score = calc_rs(df_stock.head(10), df_index)
check("RS: Zu wenig Daten -> (0, None)", punkte == 0 and rs_score is None)


# -----------------------------------------------------------------------------
print("\n=== Test 4: Signal 3 — Breakout ===")

# Konstruiere einen klaren Breakout:
# - 20 Tage seitwärts um 100 (Widerstand bei 100, mehrfach getestet)
# - Letzter Tag: Ausbruch auf 102 mit hohem Volumen, Close nahe High

n_pre = 50  # ausreichend für MIN_ROWS (20+20+3+5=48)
sideways = 100 + np.sin(np.linspace(0, 6 * np.pi, n_pre)) * 0.3  # oszilliert eng um 100
sideways[-5] = 100.0
sideways[-10] = 100.0
sideways[-15] = 99.9

_all_b = pd.date_range(end=pd.Timestamp.today(), periods=(n_pre+1)*2, freq="D"); dates_b = _all_b[_all_b.day_of_week < 5][-(n_pre+1):]

closes = list(sideways) + [102.0]  # Breakout heute
highs = [c + 0.2 for c in closes]
highs[-1] = 102.3
lows = [c - 0.2 for c in closes]
lows[-1] = 101.5
volumes = [1_000_000] * n_pre + [2_000_000]  # heute: 2x Volumen

df_breakout = pd.DataFrame({
    "date": dates_b, "close": closes, "adj_close": closes,
    "open": closes, "high": highs, "low": lows, "volume": volumes,
})

punkte, flag, age = calc_breakout(df_breakout)
check("Breakout: heute vollständig -> 30 Punkte", punkte == 30, f"(punkte={punkte}, flag={flag}, age={age})")
check("Breakout: breakout_flag == True", flag is True)
check("Breakout: age == 0", age == 0)

# find_resistance auf reinen Seitwärtsdaten -> sollte ~100 finden
resistance = find_resistance(df_breakout.iloc[-21:-1])
check("Breakout: Widerstand bei ~100 gefunden", resistance is not None and 99.5 < resistance < 100.5,
      f"(resistance={resistance})")

# Kein Breakout: flacher Seitwärtsmarkt ohne Ausbruch
df_no_breakout = make_price_series(70, start=100, daily_change=0.0, volatility=0.1)
punkte, flag, age = calc_breakout(df_no_breakout)
check("Breakout: kein Ausbruch -> flag == False", flag is False, f"(punkte={punkte}, flag={flag})")

# Zu wenig Daten
punkte, flag, age = calc_breakout(df_breakout.head(20))
check("Breakout: Zu wenig Daten -> (0, False, None)", punkte == 0 and flag is False and age is None)


# -----------------------------------------------------------------------------
print("\n=== Test 5: Signal 4 — Marktregime ===")

# Index 4,6% über SMA200 (Beispiel: S&P 500 5280 vs SMA200 5050)
df_regime_pos = make_price_series(210, start=5050, daily_change=1.1)
df_regime_pos = df_regime_pos.rename(columns={"close": "close"})[["date", "close"]]
punkte, status = calc_regime(df_regime_pos)
check("Regime: Positiv -> 15 Punkte", punkte == 15, f"(punkte={punkte}, status={status})")

# Index unter SMA200 -> negativ
df_regime_neg = make_price_series(210, start=5500, daily_change=-1.1)[["date", "close"]]
punkte, status = calc_regime(df_regime_neg)
check("Regime: Negativ -> 0 Punkte", punkte == 0, f"(punkte={punkte}, status={status})")

# Zu wenig Daten
punkte, status = calc_regime(df_regime_pos.head(50))
check("Regime: Zu wenig Daten -> (0, 'keine_daten')", punkte == 0 and status == "keine_daten")


# -----------------------------------------------------------------------------
print("\n=== Test 6: Signal 5 — Risiko/CRV (ATR-basiert) ===")

# Beispiel aus Spezifikation: Adidas
# Close=228, ATR14=4.80 -> Stop=220.80, Risiko=7.20
# 60-Tage-Hoch=242 -> Kursziel=242, CRV=(242-228)/7.20=1.94 -> 7 Punkte (CRV>=1.5, ATR_Ratio<=5%)

n = 65
_all_r = pd.date_range(end=pd.Timestamp.today(), periods=n*2, freq="D"); dates_r = _all_r[_all_r.day_of_week < 5][-n:]

# Konstante Range für stabile ATR-Berechnung
np.random.seed(1)
base = 228.0
closes_r = np.full(n, base)
closes_r[10] = 242.0  # 60-Tage-Hoch im Lookback-Fenster (Index 10, also vor "heute")
highs_r = closes_r + 2.4  # TR = 4.8 (High-Low)
lows_r = closes_r - 2.4
highs_r[10] = 244.0
lows_r[10] = 240.0

df_risk = pd.DataFrame({
    "date": dates_r, "close": closes_r, "adj_close": closes_r,
    "open": closes_r, "high": highs_r, "low": lows_r, "volume": 1_000_000,
})

atr = calc_atr(df_risk)
check("Risk: ATR14 ≈ 4.8", atr is not None and 4.0 < atr < 5.6, f"(atr={atr:.2f})" if atr else "")

punkte, stop_loss, crv, atr14, atr_ratio, kursziel = calc_risk(df_risk)
check("Risk: Stop-Loss ≈ Close - 1.5×ATR", stop_loss is not None and 218 < stop_loss < 222,
      f"(stop_loss={stop_loss})")
check("Risk: Kursziel == 242 (60-Tage-Hoch)", kursziel is not None and 241 < kursziel < 243,
      f"(kursziel={kursziel})")
check("Risk: CRV ≈ 1.9-2.0", crv is not None and 1.5 < crv < 2.5, f"(crv={crv})")
check("Risk: Punkte in {7,10}", punkte in (7, 10), f"(punkte={punkte}, atr_ratio={atr_ratio})")

# Sonderfall: Aktie auf Allzeithoch -> kein Kursziel definierbar
closes_ath = np.linspace(100, 150, n)  # stetig steigend, letzter Wert = Maximum
highs_ath = closes_ath + 1
lows_ath = closes_ath - 1
df_ath = pd.DataFrame({
    "date": dates_r, "close": closes_ath, "adj_close": closes_ath,
    "open": closes_ath, "high": highs_ath, "low": lows_ath, "volume": 1_000_000,
})
punkte, stop_loss, crv, atr14, atr_ratio, kursziel = calc_risk(df_ath)
check("Risk: Allzeithoch -> crv is None", crv is None)
check("Risk: Allzeithoch -> punkte == CRV_FALLBACK_POINTS (3)", punkte == 3, f"(punkte={punkte})")
check("Risk: Allzeithoch -> kursziel is None", kursziel is None)

# Zu wenig Daten
punkte, stop_loss, crv, atr14, atr_ratio, kursziel = calc_risk(df_risk.head(10))
check("Risk: Zu wenig Daten -> (0, None, None, None, None, None)",
      punkte == 0 and stop_loss is None and crv is None)


# -----------------------------------------------------------------------------
print("\n=== Test 7: Bewertungsstufen (assign_rating) ===")

check("Rating: 90 -> 'Starkes Kaufsignal'", assign_rating(90) == "Starkes Kaufsignal")
check("Rating: 85 -> 'Starkes Kaufsignal'", assign_rating(85) == "Starkes Kaufsignal")
check("Rating: 84 -> 'Interessant'", assign_rating(84) == "Interessant")
check("Rating: 70 -> 'Interessant'", assign_rating(70) == "Interessant")
check("Rating: 69 -> 'Beobachten'", assign_rating(69) == "Beobachten")
check("Rating: 55 -> 'Beobachten'", assign_rating(55) == "Beobachten")
check("Rating: 54 -> 'Kein Kauf'", assign_rating(54) == "Kein Kauf")
check("Rating: 0 -> 'Kein Kauf'", assign_rating(0) == "Kein Kauf")


# -----------------------------------------------------------------------------
print("\n=== Test 8: Score-Aggregation inkl. Sperrregel (ohne DB) ===")

# Simuliere Sperrregel manuell: alle Signale maximal + Regime neutral -> Cap bei 69
score_sma200, score_rs, score_breakout, score_regime, score_risk = 15, 25, 30, 7, 15
total = score_sma200 + score_rs + score_breakout + score_regime + score_risk
check("Aggregation: Summe ohne Cap == 92", total == 92, f"(total={total})")

REGIME_SCORE_CAP = 69
regime_status = "neutral"
if regime_status in ("neutral", "negativ"):
    total_capped = min(total, REGIME_SCORE_CAP)
else:
    total_capped = total

check("Aggregation: Sperrregel kappt 92 -> 69", total_capped == 69, f"(total_capped={total_capped})")
check("Aggregation: Rating nach Sperrregel == 'Beobachten'",
      assign_rating(total_capped) == "Beobachten", f"(rating={assign_rating(total_capped)})")

# Ohne Sperrregel (Regime positiv): Summe bleibt 92
regime_status = "positiv"
total_no_cap = total if regime_status == "positiv" else min(total, REGIME_SCORE_CAP)
check("Aggregation: Regime positiv -> kein Cap, Score == 92", total_no_cap == 92)
check("Aggregation: Rating ohne Cap == 'Starkes Kaufsignal'",
      assign_rating(total_no_cap) == "Starkes Kaufsignal")


# =============================================================================
# Zusammenfassung
# =============================================================================
print("\n" + "=" * 60)
print(f"ERGEBNIS: {len(PASS)} bestanden, {len(FAIL)} fehlgeschlagen")
print("=" * 60)

if FAIL:
    print("\nFehlgeschlagene Tests:")
    for f in FAIL:
        print(f"  - {f}")
    sys.exit(1)
else:
    print("\nAlle Tests bestanden.")
    sys.exit(0)
