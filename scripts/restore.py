#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import argparse
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db import DB_PATH, backup_database, restore_database, integrity_check


def main() -> int:
    parser = argparse.ArgumentParser(description="Safely restore SQLite database")
    parser.add_argument("backup", help="Path to backup .db file")
    args = parser.parse_args()

    source = Path(args.backup).expanduser().resolve()
    if not source.exists():
        print("backup_not_found:", source)
        return 1

    if Path(DB_PATH).exists():
        safety = backup_database("before_restore")
        print("pre_restore_backup:", safety)

    restored = restore_database(source)
    result = integrity_check(restored)
    print("restored:", restored)
    print("database_integrity:", result)
    return 0 if str(result).strip().lower() == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
