# =============================================================================
# config.py — Zentrale Parameterdatei
# Aktien-Scanner V1 | Alle Schwellenwerte und Konfigurationen hier
# Keine hardcodierten Werte in anderen Modulen.
# =============================================================================

# -----------------------------------------------------------------------------
# Universum
# -----------------------------------------------------------------------------
INDICES = {
    "DAX":    {"ticker": "^GDAXI", "market": "XETRA"},
    "SP500":  {"ticker": "^GSPC",  "market": "NYSE"},
    "NDX100": {"ticker": "^NDX",   "market": "NASDAQ"},
}

# Deduplizierung: Wenn Aktie in SP500 und NDX100 → SP500
DEDUP_PRIORITY = ["SP500", "NDX100", "DAX"]

# Mindesthistorie in Handelstagen
MIN_TRADING_DAYS = 210

# -----------------------------------------------------------------------------
# Hard Filter — SMA50
# -----------------------------------------------------------------------------
SMA50_PERIOD = 50
SMA50_BUFFER = 0.98  # Kurs muss > SMA50 × 0,98

# -----------------------------------------------------------------------------
# Signal 1 — Langfristiger Trend (SMA200)
# -----------------------------------------------------------------------------
SMA200_PERIOD = 200
SMA200_DATA_DAYS = 205      # + Puffer für fehlende Tage
SMA200_POSITIVE = 1.03
SMA200_NEGATIVE = 0.97
SMA200_POINTS = {
    "positiv": 15,
    "neutral": 7,
    "negativ": 0,
}

# -----------------------------------------------------------------------------
# Signal 2 — Relative Stärke
# -----------------------------------------------------------------------------
RS_PERIOD = 20              # Tage
RS_DATA_DAYS = 22           # + Puffer
RS_POINTS = [
    {"min": 5.0,  "points": 25},   # sehr stark
    {"min": 2.0,  "points": 18},   # stark
    {"min": 0.0,  "points": 12},   # neutral
    {"min": -2.0, "points": 5},    # schwach
    {"min": None, "points": 0},    # sehr schwach (Fallback)
]

# -----------------------------------------------------------------------------
# Signal 3 — Breakout
# -----------------------------------------------------------------------------
BREAKOUT_LOOKBACK = 20          # Tage für Widerstandssuche
BREAKOUT_BAND = 0.01            # ±1% Band für Widerstandstests
BREAKOUT_MIN_TESTS = 2          # Mindestanzahl Tests
BREAKOUT_MIN_CLOSE = 1.01       # Schlusskurs > Widerstand × 1,01
BREAKOUT_VOLUME_FACTOR = 1.5    # Volumen > SMA20 × 1,5
BREAKOUT_MAX_AGE = 3            # Maximales Alter in Handelstagen
BREAKOUT_POINTS = {
    "heute_vollstaendig": 30,
    "alt_vollstaendig":   24,
    "teilweise":          12,
    "nur_preis":          0,
    "kein_breakout":      0,
}

# -----------------------------------------------------------------------------
# Signal 4 — Marktregime
# -----------------------------------------------------------------------------
REGIME_SMA_PERIOD = 200
REGIME_DATA_DAYS = 205
REGIME_POSITIVE = 1.01
REGIME_NEGATIVE = 0.99
REGIME_POINTS = {
    "positiv": 15,
    "neutral": 7,
    "negativ": 0,
}
REGIME_SCORE_CAP = 69           # Maximaler Score bei Regime Neutral/Negativ

# -----------------------------------------------------------------------------
# Signal 5 — Risiko / CRV (ATR-basiert)
# -----------------------------------------------------------------------------
ATR_PERIOD = 14
ATR_DATA_DAYS = 15              # + 1 Puffer
ATR_MULTIPLIER = 1.5            # Stop-Loss = Kurs - ATR × 1,5
CRV_LOOKBACK = 60               # Tage für Kursziel (60-Tage-Hoch)
CRV_FALLBACK_POINTS = 3         # Punkte wenn kein Kursziel definierbar
RISK_POINTS = [
    {"crv_min": 3.0, "atr_max": 3.0, "points": 15},
    {"crv_min": 2.0, "atr_max": 4.0, "points": 10},
    {"crv_min": 1.5, "atr_max": 5.0, "points": 7},
    {"crv_min": 1.0, "atr_max": None,"points": 3},
    {"crv_min": None,"atr_max": None,"points": 0},
]

