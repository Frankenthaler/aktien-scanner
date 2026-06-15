"""
scoring/ai_summary.py — KI-Zusammenfassung
Aktien-Scanner V1 — Phase 5

Erzeugt eine erklärende Zusammenfassung in einfacher Sprache auf Basis der
bereits berechneten Signalwerte einer Aktie (score_dict aus get_score_detail).

Pflichtenheft Abschnitt 7:
  - Die KI darf NUR erklären, nicht entscheiden.
  - Input ausschließlich berechnete Signalwerte (kein Internetzugriff,
    keine zusätzlichen Daten).
  - Keine erfundenen Kurse, keine geschätzten Daten, keine Kaufempfehlung.
  - Max. AI_MAX_TOKENS Tokens.

Fehlerbehandlung (Pflichtenheft Abschnitt 8):
  KI-API-Fehler -> Fehlermeldung im UI, kein Absturz.
"""

import logging

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import AI_MODEL, AI_MAX_TOKENS

logger = logging.getLogger(__name__)


# =============================================================================
# System-Prompt (gemäß Pflichtenheft Abschnitt 7, unverändert)
# =============================================================================

SYSTEM_PROMPT = """Du bist ein sachlicher Finanzassistent für private Anleger.
Du erhältst berechnete Signalwerte einer Aktie.
Erkläre die Situation in 3-4 Sätzen in einfacher Sprache.
Nenne Chancen und Risiken.
Erfinde keine Kurse. Schätze keine Daten.
Mach keine Kaufempfehlung."""


# =============================================================================
# Prompt-Aufbau
# =============================================================================

def _regime_text(regime: str | None) -> str:
    mapping = {
        "positiv": "Der Gesamtmarkt befindet sich im Aufwärtstrend.",
        "neutral": "Der Gesamtmarkt ist in einer neutralen Phase.",
        "negativ": "Der Gesamtmarkt befindet sich im Abwärtstrend.",
        "keine_daten": "Zum Marktumfeld liegen keine ausreichenden Daten vor.",
    }
    return mapping.get(regime, "Zum Marktumfeld liegen keine Daten vor.")


def build_user_prompt(score_dict: dict) -> str:
    """
    Baut den User-Prompt ausschließlich aus bereits berechneten Werten.

    Enthält: Ticker, Name, alle Signalwerte, Score, Bewertung.

    Args:
        score_dict: Score-Dict, wie es get_score_detail() liefert
                     (muss score_total != None enthalten — Hard-Filter-Fälle
                     werden vom Aufrufer abgefangen, siehe get_ai_summary).

    Returns:
        Formatierter Prompt-Text als String.
    """
    ticker = score_dict.get("ticker", "?")
    name = score_dict.get("name") or ticker
    score_total = score_dict.get("score_total")
    rating = score_dict.get("rating")

    sma200_status = (
        "positiv" if score_dict.get("score_sma200", 0) >= 10
        else "neutral" if score_dict.get("score_sma200", 0) > 0
        else "negativ"
    )

    rs_score = score_dict.get("rs_score")
    rs_text = f"{rs_score:+.1f}%" if rs_score is not None else "nicht verfügbar"

    breakout_flag = score_dict.get("breakout_flag")
    breakout_age = score_dict.get("breakout_age")
    if breakout_flag:
        breakout_text = (
            f"Ja, vor {breakout_age} Handelstag(en)" if breakout_age
            else "Ja, heute"
        )
    else:
        breakout_text = "Nein"

    regime = score_dict.get("regime")

    crv = score_dict.get("crv")
    crv_text = f"{crv:.1f}" if crv is not None else "nicht bestimmbar (Aktie nahe Hochpunkt)"

    atr_ratio = score_dict.get("atr_ratio")
    atr_text = f"{atr_ratio:.1f}%" if atr_ratio is not None else "nicht verfügbar"

    stop_loss = score_dict.get("stop_loss")
    stop_loss_text = f"{stop_loss:.2f}" if stop_loss is not None else "nicht verfügbar"

    kursziel = score_dict.get("kursziel")
    kursziel_text = f"{kursziel:.2f}" if kursziel is not None else "nicht bestimmbar"

    prompt = f"""Aktie: {name} ({ticker})

Gesamtscore: {score_total} von 100 Punkten
Bewertung: {rating}

Signal "Langfristiger Trend" (SMA200): {score_dict.get('score_sma200')} von 15 Punkten ({sma200_status})
Signal "Relative Stärke gegenüber Index": {score_dict.get('score_rs')} von 25 Punkten (Differenz zum Index über 20 Tage: {rs_text})
Signal "Breakout": {score_dict.get('score_breakout')} von 30 Punkten (Ausbruch über Widerstand vorhanden: {breakout_text})
Signal "Marktregime": {score_dict.get('score_regime')} von 15 Punkten ({_regime_text(regime)})
Signal "Risiko/Chance-Verhältnis": {score_dict.get('score_risk')} von 15 Punkten (Chance-Risiko-Verhältnis: {crv_text}, Schwankungsbreite ATR: {atr_text} des Kurses)

Vorgeschlagener Stop-Loss: {stop_loss_text}
Kursziel: {kursziel_text}

Erkläre einem Einsteiger in einfacher Sprache, was diese Werte bedeuten, welche Chancen und welche Risiken bei dieser Aktie aktuell vorliegen."""

    return prompt


