#!/usr/bin/env bash
# Knowlin starten (macOS/Linux; Python-Paket duckpilot).
#  - Beim ersten Mal: eigene Python-Umgebung in .venv anlegen und Pakete installieren.
#  - Hat sich requirements.txt geändert (neue Version), werden die Pakete nachinstalliert.
#  - Den API-Schlüssel trägst du in der App ein – er liegt dann im Tresor des Betriebssystems, nicht in einer Datei.
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "Python 3.11 oder neuer fehlt. Installieren über die Paketverwaltung oder https://www.python.org/downloads/"
  exit 1
fi
if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
  echo "Knowlin braucht Python 3.11 oder neuer – gefunden: $("$PY" --version 2>&1)."
  echo "Neueres Python installieren oder mit PYTHON=python3.12 ./start.sh ein anderes wählen."
  exit 1
fi

# Neu anlegen, wenn es noch keine Umgebung gibt oder eine halbe (z. B. weil python3-venv fehlte: dann fehlt pip)
if ! .venv/bin/python -m pip --version >/dev/null 2>&1; then
  echo "Lege Python-Umgebung an …"
  if ! "$PY" -m venv --clear .venv; then
    echo "Die Python-Umgebung ließ sich nicht anlegen. Unter Debian/Ubuntu fehlt dafür meist das Paket"
    echo "python3-venv:  sudo apt install python3-venv  – danach ./start.sh noch einmal starten."
    exit 1
  fi
fi
# Pakete installieren, wenn requirements.txt neu ist oder sich geändert hat (Merker in .venv)
if ! cmp -s requirements.txt .venv/requirements.txt; then
  echo "Installiere Pakete …"
  .venv/bin/python -m pip install --upgrade pip >/dev/null
  .venv/bin/python -m pip install -r requirements.txt
  cp requirements.txt .venv/requirements.txt
fi
exec .venv/bin/python -m duckpilot "$@"
