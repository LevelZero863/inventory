import tempfile
import unittest
from pathlib import Path

import auth
import db


class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db.DATA_DIR = Path(self.tmp.name)
        db.DB_PATH = Path(self.tmp.name) / "auth.db"
        db.BACKUP_DIR = Path(self.tmp.name) / "backups"
        db.init_db()

    def tearDown(self):
        self.tmp.cleanup()

    def test_password_hash_is_salted_and_verifiable(self):
        first = auth.hash_password("safe-pass-123")
        second = auth.hash_password("safe-pass-123")
        self.assertNotEqual(first, second)
        self.assertTrue(auth.verify_password("safe-pass-123", first))
        self.assertFalse(auth.verify_password("wrong-password", first))

    def test_initial_admin_login_and_forced_password_change(self):
        self.assertTrue(auth.ensure_initial_admin())
        self.assertFalse(auth.ensure_initial_admin())
        self.assertIsNone(auth.authenticate(auth.INITIAL_ADMIN_USERNAME, "wrong-password"))

        user = auth.authenticate(auth.INITIAL_ADMIN_USERNAME, auth.INITIAL_ADMIN_PASSWORD)
        self.assertIsNotNone(user)
        self.assertTrue(user["must_change_password"])

        auth.change_password(user["id"], "new-safe-password")
        self.assertIsNone(auth.authenticate(auth.INITIAL_ADMIN_USERNAME, auth.INITIAL_ADMIN_PASSWORD))
        changed_user = auth.authenticate(auth.INITIAL_ADMIN_USERNAME, "new-safe-password")
        self.assertFalse(changed_user["must_change_password"])


if __name__ == "__main__":
    unittest.main()
