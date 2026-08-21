import sqlite3, tempfile, unittest
from pathlib import Path
import db

class SafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        db.DATA_DIR=Path(self.tmp.name)
        db.DB_PATH=Path(self.tmp.name)/"inventory.db"
        db.BACKUP_DIR=Path(self.tmp.name)/"backups"
        db.init_db()
    def tearDown(self): self.tmp.cleanup()
    def test_migration_and_integrity(self):
        self.assertEqual(db.integrity_check(), "ok")
        conn=db.get_conn()
        self.assertEqual(conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0],5)
        self.assertTrue(conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='audit_logs'"
        ).fetchone())
        self.assertIn(
            "void_reason",
            {row[1] for row in conn.execute("PRAGMA table_info(inbound_orders)")},
        )
        self.assertIn(
            "outbound_type",
            {row[1] for row in conn.execute("PRAGMA table_info(outbound_orders)")},
        )
        self.assertTrue({"code", "status", "remark"}.issubset(
            {row[1] for row in conn.execute("PRAGMA table_info(warehouses)")}
        ))
        conn.close()
    def test_backup_preserves_data(self):
        conn=db.get_conn(); conn.execute("INSERT INTO products(code,name) VALUES('X001','测试产品')"); conn.commit(); conn.close()
        b=db.backup_database("test")
        self.assertTrue(b.exists())
        other=Path(self.tmp.name)/"copy.db"
        db.restore_database(b, other)
        c=db.get_conn(other)
        self.assertEqual(c.execute("SELECT name FROM products WHERE code='X001'").fetchone()[0], '测试产品')
        c.close()

    def test_v15_warehouse_data_is_preserved_by_v16_migration(self):
        legacy = Path(self.tmp.name) / "legacy_v15.db"
        conn = sqlite3.connect(legacy)
        migrations = Path(__file__).resolve().parents[1] / "database" / "migrations"
        for version in range(1, 5):
            path = next(migrations.glob(f"{version:03d}_*.sql"))
            conn.executescript(path.read_text(encoding="utf-8"))
        conn.execute("""CREATE TABLE schema_migrations(
            version INTEGER PRIMARY KEY,name TEXT NOT NULL,applied_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        conn.executemany(
            "INSERT INTO schema_migrations(version,name) VALUES(?,?)",
            [(version, f"{version:03d}_legacy.sql") for version in range(1, 5)],
        )
        conn.execute("INSERT INTO warehouses(name) VALUES('历史仓库')")
        legacy_id = conn.execute("SELECT id FROM warehouses WHERE name='历史仓库'").fetchone()[0]
        conn.commit(); conn.close()
        db.DB_PATH = legacy
        self.assertEqual(db.migrate(auto_backup=False), [5])
        upgraded_conn = db.get_conn()
        upgraded = upgraded_conn.execute(
            "SELECT id,code,name,status FROM warehouses WHERE id=?", (legacy_id,)
        ).fetchone()
        self.assertEqual(upgraded["name"], "历史仓库")
        self.assertTrue(upgraded["code"].startswith("WH"))
        self.assertEqual(upgraded["status"], "启用")
        upgraded_conn.close()

if __name__ == '__main__': unittest.main()
