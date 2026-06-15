"""
utils/logging_config.py — Zentrale Logging-Konfiguration
Aktien-Scanner V1

Wird einmal beim Programmstart aufgerufen (setup_logging()).
Danach erhält jedes Modul über logging.getLogger(__name__) denselben
konfigurierten Logger inkl. Datei- und Konsolenausgabe.
"""

import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import LOG_PATH

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(level: int = logging.INFO) -> None:
    """
    Konfiguriert das Root-Logging einmalig für die gesamte Anwendung.

    - Schreibt nach scanner.log (Pfad aus config.LOG_PATH)
    - Schreibt zusätzlich auf die Konsole (stdout)
    - Einheitliches Format mit Zeitstempel, Level, Modulname, Nachricht

    Aufruf einmal beim Start (z.B. in scheduler.py oder streamlit_app.py):
        from utils.logging_config import setup_logging
        setup_logging()
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Doppelte Handler vermeiden (z.B. bei Streamlit-Reruns)
    if root_logger.handlers:
        root_logger.handlers.clear()

    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    # Datei-Handler
    file_handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)
    root_logger.addHandler(file_handler)

    # Konsolen-Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)
    root_logger.addHandler(console_handler)

    root_logger.info("Logging initialisiert. Logdatei: %s", os.path.abspath(LOG_PATH))
