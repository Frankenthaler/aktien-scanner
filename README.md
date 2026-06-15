# Aktien-Scanner V1

Streamlit-basierter Swing-Trading-Scanner für DAX 40, S&P 500 und Nasdaq 100.

Scannt täglich nach Aktien in Weinstein-Stage-2-Konfiguration und erstellt eine
gewichtete Rangliste (Score 0–100) mit optionaler KI-Zusammenfassung (Anthropic API).

## Starten (lokal)

```bash
pip install -r requirements.txt
streamlit run app/streamlit_app.py
```

## Tests

```bash
python tests/seed_demo_db.py && cp demo.db aktien_scanner.db
python tests/test_signals.py
python tests/test_scorer_e2e.py
python tests/test_scheduler.py
python tests/test_ai_summary.py
python tests/test_index_constituents.py
python tests/test_frontend.py
python tests/test_deployment.py
```

## Dokumentation

- [Deployment-Anleitung](DEPLOYMENT.md)
- [Projektstatus](PROJECT_STATUS.md)

## Hinweise

- Datenabruf via yfinance (kein offizielles API)
- Datenaktualisierung manuell über Button „🔄 Daten aktualisieren" in der App
- KI-Zusammenfassung erfordert `ANTHROPIC_API_KEY` als Streamlit-Secret
