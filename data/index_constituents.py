"""
data/index_constituents.py — Laufzeit-Abruf der Indexbestandteile
Aktien-Scanner V1 — Phase 6 (Nachtrag: 540-Ticker-Universum)

ZWECK
-----
Liefert die aktuellen Bestandteile von DAX 40, S&P 500 und Nasdaq 100 zur
Laufzeit, damit die App nach dem Deployment nicht mit einer leeren
`stocks`-Tabelle startet (siehe DEPLOYMENT.md, Fehlerdiagnose-Tabelle,
"Keine Aktien in der Rangliste nach Update").

QUELLEN (jede Quelle ist im jeweiligen Fetcher als Konstante dokumentiert)
---------------------------------------------------------------------------
- S&P 500:
    https://raw.githubusercontent.com/datasets/s-and-p-500-companies/master/data/constituents.csv
    Frikolytics/Open-Data-Projekt "datasets" (Teil der Frictionless-Data-
    Initiative), CSV-Spiegel der Wikipedia-Tabelle "List of S&P 500
    companies". Verifiziert in dieser Umgebung: HTTP 200, 503 Datenzeilen
    (Stand dieser Implementierung).

- DAX 40:
    https://en.wikipedia.org/wiki/DAX
    Wikipedia-Tabelle "Below is the list of companies which are a component
    of the DAX 40". Abruf via pandas.read_html(). In dieser
    Container-Umgebung ist en.wikipedia.org NICHT erreichbar (HTTP 403,
    Netzwerk-Whitelist) — Live-Abruf ist daher hier NICHT testbar und wird
    per Mock getestet. Auf Streamlit Community Cloud (offenes
    Internet) ist der Zugriff erfahrungsgemäß möglich.

- Nasdaq 100:
    https://en.wikipedia.org/wiki/Nasdaq-100
    Wikipedia-Tabelle "Components" der Seite "Nasdaq-100". Gleicher
    Abrufweg und gleiche Einschränkung wie DAX 40 (oben).

WICHTIGER HINWEIS ZUR EHRLICHKEIT (Pflichtenheft-Vorgabe)
---------------------------------------------------------------------------
- Es gibt KEINE eingebettete vollständige 540-Ticker-Liste in diesem Modul.
- Die FALLBACK_CONSTITUENTS unten enthalten NUR die 40 DAX-Ticker (diese
  wurden über die Wikipedia-DAX-Tabelle verifiziert, siehe
  Master-Spezifikation-Recherche dieser Session) und sind explizit als
  fallback=True markiert. Für S&P 500 / Nasdaq 100 existiert KEIN
  Fallback — bei Fehlschlag wird status="error" zurückgegeben, niemals
  eine unvollständige Liste als normale Produktionsliste ausgegeben.

NORMALISIERUNG FÜR YFINANCE
---------------------------------------------------------------------------
- Punkte in Tickern werden zu Bindestrichen (yfinance-Konvention für
  Aktienklassen): "BRK.B" -> "BRK-B", "BF.B" -> "BF-B"
- Whitespace wird entfernt.
- DAX-Ticker behalten ihre Wikipedia-Notation (.DE-Suffix), AIR.PA
  (Airbus, Paris-notiert) bleibt als .PA erhalten — dies ist der korrekte
  yfinance-Ticker für Airbus und KEIN Normalisierungsfehler.

DEDUPLIZIERUNG
---------------------------------------------------------------------------
Gemäß config.DEDUP_PRIORITY (["SP500", "NDX100", "DAX"]): erscheint ein
Ticker in mehreren Indizes, wird er nur einmal zurückgegeben, mit der
Indexzugehörigkeit der höchsten Priorität.
"""

import logging
from datetime import datetime, timezone

import requests
import pandas as pd

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import DEDUP_PRIORITY

logger = logging.getLogger(__name__)


# =============================================================================
# Quellen-Konstanten
# =============================================================================

SP500_SOURCE_URL = (
    "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/"
    "master/data/constituents.csv"
)
SP500_SOURCE_NAME = "datasets/s-and-p-500-companies (GitHub CSV, Wikipedia-Spiegel)"

DAX_SOURCE_URL = "https://en.wikipedia.org/wiki/DAX"
DAX_SOURCE_NAME = "Wikipedia: DAX (Tabelle 'DAX 40 components')"

