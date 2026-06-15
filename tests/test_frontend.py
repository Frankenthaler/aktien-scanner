"""
tests/test_frontend.py — Frontend-Test mit Streamlit AppTest
Aktien-Scanner V1

Nutzt streamlit.testing.v1.AppTest, um die App ohne laufenden Server
zu rendern und Inhalte zu prüfen. Verwendet die Demo-Datenbank
(tests/seed_demo_db.py muss vorher ausgeführt worden sein).
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from streamlit.testing.v1 import AppTest

def full_app_text(at) -> str:
    """Sammelt allen Text aus markdown- und caption-Elementen."""
    parts = []
    for m in at.markdown:
        parts.append(str(m.value))
    for c in at.caption:
        parts.append(str(c.value))
    return " ".join(parts)


PASS, FAIL = [], []

def check(name, cond, detail=""):
    if cond:
        PASS.append(name); print(f"  ✓ {name}")
    else:
        FAIL.append(name); print(f"  ✗ {name}  {detail}")


APP_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "app", "streamlit_app.py")


# =============================================================================
# Test 1: Startseite rendert ohne Fehler
# =============================================================================
print("\n=== Test 1: Startseite ===")

at = AppTest.from_file(APP_PATH)
at.run()

check("Startseite: keine Exception", len(at.exception) == 0,
      f"(exceptions={[str(e) for e in at.exception]})")

full_text = " ".join(at.markdown.values) if hasattr(at, "markdown") else ""
all_text = " ".join(str(e.value) for e in at.main if hasattr(e, "value"))

check("Startseite: Titel 'Aktien-Scanner' vorhanden",
      any("Aktien-Scanner" in str(t.value) for t in at.title),
      f"(titles={[str(t.value) for t in at.title]})")

check("Startseite: Subheader 'Marktstatus' vorhanden",
      any("Marktstatus" in str(s.value) for s in at.subheader),
      f"(subheaders={[str(s.value) for s in at.subheader]})")

check("Startseite: Subheader 'Übersicht' vorhanden",
      any("Übersicht" in str(s.value) for s in at.subheader))

check("Startseite: Subheader 'Rangliste' vorhanden",
      any("Rangliste" in str(s.value) for s in at.subheader))

# Schaltfläche "Daten aktualisieren"
button_labels = [b.label for b in at.button]
check("Startseite: Schaltfläche 'Daten aktualisieren' vorhanden",
      any("Daten aktualisieren" in lbl for lbl in button_labels),
      f"(buttons={button_labels})")

# Filter (Selectbox: Index, Bewertung)
selectbox_labels = [s.label for s in at.selectbox]
check("Startseite: Filter 'Index' vorhanden", "Index" in selectbox_labels,
      f"(selectboxes={selectbox_labels})")
check("Startseite: Filter 'Bewertung' vorhanden", "Bewertung" in selectbox_labels,
      f"(selectboxes={selectbox_labels})")

# Bewertungsstufen-Übersicht (4 Spalten mit Zahlen)
check("Startseite: alle 4 Bewertungsstufen im Text",
      all(r in full_app_text(at) for r in
          ["Starkes Kaufsignal", "Interessant", "Beobachten", "Kein Kauf"]))

# Ranglisten-Buttons (mind. eine Aktie aus Demo-DB)
ticker_buttons = [b.label for b in at.button if "Daten aktualisieren" not in b.label]
check("Startseite: mindestens 1 Aktien-Button in Rangliste",
      len(ticker_buttons) >= 1, f"(buttons={ticker_buttons})")
check("Startseite: SAP.DE in Rangliste-Buttons",
      any("SAP.DE" in lbl for lbl in ticker_buttons), f"(buttons={ticker_buttons})")
check("Startseite: VOW3.DE (Hard Filter) NICHT in Rangliste",
      not any("VOW3.DE" in lbl for lbl in ticker_buttons), f"(buttons={ticker_buttons})")


# =============================================================================
# Test 2: Filter funktionieren
# =============================================================================
print("\n=== Test 2: Filter ===")

at2 = AppTest.from_file(APP_PATH)
at2.run()

# Index-Filter auf "DAX" setzen
index_select = [s for s in at2.selectbox if s.label == "Index"][0]
index_select.set_value("DAX")
at2.run()

check("Filter: keine Exception nach Index-Filter", len(at2.exception) == 0,
      f"(exceptions={[str(e) for e in at2.exception]})")

ticker_buttons_dax = [b.label for b in at2.button if "Daten aktualisieren" not in b.label]
check("Filter DAX: nur .DE-Ticker in Rangliste",
      all(".DE" in lbl for lbl in ticker_buttons_dax), f"(buttons={ticker_buttons_dax})")

# Bewertungs-Filter auf "Kein Kauf" setzen
rating_select = [s for s in at2.selectbox if s.label == "Bewertung"][0]
rating_select.set_value("Kein Kauf")
at2.run()

check("Filter: keine Exception nach Bewertungs-Filter", len(at2.exception) == 0,
      f"(exceptions={[str(e) for e in at2.exception]})")


# =============================================================================
# Test 3: Detailseite — Ebene 1 (einfache Ansicht)
# =============================================================================
print("\n=== Test 3: Detailseite Ebene 1 (SAP.DE) ===")

at3 = AppTest.from_file(APP_PATH)
at3.run()

# Klick auf SAP.DE-Button in der Rangliste
sap_button = [b for b in at3.button if "SAP.DE" in b.label][0]
sap_button.click()
at3.run()

check("Detailseite: keine Exception", len(at3.exception) == 0,
      f"(exceptions={[str(e) for e in at3.exception]})")

check("Detailseite: Titel 'SAP SE' vorhanden",
      any("SAP SE" in str(t.value) for t in at3.title),
      f"(titles={[str(t.value) for t in at3.title]})")

check("Detailseite: 'Zurück zur Übersicht'-Button vorhanden",
      any("Zurück" in b.label for b in at3.button),
      f"(buttons={[b.label for b in at3.button]})")

main_text = full_app_text(at3)
check("Detailseite: Score-Anzeige vorhanden ('Score:')", "Score:" in main_text)
check("Detailseite: 'Warum diese Bewertung?' vorhanden",
      "Warum diese Bewertung?" in main_text)

# Signalstatus-Symbole (✓/~/✗) vorhanden
check("Detailseite: Signalstatus-Symbole vorhanden (✓, ~ oder ✗)",
      any(sym in main_text for sym in ["✓", "~", "✗"]))

# Kennzahlen (Stop-Loss, Kursziel, CRV) als st.metric
metric_labels = [m.label for m in at3.metric]
check("Detailseite: Metrik 'Stop-Loss' vorhanden", "Stop-Loss" in metric_labels,
      f"(metrics={metric_labels})")
check("Detailseite: Metrik 'Kursziel' vorhanden", "Kursziel" in metric_labels)
check("Detailseite: Metrik 'Chance/Risiko' vorhanden", "Chance/Risiko" in metric_labels)


# =============================================================================
# Test 4: Detailseite — Ebene 2 (technische Details, aufklappbar)
# =============================================================================
print("\n=== Test 4: Detailseite Ebene 2 (technische Details) ===")

expander_labels = [e.label for e in at3.expander]
check("Detailseite: Expander 'Technische Details' vorhanden",
      any("Technische Details" in lbl for lbl in expander_labels),
      f"(expanders={expander_labels})")

tech_expander = [e for e in at3.expander if "Technische Details" in e.label][0]
tech_text = " ".join(str(m.value) for m in tech_expander.markdown) + \
            " ".join(str(getattr(c, 'value', c)) for c in getattr(tech_expander, 'caption', []))

# st.write()-Inhalte landen ebenfalls als markdown; zusätzlich gesamten App-Text nutzen
tech_text += " " + full_app_text(at3)

check("Ebene 2: SMA200 erwähnt", "SMA200" in tech_text)
check("Ebene 2: Relative Stärke erwähnt", "Relative Stärke" in tech_text)
check("Ebene 2: Breakout erwähnt", "Breakout" in tech_text)
check("Ebene 2: Marktregime erwähnt", "Marktregime" in tech_text)
check("Ebene 2: Risiko / CRV erwähnt", "Risiko" in tech_text)
check("Ebene 2: Signalversion erwähnt", "Signalversion" in tech_text)
check("Ebene 2: Datenquelle erwähnt", "Datenquelle" in tech_text)


# =============================================================================
# Test 5: Detailseite — Ebene 3 (Chart-Endkontrolle)
# =============================================================================
print("\n=== Test 5: Detailseite Ebene 3 (Chart-Endkontrolle) ===")

check("Detailseite: Expander 'Chart-Endkontrolle' vorhanden",
      any("Chart-Endkontrolle" in lbl for lbl in expander_labels),
      f"(expanders={expander_labels})")

checklist_expander = [e for e in at3.expander if "Chart-Endkontrolle" in e.label][0]
checklist_text = full_app_text(at3)

erwartete_fragen = [
    "Widerstand im Chart klar sichtbar",
    "Ausbruchskerze überzeugend",
    "erhöhte Volumen im Chart sichtbar",
    "noch kaufbar oder bereits zu weit gelaufen",
    "ausreichend Platz nach oben",
    "Stop-Loss im Chart logisch platziert",
]

for frage in erwartete_fragen:
    check(f"Ebene 3: Frage '{frage[:40]}...' vorhanden", frage in checklist_text)

# 6 Radio-Buttons für Ja/Nein
radio_count = len([r for r in at3.radio if r.key and r.key.startswith("checklist_")])
check("Ebene 3: genau 6 Ja/Nein-Radiobuttons", radio_count == 6, f"(count={radio_count})")

# Radio-Optionen prüfen
if radio_count > 0:
    first_radio = [r for r in at3.radio if r.key and r.key.startswith("checklist_")][0]
    check("Ebene 3: Radio-Optionen sind ['—','Ja','Nein']",
          list(first_radio.options) == ["—", "Ja", "Nein"],
          f"(options={list(first_radio.options)})")

# Keine automatische Auswertung -> kein "Ergebnis"/"Auswertung"-Text
check("Ebene 3: keine automatische Auswertung der Antworten",
      "Auswertung" not in checklist_text and "Ergebnis:" not in checklist_text)


# =============================================================================
# Test 6: Navigation zurück zur Startseite
# =============================================================================
print("\n=== Test 6: Navigation zurück ===")

back_button = [b for b in at3.button if "Zurück" in b.label][0]
back_button.click()
at3.run()

check("Zurück: keine Exception", len(at3.exception) == 0)
check("Zurück: Titel 'Aktien-Scanner' wieder sichtbar",
      any("Aktien-Scanner" in str(t.value) for t in at3.title))


# =============================================================================
# Test 7: Hard-Filter-Aktie (VOW3.DE) — Detailseite via direkten Session-State
# =============================================================================
print("\n=== Test 7: Detailseite für Hard-Filter-Aktie (VOW3.DE) ===")

at7 = AppTest.from_file(APP_PATH)
at7.run()
at7.session_state["page"] = "detail"
at7.session_state["selected_ticker"] = "VOW3.DE"
at7.run()

check("Hard-Filter-Detail: keine Exception", len(at7.exception) == 0,
      f"(exceptions={[str(e) for e in at7.exception]})")

main_text7 = full_app_text(at7) + " " + " ".join(str(w.value) for w in at7.warning)
check("Hard-Filter-Detail: Titel 'Volkswagen AG' vorhanden",
      any("Volkswagen AG" in str(t.value) for t in at7.title))
check("Hard-Filter-Detail: Warnhinweis zu Aufwärtstrend vorhanden",
      "Aufwärtstrend" in main_text7 and "50-Tage-Durchschnitt" in main_text7)
check("Hard-Filter-Detail: kein Score-Wert angezeigt (kein 'Score:')",
      "Score:" not in main_text7)


# =============================================================================
# Test 8: Schaltfläche "Daten aktualisieren" (Klick simuliert run_full_update)
# =============================================================================
print("\n=== Test 8: Schaltfläche 'Daten aktualisieren' ===")

at8 = AppTest.from_file(APP_PATH)
at8.run()

update_button = [b for b in at8.button if "Daten aktualisieren" in b.label][0]

# Mock run_full_update, damit kein echter Netzwerkzugriff erfolgt
from unittest.mock import patch
import scheduler

mock_result = {
    "europe": {"erfolgreich": 2, "fehlgeschlagen": 0, "fehlerhafte_ticker": [], "total": 2},
    "usa_and_scores": {
        "daten": {"erfolgreich": 4, "fehlgeschlagen": 0, "fehlerhafte_ticker": [], "total": 4},
        "scores": {"erfolgreich": 6, "fehlgeschlagen": 1, "fehlerhafte_ticker": ["VOW3.DE"], "total": 7},
    },
}

with patch("scheduler.run_full_update", return_value=mock_result):
    update_button.click()
    at8.run()

check("Daten aktualisieren: keine Exception", len(at8.exception) == 0,
      f"(exceptions={[str(e) for e in at8.exception]})")

main_text8 = full_app_text(at8)
success_texts = " ".join(str(s.value) for s in getattr(at8, "success", []))
combined8 = main_text8 + " " + success_texts
check("Daten aktualisieren: Erfolgsmeldung mit Statistik vorhanden",
      "abgeschlossen" in combined8 and "Europa-Daten" in combined8,
      f"(success={success_texts[:200]})")


# =============================================================================
# Test 9: Detailseite — Ebene 4 (KI-Zusammenfassung)
# =============================================================================
print("\n=== Test 9: Detailseite Ebene 4 (KI-Zusammenfassung) ===")

at9 = AppTest.from_file(APP_PATH)
at9.run()
sap_button9 = [b for b in at9.button if "SAP.DE" in b.label][0]
sap_button9.click()
at9.run()

expander_labels9 = [e.label for e in at9.expander]
check("Ebene 4: Expander 'KI-Zusammenfassung' vorhanden",
      any("KI-Zusammenfassung" in lbl for lbl in expander_labels9),
      f"(expanders={expander_labels9})")

check("Ebene 4: Button 'Zusammenfassung erstellen' vorhanden",
      any("Zusammenfassung erstellen" in b.label for b in at9.button),
      f"(buttons={[b.label for b in at9.button]})")

ai_text9 = full_app_text(at9)
check("Ebene 4: Hinweis auf 'keine Kaufempfehlung' / Erklärtext vorhanden",
      "erfindet keine Kurse" in ai_text9 or "Kaufempfehlung" in ai_text9)

# Klick auf "Zusammenfassung erstellen" mit gemockter generate_summary
from unittest.mock import patch as _patch

mock_success = {"success": True, "text": "Dies ist eine Testzusammenfassung in einfacher Sprache.", "error": None}

ai_button = [b for b in at9.button if "Zusammenfassung erstellen" in b.label][0]
with _patch("scoring.ai_summary.generate_summary", return_value=mock_success):
    ai_button.click()
    at9.run()

check("Ebene 4: keine Exception nach KI-Button-Klick", len(at9.exception) == 0,
      f"(exceptions={[str(e) for e in at9.exception]})")

ai_text9_after = full_app_text(at9)
check("Ebene 4: KI-Text wird nach Klick angezeigt",
      "Testzusammenfassung" in ai_text9_after, f"(text vorhanden: {'Testzusammenfassung' in ai_text9_after})")

# Fehlerfall: generate_summary liefert Fehler
at9b = AppTest.from_file(APP_PATH)
at9b.run()
sap_button9b = [b for b in at9b.button if "SAP.DE" in b.label][0]
sap_button9b.click()
at9b.run()

mock_error = {"success": False, "text": None, "error": "Keine Verbindung zur KI möglich."}
ai_button_b = [b for b in at9b.button if "Zusammenfassung erstellen" in b.label][0]
with _patch("scoring.ai_summary.generate_summary", return_value=mock_error):
    ai_button_b.click()
    at9b.run()

check("Ebene 4: keine Exception bei Fehlerfall", len(at9b.exception) == 0)
error_texts9b = " ".join(str(e.value) for e in at9b.error)
check("Ebene 4: Fehlermeldung wird angezeigt (st.error)",
      "Keine Verbindung" in error_texts9b, f"(error_texts={error_texts9b})")




# =============================================================================
print("\n" + "=" * 60)
print(f"ERGEBNIS: {len(PASS)} bestanden, {len(FAIL)} fehlgeschlagen")
print("=" * 60)

if FAIL:
    for f in FAIL:
        print(f"  - {f}")
    sys.exit(1)
sys.exit(0)