# =============================================================================
# API-Aufruf
# =============================================================================

def generate_summary(score_dict: dict) -> dict:
    """
    Generiert eine KI-Zusammenfassung für eine Aktie.

    Args:
        score_dict: Score-Dict (muss score_total != None enthalten)

    Returns:
        dict mit:
          - "success": bool
          - "text": str (Zusammenfassung) oder None bei Fehler
          - "error": str | None (Fehlermeldung für UI, nur bei success=False)

    Fehlerbehandlung:
        Bei jedem Fehler (fehlender API-Key, Netzwerkfehler, API-Fehler,
        unerwartete Exception) wird success=False mit einer für den Nutzer
        verständlichen Fehlermeldung zurückgegeben. Es wird nichts in die
        Datenbank geschrieben und nichts geloggt, was die App zum Absturz
        bringen könnte.
    """
    if score_dict is None or score_dict.get("score_total") is None:
        return {
            "success": False,
            "text": None,
            "error": "Für diese Aktie liegt kein Score vor — eine "
                     "KI-Zusammenfassung ist daher nicht möglich.",
        }

    try:
        import anthropic
    except ImportError:
        logger.error("ai_summary: Paket 'anthropic' ist nicht installiert")
        return {
            "success": False,
            "text": None,
            "error": "Die KI-Komponente ist nicht verfügbar (Paket "
                     "'anthropic' fehlt).",
        }

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("ai_summary: ANTHROPIC_API_KEY ist nicht gesetzt")
        return {
            "success": False,
            "text": None,
            "error": "Die KI-Zusammenfassung ist derzeit nicht verfügbar "
                     "(kein API-Schlüssel konfiguriert).",
        }

    try:
        client = anthropic.Anthropic(api_key=api_key)
        user_prompt = build_user_prompt(score_dict)

        response = client.messages.create(
            model=AI_MODEL,
            max_tokens=AI_MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )

        text_parts = [block.text for block in response.content
                       if getattr(block, "type", None) == "text"]
        summary_text = "".join(text_parts).strip()

        if not summary_text:
            logger.warning(f"{score_dict.get('ticker')}: KI-Antwort war leer")
            return {
                "success": False,
                "text": None,
                "error": "Die KI hat keine Antwort geliefert. Bitte später "
                         "erneut versuchen.",
            }

        logger.info(f"{score_dict.get('ticker')}: KI-Zusammenfassung erfolgreich erzeugt "
                    f"({len(summary_text)} Zeichen)")

        return {"success": True, "text": summary_text, "error": None}

    except anthropic.APIConnectionError as e:
        logger.error(f"ai_summary: Verbindungsfehler: {e}")
        return {
            "success": False,
            "text": None,
            "error": "Keine Verbindung zur KI möglich. Bitte überprüfe "
                     "deine Internetverbindung und versuche es erneut.",
        }

    except anthropic.RateLimitError as e:
        logger.error(f"ai_summary: Rate-Limit erreicht: {e}")
        return {
            "success": False,
            "text": None,
            "error": "Die KI ist aktuell stark ausgelastet. Bitte versuche "
                     "es in ein paar Minuten erneut.",
        }

    except anthropic.APIStatusError as e:
        logger.error(f"ai_summary: API-Fehler (Status {e.status_code}): {e}")
        return {
            "success": False,
            "text": None,
            "error": "Die KI-Zusammenfassung konnte nicht erstellt werden "
                     "(API-Fehler). Bitte später erneut versuchen.",
        }

    except Exception as e:
        logger.error(f"ai_summary: Unerwarteter Fehler: {e}")
        return {
            "success": False,
            "text": None,
            "error": "Bei der Erstellung der KI-Zusammenfassung ist ein "
                     "unerwarteter Fehler aufgetreten.",
        }
