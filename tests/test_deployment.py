"""
tests/test_deployment.py — Tests für Phase 6 (Deployment-Vorbereitung)
Aktien-Scanner V1

Prüft:
  - Alle Produktionsmodule sind importierbar (keine fehlenden Abhängigkeiten)
  - requirements.txt enthält alle tatsächlich verwendeten externen Pakete
  - requirements.txt enthält keine offensichtlich unbenötigten Pakete
  - DEPLOYMENT.md und requirements.txt existieren und sind nicht leer
  - app/streamlit_app.py startet KEINEN Scheduler (Cloud-Sicherheit)
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ast
import importlib

PASS, FAIL = [], []

def check(name, cond, detail=""):
    if cond:
        PASS.append(name); print(f"  ✓ {name}")
    else:
        FAIL.append(name); print(f"  ✗ {name}  {detail}")


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# =============================================================================
# Test 1: Alle Produktionsmodule sind importierbar
# =============================================================================
print("\n=== Test 1: Importierbarkeit aller Produktionsmodule ===")

MODULES = [
    "config",
    "scheduler",
    "data.database",
    "data.fetcher",
    "data.calendar",
    "signals.filter_sma50",
    "signals.sma200",
    "signals.relative_strength",
    "signals.breakout",
    "signals.regime",
    "signals.risk",
    "scoring.scorer",
    "scoring.ai_summary",
    "utils.logging_config",
    "app.streamlit_app",  # erfordert Streamlit-Runtime-Kontext für vollen Lauf,
                           # aber reiner Import (Modul-Top-Level) muss funktionieren
]

for module_name in MODULES:
    try:
        importlib.import_module(module_name)
        check(f"Import: {module_name}", True)
    except Exception as e:
        check(f"Import: {module_name}", False, f"({type(e).__name__}: {e})")


# =============================================================================
# Test 2: requirements.txt existiert und enthält alle externen Pakete
# =============================================================================
print("\n=== Test 2: requirements.txt — Vollständigkeit ===")

req_path = os.path.join(PROJECT_ROOT, "requirements.txt")
check("requirements.txt existiert", os.path.exists(req_path))

with open(req_path, encoding="utf-8") as f:
    req_content = f.read()

check("requirements.txt ist nicht leer", len(req_content.strip()) > 0)

# Paketnamen aus requirements.txt extrahieren (vor >=, ==, etc.)
req_packages = set()
for line in req_content.splitlines():
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    pkg = line.split(">=")[0].split("==")[0].split("<")[0].strip().lower()
    req_packages.add(pkg)

print(f"    Pakete in requirements.txt: {sorted(req_packages)}")

# Tatsächlich importierte Top-Level-Pakete im Produktionscode ermitteln
# (statische Analyse via ast, um Laufzeitfehler zu vermeiden)
PROD_DIRS = ["data", "signals", "scoring", "app", "utils"]
PROD_FILES = [os.path.join(PROJECT_ROOT, "config.py"),
               os.path.join(PROJECT_ROOT, "scheduler.py")]

for d in PROD_DIRS:
    dir_path = os.path.join(PROJECT_ROOT, d)
    for fname in os.listdir(dir_path):
        if fname.endswith(".py"):
            PROD_FILES.append(os.path.join(dir_path, fname))

# Mapping: Importname -> PyPI-Paketname (für Fälle, in denen sie abweichen)
IMPORT_TO_PACKAGE = {
    "yfinance": "yfinance",
    "pandas": "pandas",
    "numpy": "numpy",
    "streamlit": "streamlit",
    "pandas_market_calendars": "pandas_market_calendars",
    "pytz": "pytz",
    "apscheduler": "apscheduler",
    "anthropic": "anthropic",
}

# Standardbibliothek-Module, die ignoriert werden
STDLIB_IGNORE = {
    "sys", "os", "logging", "datetime", "contextlib", "sqlite3", "time",
    "ast", "importlib", "unittest", "json", "re", "typing", "functools",
    "config", "data", "signals", "scoring", "app", "utils", "scheduler",
    "tests",
}

used_external_packages = set()

for filepath in PROD_FILES:
    with open(filepath, encoding="utf-8") as f:
        try:
            tree = ast.parse(f.read(), filename=filepath)
        except SyntaxError as e:
            check(f"Syntax OK: {os.path.relpath(filepath, PROJECT_ROOT)}", False, str(e))
            continue

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top not in STDLIB_IGNORE and top in IMPORT_TO_PACKAGE:
                    used_external_packages.add(IMPORT_TO_PACKAGE[top])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                top = node.module.split(".")[0]
                if top not in STDLIB_IGNORE and top in IMPORT_TO_PACKAGE:
                    used_external_packages.add(IMPORT_TO_PACKAGE[top])

print(f"    Tatsächlich verwendete externe Pakete: {sorted(used_external_packages)}")

for pkg in used_external_packages:
    check(f"requirements.txt enthält verwendetes Paket '{pkg}'",
          pkg.lower() in req_packages, f"(req_packages={sorted(req_packages)})")

# Umgekehrt: keine Pakete in requirements.txt, die nirgends verwendet werden
for pkg in req_packages:
    check(f"requirements.txt-Paket '{pkg}' wird auch tatsächlich verwendet",
          pkg in used_external_packages, f"(used={sorted(used_external_packages)})")


# =============================================================================
# Test 3: DEPLOYMENT.md existiert und enthält Pflichtabschnitte
# =============================================================================
print("\n=== Test 3: DEPLOYMENT.md — Vollständigkeit ===")

deploy_path = os.path.join(PROJECT_ROOT, "DEPLOYMENT.md")
check("DEPLOYMENT.md existiert", os.path.exists(deploy_path))

with open(deploy_path, encoding="utf-8") as f:
    deploy_content = f.read()

required_sections = [
    "GitHub-Repository",
    "Streamlit Community Cloud",
    "ANTHROPIC_API_KEY",
    "Secrets",
    "Scheduler",
    "Abschlusstest",
    "Fehlerdiagnose",
]
for section in required_sections:
    check(f"DEPLOYMENT.md enthält Abschnitt zu '{section}'", section in deploy_content)

# MANUELLE SCHRITTE müssen klar gekennzeichnet sein
check("DEPLOYMENT.md kennzeichnet manuelle Schritte explizit",
      "MANUELLER SCHRITT" in deploy_content)

manual_count = deploy_content.count("MANUELLER SCHRITT")
check("DEPLOYMENT.md enthält mindestens 4 manuelle Schritte", manual_count >= 4,
      f"(count={manual_count})")


# =============================================================================
# Test 4: app/streamlit_app.py startet keinen Scheduler (Cloud-Sicherheit)
# =============================================================================
print("\n=== Test 4: Kein Scheduler-Start im Frontend ===")

app_path = os.path.join(PROJECT_ROOT, "app", "streamlit_app.py")
with open(app_path, encoding="utf-8") as f:
    app_content = f.read()

check("streamlit_app.py importiert NICHT create_scheduler",
      "create_scheduler" not in app_content)
check("streamlit_app.py importiert NICHT BlockingScheduler/BackgroundScheduler",
      "BlockingScheduler" not in app_content and "BackgroundScheduler" not in app_content)
check("streamlit_app.py importiert run_full_update (manueller Update-Pfad)",
      "run_full_update" in app_content)
check("streamlit_app.py ruft scheduler.main() NICHT auf",
      "scheduler.main()" not in app_content and ".main()" not in app_content)


# =============================================================================
# Test 5: scheduler.py main() bleibt für lokalen Betrieb funktionsfähig
# =============================================================================
print("\n=== Test 5: scheduler.py — lokaler Scheduler-Modus unverändert ===")

sched_path = os.path.join(PROJECT_ROOT, "scheduler.py")
with open(sched_path, encoding="utf-8") as f:
    sched_content = f.read()

check("scheduler.py enthält create_scheduler()", "def create_scheduler" in sched_content)
check("scheduler.py enthält main()", "def main()" in sched_content)
check("scheduler.py enthält run_full_update() für manuellen Cloud-Pfad",
      "def run_full_update" in sched_content)


# =============================================================================
print("\n" + "=" * 60)
print(f"ERGEBNIS: {len(PASS)} bestanden, {len(FAIL)} fehlgeschlagen")
print("=" * 60)

if FAIL:
    for f in FAIL:
        print(f"  - {f}")
    sys.exit(1)
sys.exit(0)
