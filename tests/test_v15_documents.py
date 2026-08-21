import tempfile
import unittest
from pathlib import Path

import db
import pdf_exports
import services


class V15DocumentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db.DATA_DIR = Path(self.tmp.name)
        db.DB_PATH = Path(self.tmp.name) / "v15.db"
        db.BACKUP_DIR = Path(self.tmp.name) / "backups"
        db.init_db()
        self.product_id = services.list_products(active_only=True)[0]["id"]
        self.customer_id = services.list_customers(active_only=True)[0]["id"]
        services.create_inbound(
            "2026-08-01", "供应商甲", "一号仓", "仓管员", "期初入库",
            [{"product_id": self.product_id, "quantity": 10, "price": 8}],
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_material_issue_reduces_stock_without_receivable(self):
        order_no = services.create_outbound(
            "2026-08-10", None, "一号仓", "仓管员", "设备维修领用",
            [{"product_id": self.product_id, "quantity": 3, "price": 8}],
            outbound_type="领料出库", material_recipient="维修部 / 王师傅",
        )
        self.assertEqual(services.stock(self.product_id, "一号仓"), 7)
        self.assertEqual(len(services.receivable_summary()), 0)
        self.assertEqual(len(services.open_receivables()), 0)
        row = services.outbound_list(outbound_type="领料出库")[0]
        self.assertEqual(row["order_no"], order_no)
        self.assertEqual(row["customer_name"], "维修部 / 王师傅")
        self.assertEqual(row["settlement_status"], "不参与结算")
        self.assertNotIn("SYS-MATERIAL", {c["code"] for c in services.list_customers()})

    def test_sales_and_material_issue_are_separated(self):
        services.create_outbound(
            "2026-08-10", self.customer_id, "一号仓", "销售员", "",
            [{"product_id": self.product_id, "quantity": 2, "price": 20}],
        )
        services.create_outbound(
            "2026-08-11", None, "一号仓", "仓管员", "",
            [{"product_id": self.product_id, "quantity": 1, "price": 8}],
            outbound_type="领料出库",
        )
        self.assertEqual(len(services.receivable_summary()), 1)
        self.assertEqual(services.receivable_summary()[0]["outstanding"], 40)
        self.assertEqual(len(services.outbound_list(outbound_type="销售出库")), 1)
        self.assertEqual(len(services.outbound_list(outbound_type="领料出库")), 1)

    def test_date_keyword_and_as_of_filters(self):
        services.create_outbound(
            "2026-08-10", None, "一号仓", "张仓管", "",
            [{"product_id": self.product_id, "quantity": 3, "price": 8}],
            outbound_type="领料出库", material_recipient="生产一部",
        )
        before = services.inventory_rows(as_of_date="2026-08-05", warehouse="一号仓")
        after = services.inventory_rows(as_of_date="2026-08-20", warehouse="一号仓")
        self.assertEqual(before[0]["current_qty"], 10)
        self.assertEqual(after[0]["current_qty"], 7)
        self.assertEqual(len(services.inbound_list("2026-08-01", "2026-08-01", keyword="供应商甲")), 1)
        self.assertEqual(len(services.inbound_list("2026-08-02", "2026-08-31")), 0)
        self.assertEqual(len(services.outbound_list(keyword="生产一部")), 1)

    def test_all_document_pdfs_are_valid(self):
        sales_no = services.create_outbound(
            "2026-08-10", self.customer_id, "一号仓", "销售员", "销售备注",
            [{"product_id": self.product_id, "quantity": 2, "price": 20}],
        )
        conn = db.get_conn()
        inbound_id = conn.execute("SELECT id FROM inbound_orders LIMIT 1").fetchone()[0]
        outbound_id = conn.execute(
            "SELECT id FROM outbound_orders WHERE order_no=?", (sales_no,)
        ).fetchone()[0]
        conn.close()
        services.settle(
            self.customer_id, "2026-08-12", "银行转账", "财务", "已到账",
            {outbound_id: 40},
        )
        settlement_id = db.get_conn().execute(
            "SELECT id FROM settlements ORDER BY id DESC LIMIT 1"
        ).fetchone()[0]
        documents = [
            pdf_exports.inbound_pdf(*services.inbound_detail(inbound_id)),
            pdf_exports.outbound_pdf(*services.outbound_detail(outbound_id)),
            pdf_exports.settlement_pdf(*services.settlement_detail(settlement_id)),
        ]
        for content in documents:
            self.assertTrue(content.startswith(b"%PDF"))
            self.assertGreater(len(content), 2000)


if __name__ == "__main__":
    unittest.main()
