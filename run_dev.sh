#!/bin/bash
set -e
cd "$(dirname "$0")"
if [ -f .venv/bin/activate ]; then
  source .venv/bin/activate
fi
python scripts/check_db.py
python -m unittest discover -s tests -v
python -m streamlit run app.py