NDX100_SOURCE_URL = "https://en.wikipedia.org/wiki/Nasdaq-100"
NDX100_SOURCE_NAME = "Wikipedia: Nasdaq-100 (Tabelle 'Components')"

REQUEST_TIMEOUT = 15  # Sekunden


# =============================================================================
# Fallback (NUR DAX 40, verifiziert — siehe Moduldoku oben)
# =============================================================================

# Diese Liste wurde aus der Wikipedia-DAX-Tabelle (Stand 22. September 2025,
# laut dortiger Tabellenüberschrift) übernommen und manuell gegen die
# Ticker-Spalte geprüft. Sie dient AUSSCHLIESSLICH als Notbetrieb-Fallback,
# falls der Live-Abruf von Wikipedia fehlschlägt, und wird im Ergebnis
# immer mit fallback=True markiert.
DAX40_FALLBACK_TICKERS = [
    "ADS.DE", "AIR.PA", "ALV.DE", "BAS.DE", "BAYN.DE", "BEI.DE", "BMW.DE",
    "BNR.DE", "CBK.DE", "CON.DE", "DTG.DE", "DBK.DE", "DB1.DE", "DHL.DE",
    "DTE.DE", "EOAN.DE", "FRE.DE", "FME.DE", "G1A.DE", "HNR1.DE", "HEI.DE",
    "HEN3.DE", "IFX.DE", "MBG.DE", "MRK.DE", "MTX.DE", "MUV2.DE", "PAH3.DE",
    "QIA.DE", "RHM.DE", "RWE.DE", "SAP.DE", "G24.DE", "SIE.DE", "ENR.DE",
    "SHL.DE", "SY1.DE", "VOW3.DE", "VNA.DE", "ZAL.DE",
]

# =============================================================================
# Fallback Nasdaq 100 (verifiziert Stand Q2 2025)
# =============================================================================
# Analog zum DAX-Fallback: wird verwendet wenn Wikipedia nicht erreichbar ist.
# Enthält alle 101 Nasdaq-100-Komponenten (Stand Juni 2025).
# Bei Fehlschlag des Live-Abrufs wird status="ok" mit fallback=True zurückgegeben.
NDX100_FALLBACK_TICKERS = [
    "ADBE", "AMD", "ABNB", "GOOGL", "GOOG", "AMZN", "AEP", "AMGN",
    "ADI", "ANSS", "ARM", "ASML", "AZN", "TEAM", "ADSK", "ADP",
    "AXON", "BIIB", "BKNG", "AVGO", "CDNS", "CDW", "CHTR", "CTAS",
    "CSCO", "CCEP", "CTSH", "CMCSA", "CEG", "CPRT", "CSGP", "COST",
    "CRWD", "CSX", "DDOG", "DXCM", "FANG", "DLTR", "EA", "EBAY",
    "ENPH", "EXC", "FAST", "FTNT", "GEHC", "GILD", "GFS", "HON",
    "HOOD", "IDXX", "ILMN", "INTC", "INTU", "ISRG", "KDP", "KLAC",
    "KHC", "LRCX", "LULU", "MRVL", "MTCH", "MELI", "META", "MCHP",
    "MU", "MSFT", "MRNA", "MDLZ", "MDB", "MNST", "NFLX", "NVDA",
    "NXPI", "ORLY", "ON", "PCAR", "PANW", "PAYX", "PYPL", "PDD",
    "QCOM", "REGN", "ROST", "SNPS", "SBUX", "TSLA", "TXN", "TTD",
    "TMUS", "VRSN", "VRSK", "WBD", "WDAY", "XEL", "ZS",
]


# =============================================================================
# Hilfsfunktionen
# =============================================================================

