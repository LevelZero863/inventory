from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
import math
import sqlite3

from audit import write_audit
from db import get_conn
from permissions import require_permission
from services import create_inbound, create_outbound, settle


SHEETS = {
    "产品": ["产品编码", "产品名称", "规格型号", "单位", "默认单价", "状态", "备注"],
    "客户": ["客户编码", "客户名称", "联系人", "联系电话", "地址", "结算方式", "状态", "备注"],
    "仓库": ["仓库编码", "仓库名称", "状态", "备注"],
    "入库单": ["导入单号", "入库日期", "供应商", "仓库编码", "经办人", "备注", "产品编码", "数量", "单价"],
    "出库单": ["导入单号", "出库日期", "出库类型", "客户编码", "领料人或部门", "仓库编码", "经办人", "备注", "产品编码", "数量", "单价"],
    "结算单": ["导入单号", "结算日期", "客户编码", "结算方式", "经办人", "备注", "出库单号", "结算金额"],
    "库存": ["盘点日期", "仓库编码", "产品编码", "目标库存", "备注"],
}


def _blank(value) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value)) or str(value).strip() == ""


def _text(value, field, required=False) -> str:
    if _blank(value):
        if required:
            raise ValueError(f"{field}不能为空")
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _number(value, field, minimum=None) -> float:
    if _blank(value):
        raise ValueError(f"{field}不能为空")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field}必须是数字") from exc
    if not math.isfinite(result):
        raise ValueError(f"{field}必须是有效数字")
    if minimum is not None and result < minimum:
        raise ValueError(f"{field}不得小于 {minimum}")
    return result


def _date(value, field) -> str:
    if _blank(value):
        raise ValueError(f"{field}不能为空")
    if hasattr(value, "strftime"):
        result = value.strftime("%Y-%m-%d")
    else:
        result = str(value).strip()[:10]
    try:
        return date.fromisoformat(result).isoformat()
    except ValueError as exc:
        raise ValueError(f"{field}格式无效，请使用 YYYY-MM-DD") from exc


def _prepare(rows, sheet_name):
    rows = [dict(row) for row in rows]
    if not rows:
        raise ValueError("Excel 中没有可导入的数据")
    missing = [column for column in SHEETS[sheet_name] if column not in rows[0]]
    if missing:
        raise ValueError(f"缺少必填列：{', '.join(missing)}")
    return rows


def import_products(rows, actor=None):
    require_permission(actor, "manage_master")
    rows = _prepare(rows, "产品")
    normalized = []
    seen = set()
    for index, row in enumerate(rows, 2):
        try:
            code = _text(row["产品编码"], "产品编码", True)
            if code in seen:
                raise ValueError("产品编码在文件中重复")
            seen.add(code)
            status = _text(row["状态"], "状态") or "启用"
            if status not in {"启用", "停用"}:
                raise ValueError("状态只能填写启用或停用")
            normalized.append({
                "code": code, "name": _text(row["产品名称"], "产品名称", True),
                "spec": _text(row["规格型号"], "规格型号"),
                "unit": _text(row["单位"], "单位", True),
                "default_price": _number(row["默认单价"], "默认单价", 0),
                "status": status, "remark": _text(row["备注"], "备注"),
            })
        except ValueError as exc:
            raise ValueError(f"产品表第 {index} 行：{exc}") from exc
    conn = get_conn()
    created = updated = 0
    try:
        conn.execute("BEGIN IMMEDIATE")
        for item in normalized:
            before = conn.execute("SELECT * FROM products WHERE code=?", (item["code"],)).fetchone()
            if before:
                conn.execute(
                    """UPDATE products SET name=?,spec=?,unit=?,default_price=?,status=?,remark=?
                       WHERE id=?""",
                    (item["name"], item["spec"], item["unit"], item["default_price"],
                     item["status"], item["remark"], before["id"]),
                )
                after = conn.execute("SELECT * FROM products WHERE id=?", (before["id"],)).fetchone()
                write_audit("Excel导入修改产品", actor, entity_type="产品", entity_id=before["id"],
                            source_no=item["code"], before=before, after=after, conn=conn)
                updated += 1
            else:
                cur = conn.execute(
                    """INSERT INTO products(code,name,spec,unit,default_price,status,remark)
                       VALUES(?,?,?,?,?,?,?)""",
                    tuple(item[key] for key in ("code", "name", "spec", "unit", "default_price", "status", "remark")),
                )
                write_audit("Excel导入新增产品", actor, entity_type="产品", entity_id=cur.lastrowid,
                            source_no=item["code"], after=item, conn=conn)
                created += 1
        conn.commit()
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        raise ValueError("产品名称或编码与现有资料冲突") from exc
    except Exception:
        conn.rollback(); raise
    finally:
        conn.close()
    return {"新增": created, "更新": updated}


