from __future__ import annotations
import os, sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = Path(os.getenv("INVENTORY_DB_PATH", str(DATA_DIR / "inventory.db")))
MIGRATIONS_DIR = BASE_DIR / "database" / "migrations"
BACKUP_DIR = BASE_DIR / "backups"


def get_conn(path: Path | None = None) -> sqlite3.Connection:
    db_path = Path(path or DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _migration_files():
    return sorted(MIGRATIONS_DIR.glob("*.sql"))


def _ensure_migration_table(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS schema_migrations (
        version INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")


def migrate(auto_backup: bool = True) -> list[int]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = get_conn()
    try:
        _ensure_migration_table(conn)
        files = _migration_files()
        applied = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
        # Upgrade databases created by the original Demo without rewriting data.
        if not applied and conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='products'").fetchone():
            conn.execute("INSERT INTO schema_migrations(version,name) VALUES(1,'001_initial.sql (legacy baseline)')")
            conn.commit()
            applied.add(1)
        pending = [(int(f.stem.split('_',1)[0]), f) for f in files if int(f.stem.split('_',1)[0]) not in applied]
        if pending and auto_backup and DB_PATH.exists() and DB_PATH.stat().st_size > 0:
            backup_database()
        for version, path in pending:
            sql = path.read_text(encoding="utf-8")
            conn.execute("BEGIN")
            try:
                conn.executescript(sql)
                conn.execute("INSERT INTO schema_migrations(version,name) VALUES(?,?)", (version, path.name))
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return [v for v, _ in pending]
    finally:
        conn.close()


def backup_database(label: str = "auto") -> Path:
    import datetime
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    target = BACKUP_DIR / f"inventory_{stamp}_{label}.db"
    source = Path(DB_PATH)
    if not source.exists():
        return target
    src = get_conn(source)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close(); src.close()
    return target


def restore_database(backup_path: str | Path, target: Path | None = None) -> Path:
    source = Path(backup_path)
    target = Path(target or DB_PATH)
    if not source.exists():
        raise FileNotFoundError(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".restore-tmp")
    src = sqlite3.connect(source)
    dst = sqlite3.connect(tmp)
    try:
        src.backup(dst); dst.commit()
    finally:
        dst.close(); src.close()
    os.replace(tmp, target)
    return target


def integrity_check(path: Path | None = None) -> str:
    conn = get_conn(path)
    try:
        return conn.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        conn.close()


def init_db(seed: bool = True) -> None:
    migrate(auto_backup=True)
    conn = get_conn()
    try:
        if seed and conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
            conn.executemany("INSERT INTO products(code,name,spec,unit,default_price) VALUES (?,?,?,?,?)", [
                ("P001", "产品A", "规格A", "件", 10), ("P002", "产品B", "规格B", "件", 20), ("P003", "产品C", "规格C", "箱", 80)])
            conn.executemany("INSERT INTO customers(code,name,contact,settlement_method) VALUES (?,?,?,?)", [
                ("C001", "客户A", "张三", "月结"), ("C002", "客户B", "李四", "现结")])
            conn.executemany("INSERT INTO warehouses(name) VALUES (?)", [("一号仓",), ("二号仓",)])
            conn.commit()
    finally:
        conn.close()
