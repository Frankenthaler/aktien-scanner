"""
app/streamlit_app.py - Benutzeroberfläche
Aktien-Scanner V1 - Phase 4 (Frontend)

Seite 1 - Startseite:
  Marktstatus, Datenstand, Schaltfläche "Daten aktualisieren",
  Anzahl analysierter Aktien, Anzahl je Bewertungsstufe,
  Filter (Index, Bewertung), Top-20-Rangliste

Seite 2 - Detailseite:
  Ebene 1 (einfache Ansicht), Ebene 2 (technische Details, aufklappbar),
  Ebene 3 (Chart-Endkontrolle, aufklappbar)

Ebene 4 (KI-Zusammenfassung) ist nicht Teil von Phase 4.

Mobile-Anforderungen: kein horizontales Scrollen, responsive Tabellen,
Ampelfarben Grün #2ecc71 / Gelb #f39c12 / Rot #e74c3c.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd
from datetime import datetime

from utils.logging_config import setup_logging
setup_logging()

from data.database import init_db, get_latest_scores, get_score_detail, get_db_stats
from scheduler import run_full_update
from scoring.ai_summary import generate_summary
from config import RATING_THRESHOLDS

from trading.recommendation_tracker import init_swing_trading_schema, save_swing_trade_recommendation

# =============================================================================
# Konfiguration / Konstanten
# =============================================================================

COLOR_GREEN = "#2ecc71"
COLOR_YELLOW = "#f39c12"
COLOR_RED = "#e74c3c"
COLOR_GRAY = "#95a5a6"

RATING_ORDER = ["Starkes Kaufsignal", "Interessant", "Beobachten", "Kein Kauf"]

RATING_COLORS = {
    "Starkes Kaufsignal": COLOR_GREEN,
    "Interessant": COLOR_GREEN,
    "Beobachten": COLOR_YELLOW,
    "Kein Kauf": COLOR_RED,
}

# Erklärungstexte für Chart-Endkontrolle (Pflichtenheft 6.12, Ebene 3)
CHART_CHECKLIST = [
    {
        "frage": "Ist der Widerstand im Chart klar sichtbar?",
        "erklaerung": "Schau dir den Chart an: Gibt es eine Linie oder einen "
                       "Bereich, an dem der Kurs in der Vergangenheit mehrfach "
                       "nach oben abgeprallt ist? Genau dort liegt der Widerstand."
    },
    {
        "frage": "Wirkt die Ausbruchskerze überzeugend?",
        "erklaerung": "Eine überzeugende Ausbruchskerze ist eine große, grüne "
                       "Kerze, die deutlich über den Widerstand hinausgeht und "
                       "nahe ihrem Tageshoch schließt."
    },
    {
        "frage": "Ist das erhöhte Volumen im Chart sichtbar?",
        "erklaerung": "Schau auf die Volumenbalken unter dem Chart. Am Tag des "
                       "Ausbruchs sollte der Balken deutlich höher sein als an "
                       "den Tagen davor."
    },
    {
        "frage": "Ist die Aktie noch kaufbar oder bereits zu weit gelaufen?",
        "erklaerung": "Wenn der Kurs bereits stark vom Ausbruchspunkt entfernt "
                       "ist, war der ideale Einstiegszeitpunkt eventuell schon "
                       "vorbei. Ein Abstand von mehr als 3-5% kann ein Hinweis "
                       "darauf sein."
    },
    {
        "frage": "Hat die Aktie noch ausreichend Platz nach oben bis zum "
                 "nächsten Widerstand?",
        "erklaerung": "Prüfe im Chart, ob es oberhalb des aktuellen Kurses "
                       "weitere Bereiche gibt, an denen die Aktie früher schon "
                       "einmal gestoppt wurde. Wenig Platz bedeutet wenig "
                       "Potenzial nach oben."
    },
    {
        "frage": "Ist der vorgeschlagene Stop-Loss im Chart logisch platziert?",
        "erklaerung": "Der Stop-Loss sollte unterhalb einer Unterstützung oder "
                       "eines vorherigen Tiefpunkts liegen - nicht mitten in "
                       "einem Bereich, in dem der Kurs häufig hin und her "
                       "pendelt."
    },
]


# =============================================================================
# Hilfsfunktionen
# =============================================================================

def format_datetime(value) -> str:
    """Formatiert einen Zeitstempel für die Anzeige."""
    if value is None:
        return "-"
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", ""))
        except ValueError:
            return value
    return value.strftime("%d.%m.%Y %H:%M")


def ampel_html(color: str, text: str = "") -> str:
    """Erzeugt ein farbiges Ampel-Symbol als HTML."""
    dot = (
        f'<span style="display:inline-block;width:12px;height:12px;'
        f'border-radius:50%;background-color:{color};margin-right:6px;'
        f'vertical-align:middle;"></span>'
    )
    return f'{dot}<span style="vertical-align:middle;">{text}</span>'


def regime_color(regime: str) -> str:
    if regime == "positiv":
        return COLOR_GREEN
    if regime == "neutral":
        return COLOR_YELLOW
    if regime == "negativ":
        return COLOR_RED
    return COLOR_GRAY


def regime_label(regime: str) -> str:
    mapping = {
        "positiv": "Positiv",
        "neutral": "Neutral",
        "negativ": "Negativ",
        "keine_daten": "Keine Daten",
    }
    return mapping.get(regime, "Unbekannt")


def trend_ampel(row) -> str:
    """
    Trend-Ampel für die Rangliste: kombiniert SMA200- und Breakout-Signal
    zu einer einfachen Gesamteinschätzung.
    """
    score_total = row.get("score_total")
    if score_total is None:
        return "⚪"
    if score_total >= 70:
        return "🟢"
    if score_total >= 55:
        return "🟡"
    return "🔴"


def get_latest_update_timestamp() -> str | None:
    """Ermittelt den Zeitpunkt der letzten Aktualisierung (jüngster Score-Eintrag)."""
    df = get_latest_scores()
    if df.empty or "created_at" not in df.columns:
        return None
    try:
        return df["created_at"].max()
    except Exception:
        return None


def signal_status_symbol(score: int | None, max_punkte: int) -> str:
    """
    Wandelt einen Signal-Score in ein einfaches ✓ / ~ / ✗-Symbol um.
    >= 2/3 des Maximalwerts -> ✓, > 0 -> ~, == 0 -> ✗
    """
    if score is None:
        return "?"
    if score >= max_punkte * (2 / 3):
        return "✓"
    if score > 0:
        return "~"
    return "✗"


# =============================================================================
# Seiteneinrichtung
# =============================================================================

st.set_page_config(
    page_title="Aktien-Scanner",
    page_icon="📊",
    layout="centered",  # zentriert, schmal -> mobile-freundlich
    initial_sidebar_state="collapsed",
)

# Globales CSS: kein horizontales Scrollen, kompakte Darstellung
st.markdown("""
<style>
    .block-container {
        padding-left: 1rem;
        padding-right: 1rem;
        max-width: 100%;
    }
    /* Tabellen nie breiter als der Bildschirm */
    [data-testid="stDataFrame"], [data-testid="stTable"] {
        width: 100% !important;
        overflow-x: auto;
    }
    /* Lange Ticker/Namen umbrechen statt abschneiden+scrollen */
    .stMarkdown p {
        word-break: break-word;
    }
