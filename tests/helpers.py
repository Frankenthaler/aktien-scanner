"""
tests/helpers.py — Gemeinsame Hilfsfunktionen für Tests
Aktien-Scanner V1
"""

import numpy as np
import pandas as pd


def make_price_series(n: int, start: float, daily_change: float = 0.0,
                       volatility: float = 0.5, seed: int = 42) -> pd.DataFrame:
    """
    Erzeugt einen synthetischen OHLCV-DataFrame mit n Zeilen.
    daily_change: durchschnittliche tägliche Veränderung (additiv)
    volatility: Streuung für High/Low um den Close

    Hinweis: pd.date_range(freq="B") liefert in pandas >= 2.2 manchmal n-1 Tage
    wenn today() auf einen Wochentag-Rand fällt. Workaround: Kalendertage
    erzeugen und auf die letzten n Werktage filtern.
    """
    rng = np.random.default_rng(seed)
    closes = [start]
    for _ in range(n - 1):
        closes.append(closes[-1] + daily_change + rng.normal(0, volatility * 0.1))

    closes = np.array(closes)
    highs = closes + np.abs(rng.normal(volatility, volatility * 0.3, n))
    lows = closes - np.abs(rng.normal(volatility, volatility * 0.3, n))
    opens = closes + rng.normal(0, volatility * 0.2, n)
    volumes = rng.integers(1_000_000, 2_000_000, n)

    # Stabile Werktage-Erzeugung: 2× Kalenderraum, Werktage filtern, letzte n nehmen
    _all = pd.date_range(end=pd.Timestamp.today(), periods=n * 2, freq="D")
    dates = _all[_all.day_of_week < 5][-n:]

    df = pd.DataFrame({
        "date": dates,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
        "adj_close": closes,
    })
    return df