def import_customers(rows, actor=None):
    require_permission(actor, "manage_master")
    rows = _prepare(rows, "客户")
    normalized, seen = [], set()
    for index, row in enumerate(rows, 2):
        try:
            code = _text(row["客户编码"], "客户编码", True)
            if code == "SYS-MATERIAL":
                raise ValueError("该编码为系统保留编码")
            if code in seen:
                raise ValueError("客户编码在文件中重复")
            seen.add(code)
            method = _text(row["结算方式"], "结算方式") or "月结"
            status = _text(row["状态"], "状态") or "启用"
            if method not in {"现结", "月结"}:
                raise ValueError("结算方式只能填写现结或月结")
            if status not in {"启用", "停用"}:
                raise ValueError("状态只能填写启用或停用")
            normalized.append({
                "code": code, "name": _text(row["客户名称"], "客户名称", True),
                "contact": _text(row["联系人"], "联系人"), "phone": _text(row["联系电话"], "联系电话"),
                "address": _text(row["地址"], "地址"), "settlement_method": method,
                "status": status, "remark": _text(row["备注"], "备注"),
            })
        except ValueError as exc:
            raise ValueError(f"客户表第 {index} 行：{exc}") from exc
    conn = get_conn(); created = updated = 0
    try:
        conn.execute("BEGIN IMMEDIATE")
        for item in normalized:
            before = conn.execute("SELECT * FROM customers WHERE code=?", (item["code"],)).fetchone()
            values = tuple(item[key] for key in (
                "name", "contact", "phone", "address", "settlement_method", "status", "remark"
            ))
            if before:
                conn.execute(
                    """UPDATE customers SET name=?,contact=?,phone=?,address=?,settlement_method=?,status=?,remark=?
                       WHERE id=?""", values + (before["id"],),
                )
                after = conn.execute("SELECT * FROM customers WHERE id=?", (before["id"],)).fetchone()
                write_audit("Excel导入修改客户", actor, entity_type="客户", entity_id=before["id"],
                            source_no=item["code"], before=before, after=after, conn=conn)
                updated += 1
            else:
                cur = conn.execute(
                    """INSERT INTO customers(code,name,contact,phone,address,settlement_method,status,remark)
                       VALUES(?,?,?,?,?,?,?,?)""", (item["code"],) + values,
                )
                write_audit("Excel导入新增客户", actor, entity_type="客户", entity_id=cur.lastrowid,
                            source_no=item["code"], after=item, conn=conn)
                created += 1
        conn.commit()
    except sqlite3.IntegrityError as exc:
        conn.rollback(); raise ValueError("客户名称或编码与现有资料冲突") from exc
    except Exception:
        conn.rollback(); raise
    finally:
        conn.close()
    return {"新增": created, "更新": updated}


