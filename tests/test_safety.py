import tempfile, unittest
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
        self.assertEqual(conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0],2)
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

if __name__ == '__main__': unittest.main()
