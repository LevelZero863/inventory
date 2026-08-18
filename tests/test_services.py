import tempfile
import unittest
from pathlib import Path

import db
import services


class InventoryServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db.DB_PATH = Path(self.tmp.name) / "test.db"
        db.DATA_DIR = Path(self.tmp.name)
        db.init_db()

    def tearDown(self):
        self.tmp.cleanup()

    def test_inbound_changes_stock(self):
        p = db.get_conn().execute("SELECT id FROM products WHERE code='P001'").fetchone()[0]
        services.create_inbound("2026-08-17", "供应商A", "一号仓", "测试", "", [{"product_id": p, "quantity": 100, "price": 10}])
        self.assertEqual(services.stock(p, "一号仓"), 100)
        status = db.get_conn().execute("SELECT status FROM inbound_orders ORDER BY id DESC LIMIT 1").fetchone()[0]
        self.assertEqual(status, "已生效")

    def test_inbound_supports_multiple_items(self):
        conn = db.get_conn()
        product_ids = [row[0] for row in conn.execute("SELECT id FROM products ORDER BY id LIMIT 2")]
        conn.close()
        services.create_inbound("2026-08-17", "供应商A", "一号仓", "测试", "", [
            {"product_id": product_ids[0], "quantity": 10, "price": 10},
            {"product_id": product_ids[1], "quantity": 20, "price": 20},
        ])
        self.assertEqual(services.stock(product_ids[0], "一号仓"), 10)
        self.assertEqual(services.stock(product_ids[1], "一号仓"), 20)

    def test_outbound_cannot_exceed_stock(self):
        p = db.get_conn().execute("SELECT id FROM products WHERE code='P001'").fetchone()[0]
        with self.assertRaises(ValueError):
            services.create_outbound("2026-08-17", 1, "一号仓", "测试", "", [{"product_id": p, "quantity": 1, "price": 10}])

    def test_partial_settlement(self):
        p = db.get_conn().execute("SELECT id FROM products WHERE code='P001'").fetchone()[0]
        services.create_inbound("2026-08-17", "供应商A", "一号仓", "测试", "", [{"product_id": p, "quantity": 100, "price": 10}])
        services.create_outbound("2026-08-17", 1, "一号仓", "测试", "", [{"product_id": p, "quantity": 10, "price": 20}])
        oid = db.get_conn().execute("SELECT id FROM outbound_orders ORDER BY id DESC LIMIT 1").fetchone()[0]
        services.settle(1, "2026-08-17", "银行转账", "测试", "", {oid: 100})
        row = db.get_conn().execute("SELECT settled_amount,total_amount FROM outbound_orders WHERE id=?", (oid,)).fetchone()
        self.assertEqual(row[0], 100)
        self.assertEqual(row[1], 200)

    def test_receivables_are_grouped_by_customer(self):
        p = db.get_conn().execute("SELECT id FROM products WHERE code='P001'").fetchone()[0]
        services.create_inbound("2026-08-17", "供应商A", "一号仓", "测试", "", [{"product_id": p, "quantity": 100, "price": 10}])
        services.create_outbound("2026-08-17", 1, "一号仓", "测试", "", [{"product_id": p, "quantity": 10, "price": 20}])
        services.create_outbound("2026-08-17", 1, "一号仓", "测试", "", [{"product_id": p, "quantity": 5, "price": 20}])
        summary = services.receivable_summary()
        self.assertEqual(len(summary), 1)
        self.assertEqual(summary[0]["order_count"], 2)
        self.assertEqual(summary[0]["outstanding"], 300)

    def test_outbound_total_is_sum_of_all_items(self):
        conn = db.get_conn()
        product_ids = [row[0] for row in conn.execute("SELECT id FROM products ORDER BY id LIMIT 2")]
        conn.close()
        services.create_inbound("2026-08-17", "供应商A", "一号仓", "测试", "", [
            {"product_id": product_ids[0], "quantity": 100, "price": 10},
            {"product_id": product_ids[1], "quantity": 100, "price": 20},
        ])
        services.create_outbound("2026-08-17", 1, "一号仓", "测试", "", [
            {"product_id": product_ids[0], "quantity": 2, "price": 12.5},
            {"product_id": product_ids[1], "quantity": 3, "price": 20},
        ])
        conn = db.get_conn()
        order = conn.execute("SELECT total_amount FROM outbound_orders ORDER BY id DESC LIMIT 1").fetchone()
        item_total = conn.execute("""SELECT SUM(i.amount) FROM outbound_items i
                                     JOIN outbound_orders o ON o.id=i.order_id
                                     WHERE o.id=(SELECT MAX(id) FROM outbound_orders)""").fetchone()[0]
        conn.close()
        self.assertEqual(order["total_amount"], 85)
        self.assertEqual(item_total, 85)


if __name__ == "__main__":
    unittest.main()
