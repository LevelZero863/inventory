#!/bin/bash
set -e
cd "$(dirname "$0")/.."
export INVENTORY_DB_PATH="$(pwd)/data/inventory_dev.db"
rm -f "$INVENTORY_DB_PATH" "$INVENTORY_DB_PATH-wal" "$INVENTORY_DB_PATH-shm"
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/check_db.py
