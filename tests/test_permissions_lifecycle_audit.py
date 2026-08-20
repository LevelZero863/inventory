import tempfile
import unittest
from pathlib import Path

import auth
import db
import services
from audit import list_audit_logs
from permissions import has_permission


ADMIN = {"id": 1, "username": "admin", "display_name": "管理员", "role": "admin"}
WAREHOUSE = {"id": None, "username": "warehouse", "display_name": "仓库", "role": "warehouse"}
FINANCE = {"id": None, "username": "finance", "display_name": "财务", "role": "finance"}
VIEWER = {"id": None, "username": "viewer", "display_name": "只读", "role": "viewer"}


class PermissionLifecycleAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db.DATA_DIR = Path(self.tmp.name)
        db.DB_PATH = Path(self.tmp.name) / "v14.db"
        db.BACKUP_DIR = Path(self.tmp.name) / "backups"
        db.init_db()
        auth.ensure_initial_admin()
        self.product_id = services.list_products(active_only=True)[0]["id"]
        self.customer_id = services.list_customers(active_only=True)[0]["id"]

    def tearDown(self):
        self.tmp.cleanup()

    def test_role_permissions_are_enforced_in_service_layer(self):
        self.assertTrue(has_permission(WAREHOUSE, "create_inbound"))
        self.assertTrue(has_permission(FINANCE, "create_settlement"))
        self.assertFalse(has_permission(VIEWER, "create_inbound"))
        with self.assertRaises(PermissionError):
            services.add_product("PX", "越权产品", "", "件", 1, actor=WAREHOUSE)
        with self.assertRaises(PermissionError):
            services.create_inbound(
                "2026-08-20", "供应商", "一号仓", "只读", "",
                [{"product_id": self.product_id, "quantity": 1, "price": 1}],
                actor=VIEWER,
            )
        with self.assertRaises(PermissionError):
            list_audit_logs(actor=VIEWER)
        with self.assertRaises(PermissionError):
            auth.list_users(actor=WAREHOUSE)

    def test_full_document_void_chain_restores_stock_and_receivable(self):
        services.create_inbound(
            "2026-08-20", "供应商", "一号仓", "仓库", "",
            [{"product_id": self.product_id, "quantity": 10, "price": 10}],
            actor=WAREHOUSE,
        )
        inbound_id = db.get_conn().execute(
            "SELECT id FROM inbound_orders ORDER BY id DESC LIMIT 1"
        ).fetchone()[0]
        services.create_outbound(
            "2026-08-20", self.customer_id, "一号仓", "仓库", "",
            [{"product_id": self.product_id, "quantity": 4, "price": 20}],
            actor=WAREHOUSE,
        )
        conn = db.get_conn()
        outbound_id = conn.execute("SELECT id FROM outbound_orders ORDER BY id DESC LIMIT 1").fetchone()[0]
        conn.close()
        services.settle(
            self.customer_id, "2026-08-20", "银行转账", "财务", "", {outbound_id: 80},
            actor=FINANCE,
        )
        settlement_id = db.get_conn().execute(
            "SELECT id FROM settlements ORDER BY id DESC LIMIT 1"
        ).fetchone()[0]

        with self.assertRaisesRegex(ValueError, "先作废关联结算单"):
            services.void_outbound(outbound_id, "录入错误", actor=ADMIN)

        services.void_settlement(settlement_id, "收款录入错误", actor=FINANCE)
        services.void_outbound(outbound_id, "客户选择错误", actor=ADMIN)
        services.void_inbound(inbound_id, "供应商选择错误", actor=ADMIN)

        self.assertEqual(services.stock(self.product_id, "一号仓"), 0)
        self.assertEqual(len(services.receivable_summary()), 0)
        conn = db.get_conn()
        self.assertEqual(conn.execute("SELECT status FROM settlements WHERE id=?", (settlement_id,)).fetchone()[0], "已作废")
        self.assertEqual(conn.execute("SELECT status FROM outbound_orders WHERE id=?", (outbound_id,)).fetchone()[0], "已作废")
        self.assertEqual(conn.execute("SELECT status FROM inbound_orders WHERE id=?", (inbound_id,)).fetchone()[0], "已作废")
        txn_types = {row[0] for row in conn.execute("SELECT txn_type FROM inventory_txns")}
        conn.close()
        self.assertIn("入库作废", txn_types)
        self.assertIn("出库作废", txn_types)

    def test_inbound_cannot_be_voided_after_stock_is_consumed(self):
        services.create_inbound(
            "2026-08-20", "供应商", "一号仓", "仓库", "",
            [{"product_id": self.product_id, "quantity": 10, "price": 10}], actor=WAREHOUSE,
        )
        inbound_id = db.get_conn().execute("SELECT id FROM inbound_orders LIMIT 1").fetchone()[0]
        services.create_outbound(
            "2026-08-20", self.customer_id, "一号仓", "仓库", "",
            [{"product_id": self.product_id, "quantity": 1, "price": 20}], actor=WAREHOUSE,
        )
        with self.assertRaisesRegex(ValueError, "库存已被使用"):
            services.void_inbound(inbound_id, "入库录入错误", actor=ADMIN)

    def test_audit_contains_actor_and_before_after_snapshots(self):
        product = services.list_products()[0]
        services.update_product(
            product["id"], product["code"], "审计后产品", product["spec"], product["unit"],
            product["default_price"], product["status"], product["remark"], actor=ADMIN,
        )
        logs = list_audit_logs(actor=ADMIN)
        changed = next(row for row in logs if row["action"] == "修改产品")
        self.assertEqual(changed["username"], "admin")
        self.assertIn(product["name"], changed["before_json"])
        self.assertIn("审计后产品", changed["after_json"])

    def test_user_management_and_last_admin_protection(self):
        user_id = auth.create_user("warehouse01", "仓库一号", "warehouse", "safe-pass-123", actor=ADMIN)
        created = next(row for row in auth.list_users(actor=ADMIN) if row["id"] == user_id)
        self.assertEqual(created["role"], "warehouse")
        with self.assertRaisesRegex(ValueError, "至少保留一个"):
            auth.update_user(1, "系统管理员", "viewer", True, actor=ADMIN)
        auth.update_user(user_id, "仓库主管", "warehouse", False, actor=ADMIN)
        self.assertIsNone(auth.authenticate("warehouse01", "safe-pass-123"))


if __name__ == "__main__":
    unittest.main()