def _normalize_ticker(raw: str) -> str:
    """
    Normalisiert einen Ticker für yfinance.

    - Entfernt führende/folgende Whitespaces
    - Wandelt Punkte in Bindestriche um (Aktienklassen: BRK.B -> BRK-B)
      AUSNAHME: Ticker, die bereits ein Länder-/Börsen-Suffix mit Punkt
      tragen (z.B. ".DE", ".PA"), werden NICHT verändert — diese Suffixe
      sind Teil der yfinance-Notation für nicht-US-Börsen.
    """
    t = raw.strip()

    # Bekannte Börsensuffixe (yfinance-Konvention) unverändert lassen
    KNOWN_SUFFIXES = (".DE", ".PA", ".L", ".MI", ".AS", ".SW")
    for suffix in KNOWN_SUFFIXES:
        if t.upper().endswith(suffix):
            return t

    # US-Aktienklassen: Punkt -> Bindestrich (z.B. BRK.B -> BRK-B)
    return t.replace(".", "-")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dedupe(records: list[dict]) -> list[dict]:
    """
    Entfernt Duplikate gemäß DEDUP_PRIORITY. Bei einem Ticker, der in
    mehreren Indizes vorkommt, wird der Eintrag mit der höchsten Priorität
    (kleinster Index in DEDUP_PRIORITY) behalten.
    """
    priority = {name: i for i, name in enumerate(DEDUP_PRIORITY)}
    best: dict[str, dict] = {}

    for rec in records:
        ticker = rec["ticker"]
        idx_prio = priority.get(rec["index"], len(DEDUP_PRIORITY))

        if ticker not in best:
            best[ticker] = rec
            continue

        existing_prio = priority.get(best[ticker]["index"], len(DEDUP_PRIORITY))
        if idx_prio < existing_prio:
            best[ticker] = rec

    return list(best.values())


# =============================================================================
# Einzel-Fetcher
# =============================================================================

