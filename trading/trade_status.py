"""
trading/trade_status.py — Handelsstatus-Entscheidungsebene
Aktien-Scanner V1

Setzt Phase 2 der Detailkarten-Überarbeitung um: Der Score allein ist
keine Handlungsempfehlung. Status hängt zusätzlich davon ab,
  - wie gut das CRV ist (trade_crv, einstiegsbasiert),
  - wie alt das Breakout-Signal ist,
  - und vor allem: ob der aktuelle Kurs den Stop-Buy bereits erreicht hat.

Der letzte Punkt steht NICHT explizit in der ursprünglichen Spezifikation,
ist aber notwendig, um "KAUFEN" (jetzt sofort handelbar) von "STOP-BUY"
(Trigger noch nicht erreicht) sauber zu trennen — sonst würde KAUFEN auch
für Setups ausgegeben, deren Einstiegskurs noch gar nicht erreicht ist.

Bewusst ein eigenständiges Modul außerhalb von scoring/ — der gesperrte
100-Punkte-Score bleibt davon vollständig unberührt.
"""

from typing import Optional

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    TRADE_STATUS_KAUFEN_MIN_SCORE, TRADE_STATUS_KAUFEN_MAX_SIGNALALTER,
    TRADE_STATUS_KAUFEN_MIN_CRV, TRADE_STATUS_STOPBUY_MIN_SCORE,
    TRADE_STATUS_BEOBACHTEN_MIN_SCORE, TRADE_STATUS_VERPASST_BUFFER_PCT,
    TRADE_STATUS_AMPEL, TRADE_STATUS_RANK, TRADE_CRV_COLOR_STUFEN,
)

VERWERFEN = "VERWERFEN"
BEOBACHTEN = "BEOBACHTEN"
STOP_BUY = "STOP-BUY"
KAUFEN = "KAUFEN"
VERPASST = "VERPASST"


def has_required_trade_fields(detail: dict) -> bool:
    """
    Prüft, ob die für eine Handelsentscheidung zwingend nötigen Felder
    vorhanden sind (aktueller Kurs, Stop-Buy, Stop-Loss).

    Fehlen diese, ist es eine echte Datenlücke (z.B. Preis-JOIN, fehlende
    Historie) — NICHT zu verwechseln mit dem legitimen ATH-Sonderfall, bei
    dem nur kursziel/trade_chance_pct/trade_crv fehlen, der Kandidat aber
    sehr wohl ein gültiges, anzeigbares Setup ist.

    Wird verwendet, um Kandidaten mit Datenlücken aus der Top-Liste
    auszuschließen (siehe app/streamlit_app.py).
    """
    return (
        detail.get("price_close") is not None
        and detail.get("stop_buy") is not None
        and detail.get("stop_loss") is not None
    )


def determine_trade_status(detail: dict) -> str:
    """
    Bestimmt den Handelsstatus für einen Score-/Trade-Eintrag.

    Erwartet im dict (alle aus get_score_detail() / scores-Tabelle):
        score_total, breakout_age, trade_crv, price_close, stop_buy

    Priorität (erste zutreffende Regel gewinnt):
      1. VERWERFEN   — score_total fehlt oder < BEOBACHTEN-Schwelle
      2. VERPASST    — Setup war gültig, Kurs aber bereits deutlich
                        (>= VERPASST_BUFFER_PCT) über dem Stop-Buy-Niveau
      3. KAUFEN      — Top-Score, frischer Breakout, gutes CRV UND
                        Stop-Buy bereits erreicht (sofort handelbar)
      4. STOP-BUY    — guter Score, Stop-Buy aber noch nicht erreicht
      5. BEOBACHTEN  — alles Übrige mit Mindest-Score (z.B. bereits
                        getriggert, aber CRV/Signalalter reichen nicht für
                        KAUFEN; oder kein Kursziel bestimmbar / ATH-Fall)
    """
    score_total = detail.get("score_total")
    breakout_age = detail.get("breakout_age")
    trade_crv = detail.get("trade_crv")
    price_close = detail.get("price_close")
    stop_buy = detail.get("stop_buy")

    if score_total is None or score_total < TRADE_STATUS_BEOBACHTEN_MIN_SCORE:
        return VERWERFEN

    # Trigger-Vergleich nur möglich, wenn beide Werte vorhanden sind.
    triggered: Optional[bool] = None
    if price_close is not None and stop_buy is not None and stop_buy > 0:
        triggered = price_close >= stop_buy
        ueberschreitung_pct = (price_close - stop_buy) / stop_buy * 100
        if triggered and ueberschreitung_pct >= TRADE_STATUS_VERPASST_BUFFER_PCT:
            return VERPASST

    if (
        score_total >= TRADE_STATUS_KAUFEN_MIN_SCORE
        and breakout_age is not None
        and breakout_age <= TRADE_STATUS_KAUFEN_MAX_SIGNALALTER
        and trade_crv is not None
        and trade_crv >= TRADE_STATUS_KAUFEN_MIN_CRV
        and triggered is True
    ):
        return KAUFEN

    if score_total >= TRADE_STATUS_STOPBUY_MIN_SCORE and triggered is False:
        return STOP_BUY

    return BEOBACHTEN


def ampel_for_status(status: str) -> str:
    """Gibt 'gruen' | 'gelb' | 'rot' für einen Handelsstatus zurück."""
    return TRADE_STATUS_AMPEL.get(status, "gelb")


def rank_for_status(status: str) -> int:
    """Sortier-Rang für Phase 4 (kleiner = weiter oben)."""
    return TRADE_STATUS_RANK.get(status, 99)


def crv_color(trade_crv: Optional[float]) -> dict:
    """
    Ordnet einem trade_crv-Wert Farbe + Label gemäß Phase-3-Farbskala zu.

    Returns:
        dict mit 'farbe' (Hex) und 'label'. Bei trade_crv=None wird die
        unterste Stufe (Ungünstig/rot) NICHT verwendet — stattdessen
        Grau, da "nicht bestimmbar" inhaltlich etwas anderes ist als
        "schlechtes CRV".
    """
    if trade_crv is None:
        return {"farbe": "#95a5a6", "label": "Nicht bestimmbar"}

    for stufe in TRADE_CRV_COLOR_STUFEN:
        if stufe["crv_min"] is None or trade_crv >= stufe["crv_min"]:
            return {"farbe": stufe["farbe"], "label": stufe["label"]}

    return {"farbe": "#95a5a6", "label": "Nicht bestimmbar"}