def import_warehouses(rows, actor=None):
    require_permission(actor, "manage_master")
    rows = _prepare(rows, "仓库")
    normalized, seen = [], set()
    for index, row in enumerate(rows, 2):
        try:
            code = _text(row["仓库编码"], "仓库编码", True)
            if code in seen:
                raise ValueError("仓库编码在文件中重复")
            seen.add(code)
            status = _text(row["状态"], "状态") or "启用"
            if status not in {"启用", "停用"}:
                raise ValueError("状态只能填写启用或停用")
            normalized.append({"code": code, "name": _text(row["仓库名称"], "仓库名称", True),
                               "status": status, "remark": _text(row["备注"], "备注")})
        except ValueError as exc:
            raise ValueError(f"仓库表第 {index} 行：{exc}") from exc
    conn = get_conn(); created = updated = 0
    try:
        conn.execute("BEGIN IMMEDIATE")
        for item in normalized:
            before = conn.execute("SELECT * FROM warehouses WHERE code=?", (item["code"],)).fetchone()
            if before:
                if before["name"] != item["name"]:
                    used = any(conn.execute(
                        f"SELECT 1 FROM {table} WHERE warehouse=? LIMIT 1", (before["name"],)
                    ).fetchone() for table in ("inventory_txns", "inbound_orders", "outbound_orders"))
                    if used:
                        raise ValueError(f"仓库 {item['code']} 已有业务数据，不能通过 Excel 修改名称")
                conn.execute("UPDATE warehouses SET name=?,status=?,remark=? WHERE id=?",
                             (item["name"], item["status"], item["remark"], before["id"]))
                after = conn.execute("SELECT * FROM warehouses WHERE id=?", (before["id"],)).fetchone()
                write_audit("Excel导入修改仓库", actor, entity_type="仓库", entity_id=before["id"],
                            source_no=item["code"], before=before, after=after, conn=conn)
                updated += 1
            else:
                cur = conn.execute("INSERT INTO warehouses(code,name,status,remark) VALUES(?,?,?,?)",
                                   (item["code"], item["name"], item["status"], item["remark"]))
                write_audit("Excel导入新增仓库", actor, entity_type="仓库", entity_id=cur.lastrowid,
                            source_no=item["code"], after=item, conn=conn)
                created += 1
        conn.commit()
    except sqlite3.IntegrityError as exc:
        conn.rollback(); raise ValueError("仓库名称或编码与现有资料冲突") from exc
    except Exception:
        conn.rollback(); raise
    finally:
        conn.close()
    return {"新增": created, "更新": updated}


def _references():
    conn = get_conn()
    products = {row["code"]: dict(row) for row in conn.execute("SELECT * FROM products WHERE status='启用'")}
    customers = {row["code"]: dict(row) for row in conn.execute(
        "SELECT * FROM customers WHERE status='启用' AND code<>'SYS-MATERIAL'"
    )}
    warehouses = {row["code"]: dict(row) for row in conn.execute("SELECT * FROM warehouses WHERE status='启用'")}
    conn.close()
    return products, customers, warehouses


def _group_documents(rows, sheet_name, date_column):
    rows = _prepare(rows, sheet_name)
    groups = {}
    for index, row in enumerate(rows, 2):
        key = _text(row["导入单号"], "导入单号", True)
        groups.setdefault(key, []).append((index, row))
    for key, group in groups.items():
        dates = {_date(row[date_column], date_column) for _, row in group}
        if len(dates) != 1:
            raise ValueError(f"导入单号 {key} 的日期不一致")
    return groups


def import_inbound_orders(rows, actor=None):
    require_permission(actor, "create_inbound")
    products, _, warehouses = _references()
    groups = _group_documents(rows, "入库单", "入库日期")
    prepared = []
    for import_no, group in groups.items():
        first = group[0][1]
        warehouse_code = _text(first["仓库编码"], "仓库编码", True)
        if warehouse_code not in warehouses:
            raise ValueError(f"导入单号 {import_no}：仓库不存在或已停用")
        header_fields = ("供应商", "仓库编码", "经办人", "备注")
        if any(_text(row[field], field) != _text(first[field], field) for _, row in group for field in header_fields):
            raise ValueError(f"导入单号 {import_no} 的表头信息不一致")
        items = []
        for index, row in group:
            code = _text(row["产品编码"], "产品编码", True)
            if code not in products:
                raise ValueError(f"入库单表第 {index} 行：产品不存在或已停用")
            items.append({"product_id": products[code]["id"], "quantity": _number(row["数量"], "数量", 0.000001),
                          "price": _number(row["单价"], "单价", 0)})
        prepared.append((import_no, _date(first["入库日期"], "入库日期"), _text(first["供应商"], "供应商"),
                         warehouses[warehouse_code]["name"], _text(first["经办人"], "经办人"),
                         _text(first["备注"], "备注"), items))
    numbers = [create_inbound(order_date, supplier, warehouse, operator, f"[Excel:{import_no}] {remark}".strip(), items, actor=actor)
               for import_no, order_date, supplier, warehouse, operator, remark, items in prepared]
    return {"导入单据": len(numbers), "系统单号": numbers}