# -----------------------------------------------------------------------------
# Handelsstatus-Engine (Phase 2) — Entscheidungsebene, NICHT Teil des
# gesperrten 100-Punkte-Score-Systems oben. Bezieht sich auf trade_crv
# (einstiegsbasiert, siehe trading/trade_metrics.py), nicht auf 'crv'.
# -----------------------------------------------------------------------------
TRADE_STATUS_KAUFEN_MIN_SCORE = 85
TRADE_STATUS_KAUFEN_MAX_SIGNALALTER = 2        # Tage seit Breakout
TRADE_STATUS_KAUFEN_MIN_CRV = 2.0
TRADE_STATUS_STOPBUY_MIN_SCORE = 75
TRADE_STATUS_BEOBACHTEN_MIN_SCORE = 65
# Ab wie viel % oberhalb des Stop-Buy-Niveaus gilt der Einstieg als verpasst
TRADE_STATUS_VERPASST_BUFFER_PCT = 5.0

TRADE_STATUS_AMPEL = {
    "KAUFEN":     "gruen",
    "STOP-BUY":   "gelb",
    "BEOBACHTEN": "gelb",
    "VERPASST":   "rot",
    "VERWERFEN":  "rot",
}

# Sortierreihenfolge für Phase 4 (1 = oben in der Liste)
TRADE_STATUS_RANK = {
    "KAUFEN": 1,
    "STOP-BUY": 2,
    "BEOBACHTEN": 3,
    "VERPASST": 4,
    "VERWERFEN": 5,
}

# CRV-Farbskala (Phase 3) — angewendet auf trade_crv
TRADE_CRV_COLOR_STUFEN = [
    {"crv_min": 3.0, "farbe": "#1b5e20", "label": "Hervorragend"},
    {"crv_min": 2.0, "farbe": "#2e7d32", "label": "Gut"},
    {"crv_min": 1.5, "farbe": "#f9a825", "label": "Akzeptabel"},
    {"crv_min": 1.0, "farbe": "#ef6c00", "label": "Schwach"},
    {"crv_min": None, "farbe": "#c62828", "label": "Ungünstig"},
]

# -----------------------------------------------------------------------------
# Bewertungsstufen
# -----------------------------------------------------------------------------
RATING_THRESHOLDS = {
    "Starkes Kaufsignal": 85,
    "Interessant":        70,
    "Beobachten":         55,
    "Kein Kauf":          0,
}

# -----------------------------------------------------------------------------
# Signalversion
# -----------------------------------------------------------------------------
SIGNAL_VERSION = "V1"

# -----------------------------------------------------------------------------
# Scheduler-Zeiten (MEZ)
# -----------------------------------------------------------------------------
SCHEDULE_EUROPE_HOUR = 18
SCHEDULE_EUROPE_MINUTE = 30
SCHEDULE_USA_HOUR = 23
SCHEDULE_USA_MINUTE = 0

# -----------------------------------------------------------------------------
# KI-Komponente
# -----------------------------------------------------------------------------
AI_MODEL = "claude-sonnet-4-20250514"
AI_MAX_TOKENS = 300

# -----------------------------------------------------------------------------
# Datenbank
# -----------------------------------------------------------------------------
DB_PATH = "aktien_scanner.db"
LOG_PATH = "scanner.log"

# -----------------------------------------------------------------------------
# Fetcher
# -----------------------------------------------------------------------------
FETCH_RETRY_COUNT = 3
FETCH_RETRY_WAIT = 5        # Sekunden zwischen Retries
FETCH_REQUEST_PAUSE = 0.5   # Sekunden zwischen Requests (Rate Limiting)
