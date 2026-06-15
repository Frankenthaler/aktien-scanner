"""
data/calendar.py — Marktkalender
Aktien-Scanner V1
Liefert für jeden Markt den korrekten letzten abgeschlossenen Handelstag.
"""

import logging
from datetime import date, datetime, timedelta

import pandas_market_calendars as mcal
import pytz

logger = logging.getLogger(__name__)

# Mapping: interner Marktname → pandas_market_calendars Name
MARKET_CALENDAR_MAP = {
    "XETRA":   "XETR",    # Korrekte Bezeichnung in pandas_market_calendars
    "NYSE":    "NYSE",
    "NASDAQ":  "NASDAQ",
}

# Markt-Zeitzonen für "ist Handel abgeschlossen"-Prüfung
MARKET_CLOSE_UTC = {
    "XETRA":  {"hour": 16, "minute": 30},   # 17:30 MEZ = 16:30 UTC (Winterzeit)
    "NYSE":   {"hour": 21, "minute": 0},    # 22:00 MEZ = 21:00 UTC (Winterzeit)
    "NASDAQ": {"hour": 21, "minute": 0},
}


def get_last_trading_day(market: str) -> date:
    """
    Gibt den letzten sicher abgeschlossenen Handelstag zurück.
    Niemals der aktuelle Tag, wenn Handel noch läuft.

    Args:
        market: "XETRA", "NYSE" oder "NASDAQ"

    Returns:
        date: Letzter abgeschlossener Handelstag
    """
    cal_name = MARKET_CALENDAR_MAP.get(market)
    if not cal_name:
        logger.warning(f"Unbekannter Markt: {market}. Fallback auf NYSE.")
        cal_name = "NYSE"

    try:
        cal = mcal.get_calendar(cal_name)
        now_utc = datetime.utcnow()
        today = now_utc.date()

        # Letzte 10 Tage prüfen (sicher genug für Feiertage)
        start = today - timedelta(days=10)
        schedule = cal.schedule(
            start_date=start.strftime("%Y-%m-%d"),
            end_date=today.strftime("%Y-%m-%d")
        )

        if schedule.empty:
            logger.warning(f"Kein Handelskalender für {market}, Fallback auf gestern.")
            return today - timedelta(days=1)

        # Heutigen Tag nur einbeziehen wenn Handel abgeschlossen
        close_info = MARKET_CLOSE_UTC.get(market, {"hour": 21, "minute": 0})
        market_close_utc = now_utc.replace(
            hour=close_info["hour"],
            minute=close_info["minute"],
            second=0,
            microsecond=0
        )

        trading_days = [d.date() for d in schedule.index]

        if today in trading_days and now_utc >= market_close_utc:
            return today
        else:
            # Letzten Handelstag vor heute zurückgeben
            past_days = [d for d in trading_days if d < today]
            if past_days:
                return max(past_days)
            return today - timedelta(days=1)

    except Exception as e:
        logger.error(f"Kalenderfehler für {market}: {e}. Fallback auf gestern.")
        return date.today() - timedelta(days=1)


def is_trading_day(market: str, check_date: date) -> bool:
    """
    Prüft ob ein Datum ein Handelstag für den Markt ist.

    Args:
        market: "XETRA", "NYSE" oder "NASDAQ"
        check_date: Zu prüfendes Datum

    Returns:
        bool
    """
    cal_name = MARKET_CALENDAR_MAP.get(market, "NYSE")
    try:
        cal = mcal.get_calendar(cal_name)
        date_str = check_date.strftime("%Y-%m-%d")
        schedule = cal.schedule(start_date=date_str, end_date=date_str)
        return not schedule.empty
    except Exception as e:
        logger.error(f"is_trading_day Fehler: {e}")
        return check_date.weekday() < 5  # Fallback: kein Wochenende