def import_outbound_orders(rows, actor=None):
    require_permission(actor, "create_outbound")
    products, customers, warehouses = _references()
    groups = _group_documents(rows, "出库单", "出库日期")
    prepared, required = [], defaultdict(float)
    for import_no, group in groups.items():
        first = group[0][1]
        outbound_type = _text(first["出库类型"], "出库类型") or "销售出库"
        if outbound_type not in {"销售出库", "领料出库"}:
            raise ValueError(f"导入单号 {import_no}：出库类型无效")
        warehouse_code = _text(first["仓库编码"], "仓库编码", True)
        if warehouse_code not in warehouses:
            raise ValueError(f"导入单号 {import_no}：仓库不存在或已停用")
        customer_code = _text(first["客户编码"], "客户编码")
        if outbound_type == "销售出库" and customer_code not in customers:
            raise ValueError(f"导入单号 {import_no}：销售出库客户不存在或已停用")
        header_fields = ("出库类型", "客户编码", "领料人或部门", "仓库编码", "经办人", "备注")
        if any(_text(row[field], field) != _text(first[field], field) for _, row in group for field in header_fields):
            raise ValueError(f"导入单号 {import_no} 的表头信息不一致")
        items = []
        for index, row in group:
            code = _text(row["产品编码"], "产品编码", True)
            if code not in products:
                raise ValueError(f"出库单表第 {index} 行：产品不存在或已停用")
            quantity = _number(row["数量"], "数量", 0.000001)
            items.append({"product_id": products[code]["id"], "quantity": quantity,
                          "price": _number(row["单价"], "单价", 0)})
            required[(products[code]["id"], warehouses[warehouse_code]["name"])] += quantity
        prepared.append((import_no, _date(first["出库日期"], "出库日期"),
                         customers.get(customer_code, {}).get("id"), warehouses[warehouse_code]["name"],
                         _text(first["经办人"], "经办人"), _text(first["备注"], "备注"), items,
                         outbound_type, _text(first["领料人或部门"], "领料人或部门")))
    conn = get_conn()
    for (product_id, warehouse), quantity in required.items():
        current = conn.execute(
            "SELECT COALESCE(SUM(qty),0) FROM inventory_txns WHERE product_id=? AND warehouse=?",
            (product_id, warehouse),
        ).fetchone()[0]
        if float(current) + 1e-9 < quantity:
            conn.close(); raise ValueError(f"仓库 {warehouse} 的导入出库数量超过当前库存")
    conn.close()
    numbers = [create_outbound(order_date, customer_id, warehouse, operator,
                               f"[Excel:{import_no}] {remark}".strip(), items, actor=actor,
                               outbound_type=outbound_type, material_recipient=recipient)
               for import_no, order_date, customer_id, warehouse, operator, remark, items, outbound_type, recipient in prepared]
    return {"导入单据": len(numbers), "系统单号": numbers}


