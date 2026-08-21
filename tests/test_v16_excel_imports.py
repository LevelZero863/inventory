import tempfile
import unittest
from pathlib import Path

import db
import excel_imports
import services


ADMIN = {"id": None, "username": "admin", "display_name": "管理员", "role": "admin"}
WAREHOUSE = {"id": None, "username": "warehouse", "display_name": "仓管员", "role": "warehouse"}
FINANCE = {"id": None, "username": "finance", "display_name": "财务", "role": "finance"}
VIEWER = {"id": None, "username": "viewer", "display_name": "只读", "role": "viewer"}


class V16ExcelImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db.DATA_DIR = Path(self.tmp.name)
        db.DB_PATH = Path(self.tmp.name) / "v16.db"
        db.BACKUP_DIR = Path(self.tmp.name) / "backups"
        db.init_db()

    def tearDown(self):
        self.tmp.cleanup()

    def test_master_data_import_creates_and_updates(self):
        result = excel_imports.import_products([{
            "产品编码": "PX01", "产品名称": "导入产品", "规格型号": "A",
            "单位": "件", "默认单价": 12.5, "状态": "启用", "备注": "首次",
        }], actor=ADMIN)
        self.assertEqual(result["新增"], 1)
        result = excel_imports.import_products([{
            "产品编码": "PX01", "产品名称": "导入产品修改", "规格型号": "B",
            "单位": "箱", "默认单价": 20, "状态": "停用", "备注": "更新",
        }], actor=ADMIN)
        self.assertEqual(result["更新"], 1)
        product = next(row for row in services.list_products() if row["code"] == "PX01")
        self.assertEqual(product["name"], "导入产品修改")
        self.assertEqual(product["status"], "停用")

        warehouse_result = excel_imports.import_warehouses([{
            "仓库编码": "WH100", "仓库名称": "成品仓", "状态": "启用", "备注": "东区",
        }], actor=ADMIN)
        self.assertEqual(warehouse_result["新增"], 1)
        self.assertIn("成品仓", services.list_warehouses())

    def test_inbound_outbound_settlement_import_chain(self):
        inbound = excel_imports.import_inbound_orders([
            {"导入单号": "IN-1", "入库日期": "2026-08-21", "供应商": "供应商甲",
             "仓库编码": "WH001", "经办人": "仓管", "备注": "批量",
             "产品编码": "P001", "数量": 10, "单价": 10},
            {"导入单号": "IN-1", "入库日期": "2026-08-21", "供应商": "供应商甲",
             "仓库编码": "WH001", "经办人": "仓管", "备注": "批量",
             "产品编码": "P002", "数量": 5, "单价": 20},
        ], actor=WAREHOUSE)
        self.assertEqual(inbound["导入单据"], 1)

        outbound = excel_imports.import_outbound_orders([
            {"导入单号": "OUT-1", "出库日期": "2026-08-22", "出库类型": "销售出库",
             "客户编码": "C001", "领料人或部门": "", "仓库编码": "WH001",
             "经办人": "仓管", "备注": "销售", "产品编码": "P001", "数量": 2, "单价": 30},
            {"导入单号": "OUT-2", "出库日期": "2026-08-22", "出库类型": "领料出库",
             "客户编码": "", "领料人或部门": "维修部", "仓库编码": "WH001",
             "经办人": "仓管", "备注": "维修", "产品编码": "P002", "数量": 1, "单价": 20},
        ], actor=WAREHOUSE)
        self.assertEqual(outbound["导入单据"], 2)
        self.assertEqual(len(services.receivable_summary()), 1)
        self.assertEqual(services.receivable_summary()[0]["outstanding"], 60)

        sales_order_no = next(
            row["order_no"] for row in services.outbound_list(outbound_type="销售出库")
        )
        settlement = excel_imports.import_settlement_orders([{
            "导入单号": "SET-1", "结算日期": "2026-08-23", "客户编码": "C001",
            "结算方式": "银行转账", "经办人": "财务", "备注": "到账",
            "出库单号": sales_order_no, "结算金额": 40,
        }], actor=FINANCE)
        self.assertEqual(settlement["导入单据"], 1)
        self.assertEqual(services.receivable_summary()[0]["outstanding"], 20)

    def test_inventory_import_generates_adjustment_and_audit(self):
        product_id = next(
            row["id"] for row in services.list_products(active_only=True) if row["code"] == "P001"
        )
        result = excel_imports.import_inventory([{
            "盘点日期": "2026-08-21", "仓库编码": "WH001", "产品编码": "P001",
            "目标库存": 25, "备注": "期初盘点",
        }], actor=WAREHOUSE)
        self.assertEqual(result["调整行数"], 1)
        self.assertEqual(services.stock(product_id, "一号仓"), 25)
        conn = db.get_conn()
        txn = conn.execute("SELECT txn_type,qty FROM inventory_txns ORDER BY id DESC LIMIT 1").fetchone()
        audit = conn.execute("SELECT action FROM audit_logs ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()
        self.assertEqual(txn["txn_type"], "库存导入调整")
        self.assertEqual(txn["qty"], 25)
        self.assertEqual(audit["action"], "Excel导入库存")

    def test_import_permissions_are_enforced(self):
        with self.assertRaises(PermissionError):
            excel_imports.import_inventory([{
                "盘点日期": "2026-08-21", "仓库编码": "WH001", "产品编码": "P001",
                "目标库存": 1, "备注": "",
            }], actor=VIEWER)


if __name__ == "__main__":
    unittest.main()