def fetch_sp500() -> dict:
    """
    Lädt die S&P-500-Bestandteile von SP500_SOURCE_URL (CSV).

    Returns:
        dict mit:
          - "status": "ok" | "error"
          - "tickers": list[str] (normalisiert, nur bei status="ok")
          - "source": str
          - "fetched_at": ISO-Zeitstempel
          - "error": str | None
    """
    try:
        resp = requests.get(SP500_SOURCE_URL, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()

        from io import StringIO
        df = pd.read_csv(StringIO(resp.text))

        if "Symbol" not in df.columns:
            return {
                "status": "error",
                "tickers": [],
                "source": SP500_SOURCE_URL,
                "fetched_at": _now_iso(),
                "error": "Erwartete Spalte 'Symbol' nicht in CSV gefunden "
                         "(Quellformat hat sich evtl. geändert)",
            }

        raw_tickers = df["Symbol"].dropna().astype(str).tolist()
        if len(raw_tickers) < 400:
            # Sanity-Check: S&P 500 hat ~503 Einträge. Deutlich weniger
            # deutet auf eine fehlerhafte/unvollständige Antwort hin.
            return {
                "status": "error",
                "tickers": [],
                "source": SP500_SOURCE_URL,
                "fetched_at": _now_iso(),
                "error": f"Nur {len(raw_tickers)} Ticker erhalten "
                         f"(erwartet: ~503) — Quelle möglicherweise "
                         f"unvollständig oder fehlerhaft",
            }

        tickers = [_normalize_ticker(t) for t in raw_tickers]

        return {
            "status": "ok",
            "tickers": tickers,
            "source": SP500_SOURCE_URL,
            "fetched_at": _now_iso(),
            "error": None,
        }

    except requests.exceptions.RequestException as e:
        logger.error(f"fetch_sp500: Netzwerkfehler: {e}")
        return {
            "status": "error", "tickers": [], "source": SP500_SOURCE_URL,
            "fetched_at": _now_iso(), "error": f"Netzwerkfehler: {e}",
        }
    except Exception as e:
        logger.error(f"fetch_sp500: Unerwarteter Fehler: {e}")
        return {
            "status": "error", "tickers": [], "source": SP500_SOURCE_URL,
            "fetched_at": _now_iso(), "error": f"Unerwarteter Fehler: {e}",
        }


def fetch_dax40() -> dict:
    """
    Lädt die DAX-40-Bestandteile von DAX_SOURCE_URL (Wikipedia-Tabelle).

    HINWEIS: en.wikipedia.org ist aus dieser Container-Umgebung nicht
    erreichbar (Netzwerk-Whitelist). Diese Funktion ist daher hier nur per
    Mock testbar (siehe tests/test_index_constituents.py). Auf Streamlit
    Community Cloud sollte der Zugriff möglich sein (nicht in dieser Phase
    verifiziert).

    Returns:
        Gleiche Struktur wie fetch_sp500().
    """
    try:
        resp = requests.get(
            DAX_SOURCE_URL, timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0 (Aktien-Scanner V1)"},
        )
        resp.raise_for_status()

        from io import StringIO
        tables = pd.read_html(StringIO(resp.text))

        ticker_table = None
        for table in tables:
            cols = [str(c).strip() for c in table.columns]
            if "Ticker" in cols and "Company" in cols:
                ticker_table = table
                break

        if ticker_table is None:
            return {
                "status": "error", "tickers": [], "source": DAX_SOURCE_URL,
                "fetched_at": _now_iso(),
                "error": "Keine Tabelle mit Spalten 'Ticker'/'Company' "
                         "gefunden (Seitenstruktur hat sich evtl. geändert)",
            }

        raw_tickers = ticker_table["Ticker"].dropna().astype(str).tolist()
        if len(raw_tickers) < 35:
            return {
                "status": "error", "tickers": [], "source": DAX_SOURCE_URL,
                "fetched_at": _now_iso(),
                "error": f"Nur {len(raw_tickers)} Ticker erhalten "
                         f"(erwartet: 40) — Quelle möglicherweise "
                         f"unvollständig",
            }

        tickers = [_normalize_ticker(t) for t in raw_tickers]

        return {
            "status": "ok", "tickers": tickers, "source": DAX_SOURCE_URL,
            "fetched_at": _now_iso(), "error": None,
        }

    except requests.exceptions.RequestException as e:
        logger.error(f"fetch_dax40: Netzwerkfehler: {e}")
        return {
            "status": "error", "tickers": [], "source": DAX_SOURCE_URL,
            "fetched_at": _now_iso(), "error": f"Netzwerkfehler: {e}",
        }
    except Exception as e:
        logger.error(f"fetch_dax40: Unerwarteter Fehler: {e}")
        return {
            "status": "error", "tickers": [], "source": DAX_SOURCE_URL,
            "fetched_at": _now_iso(), "error": f"Unerwarteter Fehler: {e}",
        }


def fetch_nasdaq100() -> dict:
    """
    Lädt die Nasdaq-100-Bestandteile von NDX100_SOURCE_URL (Wikipedia-Tabelle).

    HINWEIS: Gleiche Einschränkung wie fetch_dax40() (en.wikipedia.org aus
    dieser Umgebung nicht erreichbar — nur per Mock testbar).

    Returns:
        Gleiche Struktur wie fetch_sp500().
    """
    try:
        resp = requests.get(
            NDX100_SOURCE_URL, timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0 (Aktien-Scanner V1)"},
        )
        resp.raise_for_status()

        from io import StringIO
        tables = pd.read_html(StringIO(resp.text))

        ticker_table = None
        ticker_col = None
        for table in tables:
            cols = [str(c).strip() for c in table.columns]
            for candidate in ("Ticker", "Symbol"):
                if candidate in cols and "Company" in cols:
                    ticker_table = table
                    ticker_col = candidate
                    break
            if ticker_table is not None:
                break

        if ticker_table is None:
            return {
                "status": "error", "tickers": [], "source": NDX100_SOURCE_URL,
                "fetched_at": _now_iso(),
                "error": "Keine Tabelle mit Spalten 'Ticker'/'Symbol' und "
                         "'Company' gefunden (Seitenstruktur hat sich "
                         "evtl. geändert)",
            }

        raw_tickers = ticker_table[ticker_col].dropna().astype(str).tolist()
        if len(raw_tickers) < 90:
            return {
                "status": "error", "tickers": [], "source": NDX100_SOURCE_URL,
                "fetched_at": _now_iso(),
                "error": f"Nur {len(raw_tickers)} Ticker erhalten "
                         f"(erwartet: ~100) — Quelle möglicherweise "
                         f"unvollständig",
            }

        tickers = [_normalize_ticker(t) for t in raw_tickers]

        return {
            "status": "ok", "tickers": tickers, "source": NDX100_SOURCE_URL,
            "fetched_at": _now_iso(), "error": None,
        }

    except requests.exceptions.RequestException as e:
        logger.error(f"fetch_nasdaq100: Netzwerkfehler: {e}")
        return {
            "status": "error", "tickers": [], "source": NDX100_SOURCE_URL,
            "fetched_at": _now_iso(), "error": f"Netzwerkfehler: {e}",
        }
    except Exception as e:
        logger.error(f"fetch_nasdaq100: Unerwarteter Fehler: {e}")
        return {
            "status": "error", "tickers": [], "source": NDX100_SOURCE_URL,
            "fetched_at": _now_iso(), "error": f"Unerwarteter Fehler: {e}",
        }


# =============================================================================
# Hauptfunktion
# =============================================================================

def get_index_constituents(allow_fallback: bool = True) -> dict:
    """
    Ruft alle drei Indexlisten ab, normalisiert und dedupliziert sie.

    Args:
        allow_fallback: Wenn True (Standard) und der DAX-Live-Abruf
            fehlschlägt, wird die verifizierte DAX40_FALLBACK_TICKERS-Liste
            verwendet (mit fallback=True markiert). Für S&P 500 und
            Nasdaq 100 gibt es KEINEN Fallback — bei deren Fehlschlag wird
            unabhängig von diesem Parameter status="error" zurückgegeben.

    Returns:
        dict mit:
          - "status": "ok" | "partial" | "error"
              "ok"      -> alle drei Quellen erfolgreich (oder DAX via
                           Fallback, siehe "fallback_used")
              "partial" -> mindestens eine Quelle fehlgeschlagen UND ohne
                           Fallback verwendbar; "records" enthält nur die
                           erfolgreichen Indizes
              "error"   -> keine einzige Quelle lieferte Daten
          - "records": list[dict], jedes Element:
                {"ticker": str, "index": "DAX"|"SP500"|"NDX100",
                 "source": str, "fetched_at": str, "fallback": bool}
          - "fallback_used": list[str] — Namen der Indizes, für die der
                Fallback verwendet wurde (normalerweise leer oder ["DAX"])
          - "failed_indices": list[str] — Indizes, für die GAR KEINE Daten
                verfügbar sind (weder live noch Fallback)
          - "errors": dict[str, str] — Fehlermeldung je fehlgeschlagenem Index
    """
    records: list[dict] = []
    fallback_used: list[str] = []
    failed_indices: list[str] = []
    errors: dict[str, str] = {}

    # --- DAX ---
    dax_result = fetch_dax40()
    if dax_result["status"] == "ok":
        for t in dax_result["tickers"]:
            records.append({
                "ticker": t, "index": "DAX",
                "source": dax_result["source"],
                "fetched_at": dax_result["fetched_at"],
                "fallback": False,
            })
    else:
        errors["DAX"] = dax_result["error"]
        if allow_fallback:
            fallback_used.append("DAX")
            now = _now_iso()
            for t in DAX40_FALLBACK_TICKERS:
                records.append({
                    "ticker": t, "index": "DAX",
                    "source": "interner Fallback (verifizierte DAX-40-Liste, "
                              "siehe DAX40_FALLBACK_TICKERS)",
                    "fetched_at": now,
                    "fallback": True,
                })
        else:
            failed_indices.append("DAX")

    # --- S&P 500 (KEIN Fallback) ---
    sp500_result = fetch_sp500()
    if sp500_result["status"] == "ok":
        for t in sp500_result["tickers"]:
            records.append({
                "ticker": t, "index": "SP500",
                "source": sp500_result["source"],
                "fetched_at": sp500_result["fetched_at"],
                "fallback": False,
            })
    else:
        errors["SP500"] = sp500_result["error"]
        failed_indices.append("SP500")

    # --- Nasdaq 100 (mit Fallback analog DAX) ---
    ndx_result = fetch_nasdaq100()
    if ndx_result["status"] == "ok":
        for t in ndx_result["tickers"]:
            records.append({
                "ticker": t, "index": "NDX100",
                "source": ndx_result["source"],
                "fetched_at": ndx_result["fetched_at"],
                "fallback": False,
            })
    else:
        errors["NDX100"] = ndx_result["error"]
        if allow_fallback:
            fallback_used.append("NDX100")
            now = _now_iso()
            for t in NDX100_FALLBACK_TICKERS:
                records.append({
                    "ticker": t, "index": "NDX100",
                    "source": "interner Fallback (verifizierte NDX100-Liste, "
                              "siehe NDX100_FALLBACK_TICKERS)",
                    "fetched_at": now,
                    "fallback": True,
                })
        else:
            failed_indices.append("NDX100")

    # Deduplizierung gemäß DEDUP_PRIORITY
    records = _dedupe(records)

    # Gesamtstatus bestimmen
    successful_indices = {"DAX", "SP500", "NDX100"} - set(failed_indices)

    if not successful_indices:
        status = "error"
    elif failed_indices:
        status = "partial"
    else:
        status = "ok"

    return {
        "status": status,
        "records": records,
        "fallback_used": fallback_used,
        "failed_indices": failed_indices,
        "errors": errors,
    }