def import_settlement_orders(rows, actor=None):
    require_permission(actor, "create_settlement")
    _, customers, _ = _references()
    groups = _group_documents(rows, "结算单", "结算日期")
    conn = get_conn(); order_map = {row["order_no"]: dict(row) for row in conn.execute(
        "SELECT id,order_no,customer_id,total_amount,settled_amount,status,outbound_type FROM outbound_orders"
    )}; conn.close()
    prepared, cumulative = [], defaultdict(float)
    for import_no, group in groups.items():
        first = group[0][1]
        customer_code = _text(first["客户编码"], "客户编码", True)
        if customer_code not in customers:
            raise ValueError(f"导入单号 {import_no}：客户不存在或已停用")
        header_fields = ("客户编码", "结算方式", "经办人", "备注")
        if any(_text(row[field], field) != _text(first[field], field) for _, row in group for field in header_fields):
            raise ValueError(f"导入单号 {import_no} 的表头信息不一致")
        allocations = {}
        for index, row in group:
            order_no = _text(row["出库单号"], "出库单号", True)
            order = order_map.get(order_no)
            if not order or order["outbound_type"] != "销售出库" or order["status"] not in {"已确认", "已生效"}:
                raise ValueError(f"结算单表第 {index} 行：出库单不存在或不可结算")
            if order["customer_id"] != customers[customer_code]["id"]:
                raise ValueError(f"结算单表第 {index} 行：出库单不属于当前客户")
            if order["id"] in allocations:
                raise ValueError(f"导入单号 {import_no}：出库单重复")
            amount = _number(row["结算金额"], "结算金额", 0.000001)
            cumulative[order["id"]] += amount
            if cumulative[order["id"]] > float(order["total_amount"] - order["settled_amount"]) + 1e-9:
                raise ValueError(f"出库单 {order_no} 的累计导入结算金额超过未收金额")
            allocations[order["id"]] = amount
        method = _text(first["结算方式"], "结算方式") or "银行转账"
        if method not in {"银行转账", "现金", "其他"}:
            raise ValueError(f"导入单号 {import_no}：结算方式无效")
        prepared.append((import_no, customers[customer_code]["id"], _date(first["结算日期"], "结算日期"),
                         method,
                         _text(first["经办人"], "经办人"), _text(first["备注"], "备注"), allocations))
    numbers = [settle(customer_id, settlement_date, method, operator,
                      f"[Excel:{import_no}] {remark}".strip(), allocations, actor=actor)
               for import_no, customer_id, settlement_date, method, operator, remark, allocations in prepared]
    return {"导入单据": len(numbers), "系统单号": numbers}


def import_inventory(rows, actor=None):
    require_permission(actor, "import_inventory")
    rows = _prepare(rows, "库存")
    products, _, warehouses = _references()
    normalized, seen = [], set()
    for index, row in enumerate(rows, 2):
        try:
            product_code = _text(row["产品编码"], "产品编码", True)
            warehouse_code = _text(row["仓库编码"], "仓库编码", True)
            if product_code not in products:
                raise ValueError("产品不存在或已停用")
            if warehouse_code not in warehouses:
                raise ValueError("仓库不存在或已停用")
            key = (products[product_code]["id"], warehouses[warehouse_code]["name"])
            if key in seen:
                raise ValueError("同一产品和仓库在文件中重复")
            seen.add(key)
            normalized.append({
                "txn_date": _date(row["盘点日期"], "盘点日期"), "product_id": key[0],
                "product_code": product_code, "warehouse": key[1],
                "target": _number(row["目标库存"], "目标库存", 0),
                "remark": _text(row["备注"], "备注"),
            })
        except ValueError as exc:
            raise ValueError(f"库存表第 {index} 行：{exc}") from exc
    source_no = "KCDR" + datetime.now().strftime("%Y%m%d%H%M%S")
    conn = get_conn(); adjustments = []
    try:
        conn.execute("BEGIN IMMEDIATE")
        for item in normalized:
            current = float(conn.execute(
                "SELECT COALESCE(SUM(qty),0) FROM inventory_txns WHERE product_id=? AND warehouse=?",
                (item["product_id"], item["warehouse"]),
            ).fetchone()[0])
            delta = item["target"] - current
            if abs(delta) > 1e-9:
                conn.execute(
                    """INSERT INTO inventory_txns(txn_date,warehouse,product_id,qty,txn_type,source_no)
                       VALUES(?,?,?,?,?,?)""",
                    (item["txn_date"], item["warehouse"], item["product_id"], delta, "库存导入调整", source_no),
                )
            adjustments.append({**item, "before_qty": current, "adjust_qty": delta})
        actor_name = (actor or {}).get("display_name") or (actor or {}).get("username") or "system"
        conn.execute("INSERT INTO operation_logs(action,source_no,operator,detail) VALUES(?,?,?,?)",
                     ("Excel导入库存", source_no, actor_name, f"{len(normalized)} 行"))
        write_audit("Excel导入库存", actor, entity_type="库存", source_no=source_no,
                    after=adjustments, detail=f"导入 {len(normalized)} 行，生成调整 {sum(abs(x['adjust_qty']) > 1e-9 for x in adjustments)} 行", conn=conn)
        conn.commit()
    except Exception:
        conn.rollback(); raise
    finally:
        conn.close()
    return {"导入行数": len(normalized), "调整行数": sum(abs(x["adjust_qty"]) > 1e-9 for x in adjustments), "批次号": source_no}
