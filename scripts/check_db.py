#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db import init_db, integrity_check, get_conn


def main() -> int:
    init_db()
    result = integrity_check()
    ok = str(result).strip().lower() == "ok"
    print("database_integrity:", result)
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        print("tables:", ", ".join(r[0] for r in rows) or "(none)")
    finally:
        conn.close()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
