"""
tests/test_ai_summary.py — Tests für scoring/ai_summary.py
Aktien-Scanner V1 — Phase 5

Alle Tests laufen mit gemockter Anthropic-API, kein echter API-Call.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import patch, MagicMock

from utils.logging_config import setup_logging
setup_logging()

import config
from scoring.ai_summary import build_user_prompt, generate_summary, SYSTEM_PROMPT

PASS, FAIL = [], []

def check(name, cond, detail=""):
    if cond:
        PASS.append(name); print(f"  ✓ {name}")
    else:
        FAIL.append(name); print(f"  ✗ {name}  {detail}")


# -----------------------------------------------------------------------------
# Beispiel-Score-Dict (vollständig, wie von get_score_detail geliefert)
# -----------------------------------------------------------------------------
SCORE_DICT_FULL = {
    "ticker": "SAP.DE",
    "name": "SAP SE",
    "date": "2026-06-12",
    "signal_version": "V1",
    "data_source": "yfinance",
    "filter_sma50": 1,
    "score_sma200": 15,
    "score_rs": 18,
    "score_breakout": 12,
    "score_regime": 15,
    "score_risk": 3,
    "score_total": 63,
    "rating": "Beobachten",
    "sma50": 186.52,
    "sma200": 160.13,
    "rs_score": 4.2,
    "breakout_flag": 0,
    "breakout_age": None,
    "regime": "positiv",
    "stop_loss": 184.0,
    "crv": None,
    "atr14": 1.54,
    "atr_ratio": 0.78,
    "kursziel": None,
}

SCORE_DICT_HARD_FILTER = {
    "ticker": "VOW3.DE",
    "name": "Volkswagen AG",
    "filter_sma50": 0,
    "score_total": None,
    "rating": None,
}


# =============================================================================
# Test 1: build_user_prompt() — Input ausschließlich aus Signalwerten
# =============================================================================
print("\n=== Test 1: build_user_prompt() ===")

prompt = build_user_prompt(SCORE_DICT_FULL)

check("Prompt enthält Ticker", "SAP.DE" in prompt)
check("Prompt enthält Name", "SAP SE" in prompt)
check("Prompt enthält Gesamtscore", "63" in prompt)
check("Prompt enthält Bewertung", "Beobachten" in prompt)
check("Prompt enthält SMA200-Punkte", "15 von 15 Punkten" in prompt)
check("Prompt enthält RS-Punkte", "18 von 25 Punkten" in prompt)
check("Prompt enthält Breakout-Punkte", "12 von 30 Punkten" in prompt)
check("Prompt enthält Regime-Punkte", "15 von 15 Punkten" in prompt)
check("Prompt enthält Risiko-Punkte", "3 von 15 Punkten" in prompt)
check("Prompt enthält RS-Wert (+4.2%)", "+4.2%" in prompt)
check("Prompt enthält Stop-Loss", "184.00" in prompt)
check("Prompt enthält Marktregime-Text (positiv)",
      "Aufwärtstrend" in prompt)

# Sonderfall: kein CRV/Kursziel -> Text statt None
check("Prompt: CRV='nicht bestimmbar' bei crv=None",
      "nicht bestimmbar (Aktie nahe Hochpunkt)" in prompt)
check("Prompt: Kursziel='nicht bestimmbar' bei kursziel=None",
      "Kursziel: nicht bestimmbar" in prompt)

# Keine erfundenen/zusätzlichen Werte: Prompt darf keine Zahlen enthalten,
# die nicht aus score_dict stammen (Stichprobe: kein zufälliger Kurswert)
check("Prompt enthält keinen 'Tagesschlusskurs' o.ä. unbekannten Begriff",
      "Tagesschlusskurs" not in prompt and "aktueller Kurs:" not in prompt)


# -----------------------------------------------------------------------------
# Breakout-Varianten
# -----------------------------------------------------------------------------
print("\n=== Test 1b: build_user_prompt() Breakout-Varianten ===")

d_breakout_today = {**SCORE_DICT_FULL, "breakout_flag": 1, "breakout_age": 0}
p = build_user_prompt(d_breakout_today)
check("Breakout heute -> 'Ja, heute'", "Ja, heute" in p)

d_breakout_old = {**SCORE_DICT_FULL, "breakout_flag": 1, "breakout_age": 2}
p = build_user_prompt(d_breakout_old)
check("Breakout vor 2 Tagen -> 'Ja, vor 2 Handelstag(en)'", "Ja, vor 2 Handelstag(en)" in p)

d_no_breakout = {**SCORE_DICT_FULL, "breakout_flag": 0, "breakout_age": None}
p = build_user_prompt(d_no_breakout)
check("Kein Breakout -> 'Nein'", "vorhanden: Nein" in p)


# =============================================================================
# Test 2: generate_summary() — Erfolgsfall (gemockt)
# =============================================================================
print("\n=== Test 2: generate_summary() Erfolgsfall ===")

mock_text_block = MagicMock()
mock_text_block.type = "text"
mock_text_block.text = "SAP zeigt einen soliden langfristigen Aufwärtstrend und ist stärker als der Markt. " \
                        "Ein Ausbruch hat noch nicht vollständig bestätigt. Das Chance-Risiko-Verhältnis " \
                        "ist aktuell nicht eindeutig bestimmbar, da die Aktie nahe ihrem Hochpunkt steht."

mock_response = MagicMock()
mock_response.content = [mock_text_block]

with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key-123"}):
    with patch("anthropic.Anthropic") as MockAnthropic:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        MockAnthropic.return_value = mock_client

        result = generate_summary(SCORE_DICT_FULL)

check("Erfolgsfall: success == True", result["success"] is True, f"(result={result})")
check("Erfolgsfall: text vorhanden", result["text"] is not None and len(result["text"]) > 0)
check("Erfolgsfall: error is None", result["error"] is None)
check("Erfolgsfall: Text enthält keine erfundenen Kurswerte (kein '€' im Mock-Text)",
      "€" not in result["text"])

# Prüfen: API wurde mit korrektem Modell, max_tokens, system-Prompt aufgerufen
call_kwargs = mock_client.messages.create.call_args.kwargs
check("API-Call: model == config.AI_MODEL", call_kwargs["model"] == config.AI_MODEL,
      f"(model={call_kwargs['model']})")
check("API-Call: max_tokens == config.AI_MAX_TOKENS",
      call_kwargs["max_tokens"] == config.AI_MAX_TOKENS)
check("API-Call: system-Prompt == SYSTEM_PROMPT (unverändert aus Pflichtenheft)",
      call_kwargs["system"] == SYSTEM_PROMPT)
check("API-Call: Erfinde-keine-Kurse-Anweisung im System-Prompt",
      "Erfinde keine Kurse" in call_kwargs["system"])
check("API-Call: Keine-Kaufempfehlung-Anweisung im System-Prompt",
      "Mach keine Kaufempfehlung" in call_kwargs["system"])
check("API-Call: genau 1 User-Message",
      len(call_kwargs["messages"]) == 1 and call_kwargs["messages"][0]["role"] == "user")


# =============================================================================
# Test 3: generate_summary() — kein API-Key
# =============================================================================
print("\n=== Test 3: generate_summary() ohne API-Key ===")

env_without_key = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
with patch.dict(os.environ, env_without_key, clear=True):
    result = generate_summary(SCORE_DICT_FULL)

check("Ohne API-Key: success == False", result["success"] is False)
check("Ohne API-Key: text is None", result["text"] is None)
check("Ohne API-Key: verständliche Fehlermeldung", result["error"] is not None and len(result["error"]) > 0,
      f"(error={result['error']})")


# =============================================================================
# Test 4: generate_summary() — Verbindungsfehler
# =============================================================================
print("\n=== Test 4: generate_summary() Verbindungsfehler ===")

import anthropic

with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key-123"}):
    with patch("anthropic.Anthropic") as MockAnthropic:
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = anthropic.APIConnectionError(
            request=MagicMock()
        )
        MockAnthropic.return_value = mock_client

        result = generate_summary(SCORE_DICT_FULL)

check("Verbindungsfehler: success == False", result["success"] is False)
check("Verbindungsfehler: kein Absturz (Exception abgefangen)", True)  # implizit durch Erreichen dieser Zeile
check("Verbindungsfehler: verständliche Fehlermeldung",
      "Internetverbindung" in result["error"], f"(error={result['error']})")


# =============================================================================
# Test 5: generate_summary() — Rate-Limit-Fehler
# =============================================================================
print("\n=== Test 5: generate_summary() Rate-Limit ===")

with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key-123"}):
    with patch("anthropic.Anthropic") as MockAnthropic:
        mock_client = MagicMock()
        mock_response_429 = MagicMock()
        mock_response_429.status_code = 429
        mock_response_429.headers = {}
        mock_client.messages.create.side_effect = anthropic.RateLimitError(
            message="rate limit", response=mock_response_429, body=None
        )
        MockAnthropic.return_value = mock_client

        result = generate_summary(SCORE_DICT_FULL)

check("Rate-Limit: success == False", result["success"] is False)
check("Rate-Limit: verständliche Fehlermeldung", "ausgelastet" in result["error"],
      f"(error={result['error']})")


# =============================================================================
# Test 6: generate_summary() — allgemeiner API-Statusfehler
# =============================================================================
print("\n=== Test 6: generate_summary() API-Statusfehler (z.B. 500) ===")

with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key-123"}):
    with patch("anthropic.Anthropic") as MockAnthropic:
        mock_client = MagicMock()
        mock_response_500 = MagicMock()
        mock_response_500.status_code = 500
        mock_response_500.headers = {}
        mock_client.messages.create.side_effect = anthropic.APIStatusError(
            message="server error", response=mock_response_500, body=None
        )
        MockAnthropic.return_value = mock_client

        result = generate_summary(SCORE_DICT_FULL)

check("API-Statusfehler: success == False", result["success"] is False)
check("API-Statusfehler: verständliche Fehlermeldung", result["error"] is not None)


# =============================================================================
# Test 7: generate_summary() — unerwartete Exception
# =============================================================================
print("\n=== Test 7: generate_summary() unerwartete Exception ===")

with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key-123"}):
    with patch("anthropic.Anthropic") as MockAnthropic:
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = ValueError("Irgendwas Unerwartetes")
        MockAnthropic.return_value = mock_client

        result = generate_summary(SCORE_DICT_FULL)

check("Unerwartete Exception: success == False", result["success"] is False)
check("Unerwartete Exception: kein Absturz, verständliche Meldung",
      result["error"] is not None and len(result["error"]) > 0)


# =============================================================================
# Test 8: generate_summary() — leere KI-Antwort
# =============================================================================
print("\n=== Test 8: generate_summary() leere Antwort ===")

mock_response_empty = MagicMock()
mock_response_empty.content = []

with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key-123"}):
    with patch("anthropic.Anthropic") as MockAnthropic:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response_empty
        MockAnthropic.return_value = mock_client

        result = generate_summary(SCORE_DICT_FULL)

check("Leere Antwort: success == False", result["success"] is False)
check("Leere Antwort: verständliche Fehlermeldung", result["error"] is not None)


# =============================================================================
# Test 9: generate_summary() — Hard-Filter-Fall (score_total is None)
# =============================================================================
print("\n=== Test 9: generate_summary() Hard-Filter-Fall ===")

result = generate_summary(SCORE_DICT_HARD_FILTER)

check("Hard-Filter: success == False", result["success"] is False)
check("Hard-Filter: kein API-Aufruf nötig (kein API-Key gesetzt, trotzdem korrekt)",
      result["error"] is not None)
check("Hard-Filter: Fehlermeldung erklärt fehlenden Score",
      "kein Score" in result["error"])

result_none = generate_summary(None)
check("None-Input: success == False", result_none["success"] is False)


# =============================================================================
# Test 10: System-Prompt entspricht exakt Pflichtenheft-Vorgabe
# =============================================================================
print("\n=== Test 10: System-Prompt-Inhalt (Pflichtenheft-Vorgaben) ===")

required_phrases = [
    "sachlicher Finanzassistent",
    "berechnete Signalwerte",
    "einfacher Sprache",
    "Chancen und Risiken",
    "Erfinde keine Kurse",
    "Schätze keine Daten",
    "Mach keine Kaufempfehlung",
]
for phrase in required_phrases:
    check(f"System-Prompt enthält: '{phrase}'", phrase in SYSTEM_PROMPT)


# =============================================================================
print("\n" + "=" * 60)
print(f"ERGEBNIS: {len(PASS)} bestanden, {len(FAIL)} fehlgeschlagen")
print("=" * 60)

if os.path.exists("scanner.log"):
    os.remove("scanner.log")

if FAIL:
    for f in FAIL:
        print(f"  - {f}")
    sys.exit(1)
sys.exit(0)