</style>
""", unsafe_allow_html=True)

init_db()


# =============================================================================
# Session State / Navigation
# =============================================================================

if "page" not in st.session_state:
    st.session_state.page = "start"
if "selected_ticker" not in st.session_state:
    st.session_state.selected_ticker = None


def go_to_detail(ticker: str):
    st.session_state.page = "detail"
    st.session_state.selected_ticker = ticker


def go_to_start():
    st.session_state.page = "start"
    st.session_state.selected_ticker = None


# =============================================================================
# Seite 1 - Startseite
# =============================================================================

def render_startseite():
    st.title("📊 Aktien-Scanner")
    st.caption("Swing-Trading-Kandidaten aus DAX, S&P 500 und Nasdaq 100")

    # -------------------------------------------------------------------
    # Marktstatus
    # -------------------------------------------------------------------
    st.subheader("Marktstatus")

    scores_df = get_latest_scores()

    if scores_df.empty:
        st.info(
            "Noch keine Daten vorhanden. Bitte zuerst auf "
            "**"Daten aktualisieren“** tippen, um die erste Analyse zu starten."
        )
        col_dax, col_sp500 = None, None
        regime_dax, regime_sp500 = "keine_daten", "keine_daten"
    else:
        # Regime aus den Scores ableiten: DAX-Aktien -> DAX-Regime,
        # SP500/NDX100-Aktien -> SP500-Regime (Deduplizierungsregel: NDX100 -> SP500)
        dax_rows = scores_df[scores_df["ticker"].notna()]
        regime_dax = "keine_daten"
        regime_sp500 = "keine_daten"

        for _, row in scores_df.iterrows():
            regime = row.get("regime")
            if regime is None:
                continue
            # Heuristik: deutsche Ticker enden auf .DE -> DAX-Regime
            if str(row["ticker"]).endswith(".DE"):
                if regime_dax == "keine_daten":
                    regime_dax = regime
            else:
                if regime_sp500 == "keine_daten":
                    regime_sp500 = regime

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**DAX**")
        st.markdown(
            ampel_html(regime_color(regime_dax), regime_label(regime_dax)),
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown("**S&P 500**")
        st.markdown(
            ampel_html(regime_color(regime_sp500), regime_label(regime_sp500)),
            unsafe_allow_html=True,
        )

    if regime_dax == "negativ" or regime_sp500 == "negativ":
        st.warning(
            "⚠️ Der Markt befindet sich in einem ungünstigen Umfeld. "
            "Kaufsignale werden automatisch vorsichtiger bewertet "
            "(maximale Bewertung: "Beobachten“)."
        )
    elif regime_dax == "neutral" or regime_sp500 == "neutral":
        st.info(
            "Der Markt ist aktuell in einer neutralen Phase. "
            "Kaufsignale werden vorsichtiger bewertet."
        )

    # -------------------------------------------------------------------
    # Datenstand
    # -------------------------------------------------------------------
    st.divider()

    last_update = get_latest_update_timestamp()
    st.caption(f"🕐 Letzte Aktualisierung: {format_datetime(last_update)}")

    # -------------------------------------------------------------------
    # Schaltfläche "Daten aktualisieren"
    # -------------------------------------------------------------------
    if st.button("🔄 Daten aktualisieren", use_container_width=True, type="primary"):
        with st.spinner(
            "Daten werden aktualisiert ... Das kann je nach Anzahl der Aktien "
            "einige Minuten dauern."
        ):
            try:
                result = run_full_update()

                # --- Indexlisten-Status (Phase-6-Nachtrag) ---
                index_sync = result.get("index_sync", {})
                index_status = index_sync.get("status")

                if index_status == "error":
                    st.error(
                        "⚠️ Indexliste konnte nicht vollständig geladen "
                        "werden. Es konnten keine aktuellen Ticker für "
                        "DAX 40, S&P 500 oder Nasdaq 100 abgerufen werden. "
                        "Die bestehende Aktienliste wurde NICHT verändert."
                    )
                elif index_status == "partial":
                    fehlende = ", ".join(index_sync.get("failed_indices", []))
                    st.warning(
                        f"⚠️ Indexliste konnte nicht vollständig geladen "
                        f"werden. Folgende Indizes fehlen: {fehlende}. "
                        f"Die übrigen Indizes wurden aktualisiert."
                    )
                elif index_sync.get("fallback_used"):
                    fallback = ", ".join(index_sync["fallback_used"])
                    st.info(
                        f"ℹ️ Für {fallback} wurde eine interne "
                        f"Reserveliste verwendet, da die aktuelle Liste "
                        f"nicht abgerufen werden konnte."
                    )

                erfolg_eu = result["europe"]["erfolgreich"]
                total_eu = result["europe"]["total"]
                erfolg_us = result["usa_and_scores"]["daten"]["erfolgreich"]
                total_us = result["usa_and_scores"]["daten"]["total"]
                erfolg_scores = result["usa_and_scores"]["scores"]["erfolgreich"]
                total_scores = result["usa_and_scores"]["scores"]["total"]

                st.success(
                    f"Aktualisierung abgeschlossen.\n\n"
                    f"- Europa-Daten: {erfolg_eu}/{total_eu} Aktien\n"
                    f"- USA-Daten: {erfolg_us}/{total_us} Aktien\n"
                    f"- Scores berechnet: {erfolg_scores}/{total_scores} Aktien"
                )
            except Exception as e:
                st.error(
                    f"Bei der Aktualisierung ist ein Fehler aufgetreten: {e}\n\n"
                    f"Details siehe Logdatei."
                )

    st.divider()

    # -------------------------------------------------------------------
    # Übersicht: Anzahl analysierter Aktien + je Bewertungsstufe
    # -------------------------------------------------------------------
    if scores_df.empty:
        return

    st.subheader("Übersicht")
    st.markdown(f"**{len(scores_df)}** Aktien wurden heute analysiert.")

    # Anzahl je Bewertungsstufe
    rating_counts = scores_df["rating"].value_counts()

    cols = st.columns(len(RATING_ORDER))
    for i, rating in enumerate(RATING_ORDER):
        count = int(rating_counts.get(rating, 0))
        with cols[i]:
            color = RATING_COLORS[rating]
            st.markdown(
                f'<div style="text-align:center;">'
                f'<div style="font-size:1.6rem;font-weight:bold;color:{color};">'
                f'{count}</div>'
                f'<div style="font-size:0.75rem;color:#666;">{rating}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.divider()

    # -------------------------------------------------------------------
    # Filter
    # -------------------------------------------------------------------
    st.subheader("Rangliste - Top 20")

    col_f1, col_f2 = st.columns(2)

    with col_f1:
        # Index-Filter: aus Ticker-Endung ableiten (.DE -> DAX, sonst SP500/NDX100)
        index_options = ["Alle"]
        has_de = scores_df["ticker"].astype(str).str.endswith(".DE").any()
        has_us = (~scores_df["ticker"].astype(str).str.endswith(".DE")).any()
        if has_de:
            index_options.append("DAX")
        if has_us:
            index_options.append("USA (S&P 500 / Nasdaq 100)")

        index_filter = st.selectbox("Index", index_options)

    with col_f2:
        rating_options = ["Alle"] + RATING_ORDER
        rating_filter = st.selectbox("Bewertung", rating_options)

    # Filter anwenden
    filtered = scores_df.copy()

    if index_filter == "DAX":
        filtered = filtered[filtered["ticker"].astype(str).str.endswith(".DE")]
    elif index_filter == "USA (S&P 500 / Nasdaq 100)":
        filtered = filtered[~filtered["ticker"].astype(str).str.endswith(".DE")]

    if rating_filter != "Alle":
        filtered = filtered[filtered["rating"] == rating_filter]

    # -------------------------------------------------------------------
    # Top-20-Rangliste
    # -------------------------------------------------------------------
    if filtered.empty:
        st.info("Keine Aktien entsprechen den gewählten Filtern.")
        return

    top20 = filtered.sort_values("score_total", ascending=False).head(20)

    # Header-Zeile
    header_cols = st.columns([3, 2, 2, 1])
    header_cols[0].markdown("**Aktie**")
    header_cols[1].markdown("**Score**")
    header_cols[2].markdown("**Bewertung**")
    header_cols[3].markdown("**Trend**")

    for _, row in top20.iterrows():
        cols = st.columns([3, 2, 2, 1])

        name = row.get("name") or row["ticker"]
        display_name = name if len(str(name)) <= 18 else str(name)[:16] + "..."

        with cols[0]:
            if st.button(
                f"{display_name}\n{row['ticker']}",
                key=f"btn_{row['ticker']}",
                use_container_width=True,
            ):
                go_to_detail(row["ticker"])
                st.rerun()

        with cols[1]:
            st.markdown(
                f'<div style="padding-top:0.6rem;font-weight:bold;">'
                f'{int(row["score_total"])}</div>',
                unsafe_allow_html=True,
            )

        with cols[2]:
            color = RATING_COLORS.get(row["rating"], COLOR_GRAY)
            st.markdown(
                f'<div style="padding-top:0.6rem;">'
                f'{ampel_html(color, row["rating"])}</div>',
                unsafe_allow_html=True,
            )

        with cols[3]:
            st.markdown(
                f'<div style="padding-top:0.6rem;font-size:1.3rem;">'
                f'{trend_ampel(row)}</div>',
                unsafe_allow_html=True,
            )


# =============================================================================
# Seite 2 - Detailseite
# =============================================================================

def render_detailseite():
    """Neue Detailansicht mit Swing-Trade-Fokus"""
    ticker = st.session_state.selected_ticker

    if st.button("← Zurück zur Übersicht"):
        go_to_start()
        st.rerun()

    detail = get_score_detail(ticker)

    if detail is None:
        st.error(f"Keine Daten für {ticker} gefunden.")
        return

    name = detail.get("name") or ticker

    # Hard-Filter-Fall
    if detail.get("score_total") is None:
        st.title(name)
        st.caption(ticker)
        st.warning(
            "Diese Aktie wird derzeit nicht bewertet, da sie sich nicht im "
            "kurzfristigen Aufwärtstrend befindet (Kurs liegt unter dem "
            "50-Tage-Durchschnitt)."
        )
        return

    score_total = int(detail["score_total"])
    rating = detail["rating"]
    breakout_age = detail.get("breakout_age")
    crv = detail.get("crv")
    atr_ratio = detail.get("atr_ratio")
    
    # ========================================================================
    # EBENE 1 - SWING-TRADE HEADER
    # ========================================================================
    
    st.title(f"{name} ({ticker})")
    
    # Handlungssignal
    color = RATING_COLORS.get(rating, COLOR_GRAY)
    signal_emoji = {"Starkes Kaufsignal": "🟢", "Interessant": "🟢", "Beobachten": "🟡", "Kein Kauf": "🔴"}
    emoji = signal_emoji.get(rating, "⚪")
    
    st.markdown(
        f'<div style="background-color:{color};color:white;padding:1rem;border-radius:8px;margin:1rem 0;text-align:center;">'
        f'<div style="font-size:2rem;font-weight:bold;">{emoji} {rating}</div>'
        f'<div style="font-size:1.2rem;">Score: {score_total} / 100</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    
    # Kernkennzahlen
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        price = detail.get("price_close")
        st.metric("Aktueller Kurs", f"{price:.2f} €" if price else "-")
    with col2:
        stop_buy = detail.get("stop_buy")
        st.metric("Stop-Buy", f"{stop_buy:.2f} €" if stop_buy else "-")
    with col3:
        stop_loss = detail.get("stop_loss")
        st.metric("Stop-Loss", f"{stop_loss:.2f} €" if stop_loss else "-")
    with col4:
        if price and stop_loss:
            risk_pct = abs((price - stop_loss) / price * 100)
            st.metric("Risiko", f"{risk_pct:.1f}%")
        else:
            st.metric("Risiko", "-")
    
    # Kursziele & CRV
    col1, col2, col3 = st.columns(3)
    with col1:
        kursziel = detail.get("kursziel")
        if kursziel:
            st.metric("Kursziel 1", f"{kursziel:.2f} €")
        else:
            st.info("📍 Kursziel: Aktie zu nah am Hochpunkt. Einstieg nur über Stop-Buy.")
    with col2:
        st.metric("Kursziel 2", "-")
    with col3:
        if crv:
            st.metric("Chance/Risiko", f"{crv:.2f}")
        else:
            st.info("📊 CRV: Nicht bestimmbar.")
    
    # Metadaten
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Signalalter", f"{breakout_age} Tage" if breakout_age else "-")
    with col2:
        setup_type = "Breakout" if detail.get("breakout_flag") else "Beobachtung"
        st.metric("Setup-Typ", setup_type)
    
    st.divider()
    
    # Score-Aufschlüsselung
    st.subheader("📊 Score-Aufschlüsselung")
    
    sma200_score = detail.get("score_sma200", 0)
    st.markdown(f"**SMA200:** {sma200_score} / 15 Punkte")
    if sma200_score == 15:
        st.success("✓ Deutlich über 200er-Durchschnitt")
    elif sma200_score > 0:
        st.info("~ Über 200er-Durchschnitt")
    else:
        st.error("✗ Unter 200er-Durchschnitt")
    st.divider()
    
    rs_score = detail.get("score_rs", 0)
    st.markdown(f"**Relative Stärke:** {rs_score} / 25 Punkte")
    if rs_score >= 20:
        st.success("✓ Deutlich stärker als Markt")
    elif rs_score > 0:
        st.info("~ Stärker als Markt")
    else:
        st.error("✗ Schwächer als Markt")
    st.divider()
    
    breakout_score = detail.get("score_breakout", 0)
    st.markdown(f"**Breakout:** {breakout_score} / 30 Punkte")
    if detail.get("breakout_flag"):
        st.success(f"✓ Widerstand durchbrochen vor {breakout_age if breakout_age else 0} Tagen")
    elif breakout_score > 0:
        st.info("~ Erste Ausbruchsanzeichen")
    else:
        st.error("✗ Kein Breakout")
    st.divider()
    
    regime = detail.get("regime")
    regime_score = detail.get("score_regime", 0)
    st.markdown(f"**Marktregime:** {regime_score} / 15 Punkte")
    if regime == "positiv":
        st.success("✓ Markt im Aufwärtstrend")
    elif regime == "neutral":
        st.info("~ Markt neutral")
    else:
        st.error("✗ Markt im Abwärtstrend")
    st.divider()
    
    risk_score = detail.get("score_risk", 0)
    st.markdown(f"**Risiko / CRV:** {risk_score} / 15 Punkte")
    if crv and crv > 1.5:
        st.success("✓ Hervorragendes CRV")
    elif crv and crv > 1:
        st.success("✓ Gutes CRV")
    elif crv:
        st.warning("⚠ Schwaches CRV")
    else:
        st.info("~ CRV nicht bestimmbar")
    
    st.divider()
    
    # ========================================================================
    # EBENE 2 - TECHNISCHE DETAILS (aufklappbar)
    # ========================================================================
    
    with st.expander("📋 Technische Details"):
        col1, col2 = st.columns(2)
        with col1:
            st.write(f"**Datum:** {detail.get('date', '-')}")
            st.write(f"**SMA50:** {detail.get('sma50', '-')}")
        with col2:
            st.write(f"**Signal-Version:** {detail.get('signal_version', '-')}")
            if atr_ratio:
                st.write(f"**ATR-Ratio:** {atr_ratio:.2f}%")
    
    # ========================================================================
    # EBENE 3 - CHART-ENDKONTROLLE (aufklappbar)
    # ========================================================================
    
    with st.expander("✅ Chart-Endkontrolle"):
        st.markdown("Bevor du kaufst, überprüfe diese Punkte im Chart:")
        for i, item in enumerate(CHART_CHECKLIST, start=1):
            st.markdown(f"**{i}. {item['frage']}**")


# =============================================================================
# HAUPTNAVIGATION
# =============================================================================

if st.session_state.page == "start":
    render_startseite()
elif st.session_state.page == "detail":
    render_detailseite()
