#!/bin/bash
# Double-click this file to launch the dashboard.
# Everything runs on this Mac only — no data leaves this computer.

cd "$(dirname "$0")"

echo "======================================"
echo " HBF Dashboard - starting up"
echo "======================================"
echo ""

if ! command -v python3 &> /dev/null; then
  echo "This Mac doesn't have Python installed yet."
  echo "Please go to https://www.python.org/downloads/macos/ , download and install it,"
  echo "then double-click this file again."
  echo ""
  read -p "Press Enter to close this window..."
  exit 1
fi

if [ ! -d ".venv_dashboard" ]; then
  echo "First time setup — this may take a minute or two, please wait..."
  python3 -m venv .venv_dashboard
fi

source .venv_dashboard/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

echo ""
echo "Setup complete. Opening the dashboard in your browser now..."
echo "(To stop it later, come back to this window and press Control + C.)"
echo ""

streamlit run 09_dashboard_presentation.py

echo ""
read -p "Dashboard closed. Press Enter to close this window..."
