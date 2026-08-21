from __future__ import annotations

from collections import defaultdict
from datetime import date
import sqlite3
from typing import Iterable

from audit import write_audit
from db import get_conn
from permissions import require_permission

MATERIAL_CUSTOMER_CODE = "SYS-MATERIAL"
OUTBOUND_TYPES = {"销售出库", "领料出库"}


def _raise_friendly_unique_error(exc: sqlite3.IntegrityError, entity: str) -> None:
    if "unique" in str(exc).lower():
        raise ValueError(f"{entity}编码已存在，请使用其他编码") from exc
    raise exc


def next_no(prefix: str) -> str:
    today = date.today().strftime("%Y%m%d")
    conn = get_conn()
    row = conn.execute("SELECT MAX(CAST(substr(source_no, 11) AS INTEGER)) FROM operation_logs WHERE source_no LIKE ?", (f"{prefix}{today}%",)).fetchone()
    conn.close()
    return f"{prefix}{today}{int(row[0] or 0) + 1:03d}"


def list_products(active_only: bool = False):
    conn = get_conn()
    sql = "SELECT * FROM products"
    if active_only:
        sql += " WHERE status='启用'"
    rows = conn.execute(sql + " ORDER BY id DESC").fetchall()
    conn.close()
    return rows


def list_customers(active_only: bool = False, include_system: bool = False):
    conn = get_conn()
    sql = "SELECT * FROM customers"
    conditions = []
    if active_only:
        conditions.append("status='启用'")
    if not include_system:
        conditions.append("code<>?")
    params = [] if include_system else [MATERIAL_CUSTOMER_CODE]
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    rows = conn.execute(sql + " ORDER BY id DESC", params).fetchall()
    conn.close()
    return rows


def list_warehouses():
    conn = get_conn(); rows = conn.execute("SELECT name FROM warehouses ORDER BY id").fetchall(); conn.close(); return [r[0] for r in rows]


def add_product(code, name, spec, unit, price, status="启用", remark="", actor=None):
    require_permission(actor, "manage_master")
    code, name, unit = str(code).strip(), str(name).strip(), str(unit).strip()
    if not code or not name or not unit:
        raise ValueError("产品编码、产品名称和单位不能为空")
    if float(price) < 0:
        raise ValueError("默认单价不得小于 0")
    if status not in {"启用", "停用"}:
        raise ValueError("产品状态无效")
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO products(code,name,spec,unit,default_price,status,remark) VALUES(?,?,?,?,?,?,?)",
            (code, name, str(spec).strip(), unit, float(price), status, str(remark).strip()),
        )
        product_id = int(cur.lastrowid)
        write_audit(
            "新增产品", actor, entity_type="产品", entity_id=product_id, source_no=code,
            after={"code": code, "name": name, "spec": str(spec).strip(), "unit": unit,
                   "default_price": float(price), "status": status, "remark": str(remark).strip()},
            conn=conn,
        )
        conn.commit()
    except sqlite3.IntegrityError as exc:
        _raise_friendly_unique_error(exc, "产品")
    finally:
        conn.close()


def update_product(product_id, code, name, spec, unit, price, status, remark="", actor=None):
    require_permission(actor, "manage_master")
    code, name, unit = str(code).strip(), str(name).strip(), str(unit).strip()
    if not code or not name or not unit:
        raise ValueError("产品编码、产品名称和单位不能为空")
    if float(price) < 0:
        raise ValueError("默认单价不得小于 0")
    if status not in {"启用", "停用"}:
        raise ValueError("产品状态无效")
    conn = get_conn()
    try:
        before = conn.execute("SELECT * FROM products WHERE id=?", (int(product_id),)).fetchone()
        if not before:
            raise ValueError("产品不存在")
        cur = conn.execute(
            """UPDATE products
               SET code=?,name=?,spec=?,unit=?,default_price=?,status=?,remark=?
               WHERE id=?""",
            (code, name, str(spec).strip(), unit, float(price), status, str(remark).strip(), int(product_id)),
        )
        if cur.rowcount != 1:
            raise ValueError("产品不存在")
        after = conn.execute("SELECT * FROM products WHERE id=?", (int(product_id),)).fetchone()
        if dict(before) != dict(after):
            write_audit(
                "修改产品", actor, entity_type="产品", entity_id=int(product_id), source_no=code,
                before=before, after=after, conn=conn,
            )
        conn.commit()
    except sqlite3.IntegrityError as exc:
        _raise_friendly_unique_error(exc, "产品")
    finally:
        conn.close()


def add_customer(code, name, contact, phone, address, method, status="启用", remark="", actor=None):
    require_permission(actor, "manage_master")
    code, name = str(code).strip(), str(name).strip()
    if not code or not name:
        raise ValueError("客户编码和客户名称不能为空")
    if method not in {"现结", "月结"}:
        raise ValueError("结算方式无效")
    if status not in {"启用", "停用"}:
        raise ValueError("客户状态无效")
    conn = get_conn()
    try:
        cur = conn.execute(
            """INSERT INTO customers(
                   code,name,contact,phone,address,settlement_method,status,remark
               ) VALUES(?,?,?,?,?,?,?,?)""",
            (
                code, name, str(contact).strip(), str(phone).strip(), str(address).strip(),
                method, status, str(remark).strip(),
            ),
        )
        customer_id = int(cur.lastrowid)
        write_audit(
            "新增客户", actor, entity_type="客户", entity_id=customer_id, source_no=code,
            after={"code": code, "name": name, "contact": str(contact).strip(),
                   "phone": str(phone).strip(), "address": str(address).strip(),
                   "settlement_method": method, "status": status, "remark": str(remark).strip()},
            conn=conn,
        )
        conn.commit()
    except sqlite3.IntegrityError as exc:
        _raise_friendly_unique_error(exc, "客户")
    finally:
        conn.close()


def update_customer(customer_id, code, name, contact, phone, address, method, status, remark="", actor=None):
    require_permission(actor, "manage_master")
    code, name = str(code).strip(), str(name).strip()
    if not code or not name:
        raise ValueError("客户编码和客户名称不能为空")
    if method not in {"现结", "月结"}:
        raise ValueError("结算方式无效")
    if status not in {"启用", "停用"}:
        raise ValueError("客户状态无效")
    conn = get_conn()
    try:
        before = conn.execute("SELECT * FROM customers WHERE id=?", (int(customer_id),)).fetchone()
        if not before:
            raise ValueError("客户不存在")
        cur = conn.execute(
            """UPDATE customers
               SET code=?,name=?,contact=?,phone=?,address=?,settlement_method=?,status=?,remark=?
               WHERE id=?""",
            (
                code, name, str(contact).strip(), str(phone).strip(), str(address).strip(),
                method, status, str(remark).strip(), int(customer_id),
            ),
        )
        if cur.rowcount != 1:
            raise ValueError("客户不存在")
        after = conn.execute("SELECT * FROM customers WHERE id=?", (int(customer_id),)).fetchone()
        if dict(before) != dict(after):
            write_audit(
                "修改客户", actor, entity_type="客户", entity_id=int(customer_id), source_no=code,
                before=before, after=after, conn=conn,
            )
        conn.commit()
    except sqlite3.IntegrityError as exc:
        _raise_friendly_unique_error(exc, "客户")
    finally:
        conn.close()


def inventory_rows(as_of_date=None, warehouse=None, keyword=None, include_zero=True):
    conn = get_conn()
    txn_date_condition = ""
    params = []
    if as_of_date:
        txn_date_condition = " AND t.txn_date<=?"
        params.append(str(as_of_date))
    conditions = []
    if warehouse and warehouse != "全部":
        conditions.append("COALESCE(t.warehouse,'暂无库存')=?")
        params.append(str(warehouse))
    if keyword:
        conditions.append("(p.code LIKE ? OR p.name LIKE ? OR p.spec LIKE ?)")
        pattern = f"%{str(keyword).strip()}%"
        params.extend([pattern, pattern, pattern])
    having = "" if include_zero else " HAVING ABS(COALESCE(SUM(t.qty),0))>0.000000001"
    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    rows = conn.execute(f"""
        SELECT p.code product_code,p.name product_name,p.spec,p.unit,
               COALESCE(t.warehouse,'暂无库存') warehouse,
               COALESCE(SUM(t.qty),0) current_qty,COALESCE(SUM(t.qty),0) available_qty
        FROM products p LEFT JOIN inventory_txns t ON t.product_id=p.id{txn_date_condition}
        {where}
        GROUP BY p.id,t.warehouse{having} ORDER BY p.code,t.warehouse
    """, params).fetchall()
    conn.close(); return rows


def stock(product_id: int, warehouse: str) -> float:
    conn = get_conn(); row = conn.execute("SELECT COALESCE(SUM(qty),0) FROM inventory_txns WHERE product_id=? AND warehouse=?", (product_id, warehouse)).fetchone(); conn.close(); return float(row[0])


def _validate_active_products(items: list[dict]) -> None:
    product_ids = sorted({int(item["product_id"]) for item in items})
    placeholders = ",".join("?" for _ in product_ids)
    conn = get_conn()
    rows = conn.execute(
        f"SELECT id FROM products WHERE status='启用' AND id IN ({placeholders})",
        product_ids,
    ).fetchall()
    conn.close()
    active_ids = {int(row[0]) for row in rows}
    missing = [product_id for product_id in product_ids if product_id not in active_ids]
    if missing:
        raise ValueError(f"产品ID {missing[0]} 不存在或已停用")


def create_inbound(order_date, supplier, warehouse, operator, remark, items: Iterable[dict], confirm=None, actor=None):
    """Create an inbound order and apply it immediately.

    ``confirm`` is retained only for compatibility with V1.0.1 callers. New
    orders no longer have a draft state.
    """
    require_permission(actor, "create_inbound")
    items = list(items)
    if not items: raise ValueError("至少需要一条入库明细")
    if any(i["quantity"] <= 0 for i in items): raise ValueError("入库数量必须大于0")
    if any(i["price"] < 0 for i in items): raise ValueError("单价不得小于0")
    _validate_active_products(items)
    total = sum(i["quantity"] * i["price"] for i in items)
    no = next_no("RK")
    conn = get_conn()
    try:
        conn.execute("BEGIN")
        cur = conn.execute("INSERT INTO inbound_orders(order_no,order_date,supplier,warehouse,operator,remark,status,total_amount) VALUES(?,?,?,?,?,?,?,?)", (no,order_date,supplier,warehouse,operator,remark,"已生效",total))
        oid = cur.lastrowid
        for i in items:
            amount=i["quantity"]*i["price"]
            conn.execute("INSERT INTO inbound_items(order_id,product_id,quantity,price,amount) VALUES(?,?,?,?,?)", (oid,i["product_id"],i["quantity"],i["price"],amount))
            conn.execute("INSERT INTO inventory_txns(txn_date,warehouse,product_id,qty,txn_type,source_no) VALUES(?,?,?,?,?,?)", (order_date,warehouse,i["product_id"],i["quantity"],"入库",no))
        conn.execute("INSERT INTO operation_logs(action,source_no,operator,detail) VALUES(?,?,?,?)", ("入库生效",no,operator,""))
        write_audit(
            "入库单生效", actor, entity_type="入库单", entity_id=oid, source_no=no,
            after={"order_no": no, "order_date": order_date, "supplier": supplier,
                   "warehouse": warehouse, "operator": operator, "remark": remark,
                   "status": "已生效", "total_amount": total, "items": items},
            conn=conn,
        )
        conn.commit()
    except Exception:
        conn.rollback(); raise
    finally: conn.close()
    return no


def create_outbound(
    order_date, customer_id, warehouse, operator, remark, items: Iterable[dict],
    confirm=None, actor=None, outbound_type="销售出库", material_recipient="",
):
    """Create an outbound order and apply it immediately.

    ``confirm`` is retained only for compatibility with V1.0.1 callers. New
    orders no longer have a draft state.
    """
    require_permission(actor, "create_outbound")
    if outbound_type not in OUTBOUND_TYPES:
        raise ValueError("出库类型无效")
    items = list(items)
    if not items: raise ValueError("至少需要一条出库明细")
    if any(i["quantity"] <= 0 for i in items): raise ValueError("出库数量必须大于0")
    if any(i["price"] < 0 for i in items): raise ValueError("单价不得小于0")
    _validate_active_products(items)
    conn = get_conn()
    if outbound_type == "销售出库":
        customer = conn.execute(
            "SELECT id FROM customers WHERE id=? AND status='启用' AND code<>?",
            (int(customer_id), MATERIAL_CUSTOMER_CODE),
        ).fetchone()
        if not customer:
            conn.close()
            raise ValueError("客户不存在或已停用")
        resolved_customer_id = int(customer_id)
        material_recipient = ""
    else:
        conn.execute(
            """INSERT OR IGNORE INTO customers(
                   code,name,contact,phone,address,settlement_method,status,remark
               ) VALUES(?,?,?,?,?,?,?,?)""",
            (MATERIAL_CUSTOMER_CODE, "内部领料（系统）", "", "", "", "现结", "停用",
             "系统内部客户，请勿修改"),
        )
        conn.commit()
        customer = conn.execute(
            "SELECT id FROM customers WHERE code=?", (MATERIAL_CUSTOMER_CODE,)
        ).fetchone()
        if not customer:
            conn.close()
            raise ValueError("领料出库系统资料不存在，请先执行数据库迁移")
        resolved_customer_id = int(customer["id"])
        material_recipient = str(material_recipient).strip()
    conn.close()
    required = defaultdict(float)
    for i in items:
        required[int(i["product_id"])] += float(i["quantity"])
    for product_id, quantity in required.items():
        if stock(product_id, warehouse) < quantity:
            raise ValueError(f"产品ID {product_id} 当前库存不足")
    total=sum(i["quantity"]*i["price"] for i in items)
    no=next_no("CK")
    conn=get_conn()
    try:
        conn.execute("BEGIN")
        cur=conn.execute(
            """INSERT INTO outbound_orders(
                   order_no,order_date,customer_id,warehouse,operator,remark,status,total_amount,
                   outbound_type,material_recipient
               ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (no,order_date,resolved_customer_id,warehouse,operator,remark,"已生效",total,
             outbound_type,material_recipient),
        )
        oid=cur.lastrowid
        for i in items:
            amount=i["quantity"]*i["price"]
            conn.execute("INSERT INTO outbound_items(order_id,product_id,quantity,price,amount) VALUES(?,?,?,?,?)", (oid,i["product_id"],i["quantity"],i["price"],amount))
            conn.execute("INSERT INTO inventory_txns(txn_date,warehouse,product_id,qty,txn_type,source_no) VALUES(?,?,?,?,?,?)", (order_date,warehouse,i["product_id"],-i["quantity"],"出库",no))
        conn.execute("INSERT INTO operation_logs(action,source_no,operator,detail) VALUES(?,?,?,?)", ("出库生效",no,operator,""))
        write_audit(
            "出库单生效", actor, entity_type="出库单", entity_id=oid, source_no=no,
            after={"order_no": no, "order_date": order_date,
                   "customer_id": resolved_customer_id if outbound_type == "销售出库" else None,
                   "outbound_type": outbound_type, "material_recipient": material_recipient,
                   "warehouse": warehouse, "operator": operator, "remark": remark,
                   "status": "已生效", "total_amount": total, "items": items},
            conn=conn,
        )
        conn.commit()
    except Exception:
        conn.rollback(); raise
    finally: conn.close()
    return no


def open_receivables(customer_id=None):
    conn=get_conn()
    sql="""SELECT o.id,o.order_no,o.order_date,c.name customer_name,o.total_amount,o.settled_amount,
           o.total_amount-o.settled_amount outstanding,
           CASE WHEN o.settled_amount<=0 THEN '未结算' WHEN o.settled_amount<o.total_amount THEN '部分结算' ELSE '已结算' END settlement_status
           FROM outbound_orders o JOIN customers c ON c.id=o.customer_id
           WHERE o.outbound_type='销售出库'
             AND o.status IN ('已确认','已生效') AND o.total_amount-o.settled_amount>0"""
    params=[]
    if customer_id is not None: sql += " AND o.customer_id=?"; params.append(customer_id)
    sql += " ORDER BY o.order_date,o.id"
    rows=conn.execute(sql,params).fetchall(); conn.close(); return rows


def receivable_summary():
    """Return outstanding receivables grouped by customer."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT c.id customer_id,c.code customer_code,c.name customer_name,
               COUNT(o.id) order_count,
               COALESCE(SUM(o.total_amount),0) total_amount,
               COALESCE(SUM(o.settled_amount),0) settled_amount,
               COALESCE(SUM(o.total_amount-o.settled_amount),0) outstanding
        FROM outbound_orders o
        JOIN customers c ON c.id=o.customer_id
        WHERE o.outbound_type='销售出库'
          AND o.status IN ('已确认','已生效')
          AND o.total_amount-o.settled_amount>0
        GROUP BY c.id,c.code,c.name
        ORDER BY outstanding DESC,c.id
    """).fetchall()
    conn.close()
    return rows


def settle(customer_id, settlement_date, method, operator, remark, allocations: dict[int,float], actor=None):
    require_permission(actor, "create_settlement")
    allocations={int(k):float(v) for k,v in allocations.items() if float(v)>0}
    if not allocations: raise ValueError("至少选择一张出库单并填写结算金额")
    conn=get_conn()
    try:
        conn.execute("BEGIN")
        total=0
        for oid, amount in allocations.items():
            row=conn.execute(
                "SELECT customer_id,total_amount,settled_amount,status,outbound_type FROM outbound_orders WHERE id=?",
                (oid,),
            ).fetchone()
            if not row: raise ValueError("出库单不存在")
            if row[4] != "销售出库": raise ValueError("领料出库不参与应收结算")
            if row[0] != customer_id: raise ValueError("只能结算当前客户的出库单")
            if row[3] not in {"已确认", "已生效"}:
                raise ValueError("只能结算已生效的出库单")
            outstanding=row[1]-row[2]
            if amount<=0 or amount>outstanding+1e-9: raise ValueError(f"出库单 {oid} 本次结算金额超过未结算金额")
            total+=amount
        no=next_no("JS")
        cur=conn.execute("INSERT INTO settlements(settlement_no,settlement_date,customer_id,method,amount,operator,remark) VALUES(?,?,?,?,?,?,?)",(no,settlement_date,customer_id,method,total,operator,remark))
        sid=cur.lastrowid
        for oid,amount in allocations.items():
            conn.execute("INSERT INTO settlement_items(settlement_id,outbound_order_id,amount) VALUES(?,?,?)",(sid,oid,amount))
            row=conn.execute("SELECT total_amount,settled_amount FROM outbound_orders WHERE id=?",(oid,)).fetchone()
            new_settled=row[1]+amount
            conn.execute("UPDATE outbound_orders SET settled_amount=? WHERE id=?",(new_settled,oid))
        conn.execute("INSERT INTO operation_logs(action,source_no,operator,detail) VALUES(?,?,?,?)",("结算",no,operator,f"金额 {total:.2f}"))
        write_audit(
            "结算单生效", actor, entity_type="结算单", entity_id=sid, source_no=no,
            after={"settlement_no": no, "settlement_date": settlement_date,
                   "customer_id": int(customer_id), "method": method, "amount": total,
                   "operator": operator, "remark": remark, "status": "已生效",
                   "allocations": allocations},
            conn=conn,
        )
        conn.commit()
    except Exception:
        conn.rollback(); raise
    finally: conn.close()
    return no


def void_inbound(order_id: int, reason: str, actor=None) -> None:
    require_permission(actor, "void_inbound")
    reason = str(reason).strip()
    if len(reason) < 3:
        raise ValueError("作废原因至少填写 3 个字")
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        order = conn.execute("SELECT * FROM inbound_orders WHERE id=?", (int(order_id),)).fetchone()
        if not order:
            raise ValueError("入库单不存在")
        if order["status"] not in {"已确认", "已生效"}:
            raise ValueError("只有已生效的入库单可以作废")
        items = conn.execute(
            "SELECT product_id,SUM(quantity) quantity FROM inbound_items WHERE order_id=? GROUP BY product_id",
            (int(order_id),),
        ).fetchall()
        for item in items:
            current = conn.execute(
                "SELECT COALESCE(SUM(qty),0) FROM inventory_txns WHERE product_id=? AND warehouse=?",
                (item["product_id"], order["warehouse"]),
            ).fetchone()[0]
            if float(current) + 1e-9 < float(item["quantity"]):
                raise ValueError("该入库单对应库存已被使用，不能直接作废；请先处理后续出库")
        for item in items:
            conn.execute(
                """INSERT INTO inventory_txns(
                       txn_date,warehouse,product_id,qty,txn_type,source_no
                   ) VALUES(?,?,?,?,?,?)""",
                (date.today().isoformat(), order["warehouse"], item["product_id"],
                 -float(item["quantity"]), "入库作废", order["order_no"]),
            )
        actor_name = (actor or {}).get("username") or "system"
        conn.execute(
            """UPDATE inbound_orders SET status='已作废',void_reason=?,
                      voided_at=CURRENT_TIMESTAMP,voided_by=? WHERE id=?""",
            (reason, actor_name, int(order_id)),
        )
        after = conn.execute("SELECT * FROM inbound_orders WHERE id=?", (int(order_id),)).fetchone()
        conn.execute(
            "INSERT INTO operation_logs(action,source_no,operator,detail) VALUES(?,?,?,?)",
            ("入库作废", order["order_no"], actor_name, reason),
        )
        write_audit(
            "作废入库单", actor, entity_type="入库单", entity_id=int(order_id),
            source_no=order["order_no"], before=order, after=after, detail=reason, conn=conn,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def void_outbound(order_id: int, reason: str, actor=None) -> None:
    require_permission(actor, "void_outbound")
    reason = str(reason).strip()
    if len(reason) < 3:
        raise ValueError("作废原因至少填写 3 个字")
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        order = conn.execute("SELECT * FROM outbound_orders WHERE id=?", (int(order_id),)).fetchone()
        if not order:
            raise ValueError("出库单不存在")
        if order["status"] not in {"已确认", "已生效"}:
            raise ValueError("只有已生效的出库单可以作废")
        if float(order["settled_amount"]) > 1e-9:
            raise ValueError("该出库单已有结算记录，请先作废关联结算单")
        items = conn.execute(
            "SELECT product_id,SUM(quantity) quantity FROM outbound_items WHERE order_id=? GROUP BY product_id",
            (int(order_id),),
        ).fetchall()
        for item in items:
            conn.execute(
                """INSERT INTO inventory_txns(
                       txn_date,warehouse,product_id,qty,txn_type,source_no
                   ) VALUES(?,?,?,?,?,?)""",
                (date.today().isoformat(), order["warehouse"], item["product_id"],
                 float(item["quantity"]), "出库作废", order["order_no"]),
            )
        actor_name = (actor or {}).get("username") or "system"
        conn.execute(
            """UPDATE outbound_orders SET status='已作废',void_reason=?,
                      voided_at=CURRENT_TIMESTAMP,voided_by=? WHERE id=?""",
            (reason, actor_name, int(order_id)),
        )
        after = conn.execute("SELECT * FROM outbound_orders WHERE id=?", (int(order_id),)).fetchone()
        conn.execute(
            "INSERT INTO operation_logs(action,source_no,operator,detail) VALUES(?,?,?,?)",
            ("出库作废", order["order_no"], actor_name, reason),
        )
        write_audit(
            "作废出库单", actor, entity_type="出库单", entity_id=int(order_id),
            source_no=order["order_no"], before=order, after=after, detail=reason, conn=conn,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def void_settlement(settlement_id: int, reason: str, actor=None) -> None:
    require_permission(actor, "void_settlement")
    reason = str(reason).strip()
    if len(reason) < 3:
        raise ValueError("作废原因至少填写 3 个字")
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        settlement = conn.execute(
            "SELECT * FROM settlements WHERE id=?", (int(settlement_id),)
        ).fetchone()
        if not settlement:
            raise ValueError("结算单不存在")
        if settlement["status"] != "已生效":
            raise ValueError("只有已生效的结算单可以作废")
        allocations = conn.execute(
            "SELECT outbound_order_id,amount FROM settlement_items WHERE settlement_id=?",
            (int(settlement_id),),
        ).fetchall()
        for allocation in allocations:
            row = conn.execute(
                "SELECT settled_amount,status FROM outbound_orders WHERE id=?",
                (allocation["outbound_order_id"],),
            ).fetchone()
            if not row or row["status"] not in {"已确认", "已生效"}:
                raise ValueError("关联出库单状态异常，不能作废结算单")
            if float(row["settled_amount"]) + 1e-9 < float(allocation["amount"]):
                raise ValueError("关联出库单已结算金额异常，不能作废结算单")
            conn.execute(
                "UPDATE outbound_orders SET settled_amount=settled_amount-? WHERE id=?",
                (float(allocation["amount"]), allocation["outbound_order_id"]),
            )
        actor_name = (actor or {}).get("username") or "system"
        conn.execute(
            """UPDATE settlements SET status='已作废',void_reason=?,
                      voided_at=CURRENT_TIMESTAMP,voided_by=? WHERE id=?""",
            (reason, actor_name, int(settlement_id)),
        )
        after = conn.execute("SELECT * FROM settlements WHERE id=?", (int(settlement_id),)).fetchone()
        conn.execute(
            "INSERT INTO operation_logs(action,source_no,operator,detail) VALUES(?,?,?,?)",
            ("结算作废", settlement["settlement_no"], actor_name, reason),
        )
        write_audit(
            "作废结算单", actor, entity_type="结算单", entity_id=int(settlement_id),
            source_no=settlement["settlement_no"], before=settlement, after=after,
            detail=reason, conn=conn,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def inbound_detail(order_id: int):
    conn = get_conn()
    try:
        header = conn.execute("SELECT * FROM inbound_orders WHERE id=?", (int(order_id),)).fetchone()
        items = conn.execute(
            """SELECT p.code product_code,p.name product_name,p.spec,p.unit,
                      i.quantity,i.price,i.amount
               FROM inbound_items i JOIN products p ON p.id=i.product_id
               WHERE i.order_id=? ORDER BY i.id""",
            (int(order_id),),
        ).fetchall()
        return header, items
    finally:
        conn.close()


def outbound_detail(order_id: int):
    conn = get_conn()
    try:
        header = conn.execute(
            """SELECT o.*,c.code customer_code,
                      CASE WHEN o.outbound_type='领料出库'
                           THEN COALESCE(NULLIF(o.material_recipient,''),'未填写')
                           ELSE c.name END customer_name
               FROM outbound_orders o JOIN customers c ON c.id=o.customer_id WHERE o.id=?""",
            (int(order_id),),
        ).fetchone()
        items = conn.execute(
            """SELECT p.code product_code,p.name product_name,p.spec,p.unit,
                      i.quantity,i.price,i.amount
               FROM outbound_items i JOIN products p ON p.id=i.product_id
               WHERE i.order_id=? ORDER BY i.id""",
            (int(order_id),),
        ).fetchall()
        return header, items
    finally:
        conn.close()


def settlement_detail(settlement_id: int):
    conn = get_conn()
    try:
        header = conn.execute(
            """SELECT s.*,c.code customer_code,c.name customer_name
               FROM settlements s JOIN customers c ON c.id=s.customer_id WHERE s.id=?""",
            (int(settlement_id),),
        ).fetchone()
        items = conn.execute(
            """SELECT o.order_no,o.order_date,si.amount
               FROM settlement_items si
               JOIN outbound_orders o ON o.id=si.outbound_order_id
               WHERE si.settlement_id=? ORDER BY si.id""",
            (int(settlement_id),),
        ).fetchall()
        return header, items
    finally:
        conn.close()


def dashboard():
    conn=get_conn()
    today=date.today().isoformat(); month=date.today().strftime("%Y-%m")
    vals={
        "inbound_today": conn.execute("SELECT COUNT(*) FROM inbound_orders WHERE order_date=? AND status IN ('已确认','已生效')",(today,)).fetchone()[0],
        "outbound_today": conn.execute("SELECT COUNT(*) FROM outbound_orders WHERE order_date=? AND status IN ('已确认','已生效')",(today,)).fetchone()[0],
        "settlement_today": conn.execute("SELECT COUNT(*) FROM settlements WHERE settlement_date=? AND status='已生效'",(today,)).fetchone()[0],
        "outbound_today_amount": conn.execute("SELECT COALESCE(SUM(total_amount),0) FROM outbound_orders WHERE order_date=? AND status IN ('已确认','已生效')",(today,)).fetchone()[0],
        "inventory_total": conn.execute("SELECT COALESCE(SUM(qty),0) FROM inventory_txns").fetchone()[0],
        "product_types": conn.execute("SELECT COUNT(*) FROM products WHERE status='启用'").fetchone()[0],
        "receivable": conn.execute("SELECT COALESCE(SUM(total_amount-settled_amount),0) FROM outbound_orders WHERE outbound_type='销售出库' AND status IN ('已确认','已生效')").fetchone()[0],
        "month_new_ar": conn.execute("SELECT COALESCE(SUM(total_amount),0) FROM outbound_orders WHERE outbound_type='销售出库' AND status IN ('已确认','已生效') AND substr(order_date,1,7)=?",(month,)).fetchone()[0],
        "month_settled": conn.execute("SELECT COALESCE(SUM(amount),0) FROM settlements WHERE status='已生效' AND substr(settlement_date,1,7)=?",(month,)).fetchone()[0],
    }
    conn.close(); return vals


def inbound_list(start_date=None, end_date=None, status=None, warehouse=None, keyword=None):
    conditions, params = [], []
    if start_date:
        conditions.append("i.order_date>=?"); params.append(str(start_date))
    if end_date:
        conditions.append("i.order_date<=?"); params.append(str(end_date))
    if status and status != "全部":
        if status == "已生效":
            conditions.append("i.status IN ('已确认','已生效')")
        else:
            conditions.append("i.status=?"); params.append(str(status))
    if warehouse and warehouse != "全部":
        conditions.append("i.warehouse=?"); params.append(str(warehouse))
    if keyword:
        pattern = f"%{str(keyword).strip()}%"
        conditions.append("(i.order_no LIKE ? OR i.supplier LIKE ? OR i.operator LIKE ?)")
        params.extend([pattern, pattern, pattern])
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    conn = get_conn()
    rows = conn.execute(
        """SELECT i.id,i.order_no,i.order_date,i.supplier,i.warehouse,
                  i.total_amount,i.operator,i.status
           FROM inbound_orders i""" + where + " ORDER BY i.id DESC",
        params,
    ).fetchall()
    conn.close()
    return rows


def outbound_list(
    start_date=None, end_date=None, status=None, warehouse=None,
    outbound_type=None, keyword=None,
):
    conditions, params = [], []
    if start_date:
        conditions.append("o.order_date>=?"); params.append(str(start_date))
    if end_date:
        conditions.append("o.order_date<=?"); params.append(str(end_date))
    if status and status != "全部":
        if status == "已生效":
            conditions.append("o.status IN ('已确认','已生效')")
        else:
            conditions.append("o.status=?"); params.append(str(status))
    if warehouse and warehouse != "全部":
        conditions.append("o.warehouse=?"); params.append(str(warehouse))
    if outbound_type and outbound_type != "全部":
        conditions.append("o.outbound_type=?"); params.append(str(outbound_type))
    if keyword:
        pattern = f"%{str(keyword).strip()}%"
        conditions.append(
            "(o.order_no LIKE ? OR c.name LIKE ? OR o.material_recipient LIKE ? OR o.operator LIKE ?)"
        )
        params.extend([pattern, pattern, pattern, pattern])
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    conn = get_conn()
    rows = conn.execute(
        """SELECT o.id,o.order_no,o.order_date,o.outbound_type,
                  CASE WHEN o.outbound_type='领料出库'
                       THEN COALESCE(NULLIF(o.material_recipient,''),'未填写')
                       ELSE c.name END customer_name,
                  o.warehouse,o.total_amount,o.settled_amount,
                  CASE WHEN o.outbound_type='领料出库' THEN 0
                       ELSE o.total_amount-o.settled_amount END outstanding,
                  CASE WHEN o.outbound_type='领料出库' THEN '不参与结算'
                       WHEN o.settled_amount<=0 THEN '未结算'
                       WHEN o.settled_amount<o.total_amount THEN '部分结算'
                       ELSE '已结算' END settlement_status,
                  o.operator,o.status
           FROM outbound_orders o JOIN customers c ON c.id=o.customer_id""" + where +
        " ORDER BY o.id DESC",
        params,
    ).fetchall()
    conn.close()
    return rows


def settlement_list(start_date=None, end_date=None, status=None, customer_id=None, keyword=None):
    conditions, params = [], []
    if start_date:
        conditions.append("s.settlement_date>=?"); params.append(str(start_date))
    if end_date:
        conditions.append("s.settlement_date<=?"); params.append(str(end_date))
    if status and status != "全部":
        conditions.append("s.status=?"); params.append(str(status))
    if customer_id:
        conditions.append("s.customer_id=?"); params.append(int(customer_id))
    if keyword:
        pattern = f"%{str(keyword).strip()}%"
        conditions.append("(s.settlement_no LIKE ? OR c.name LIKE ? OR s.operator LIKE ?)")
        params.extend([pattern, pattern, pattern])
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    conn = get_conn()
    rows = conn.execute(
        """SELECT s.id,s.settlement_no,s.settlement_date,c.name customer_name,s.method,
                  s.amount,s.operator,s.status,s.remark
           FROM settlements s JOIN customers c ON c.id=s.customer_id""" + where +
        " ORDER BY s.id DESC",
        params,
    ).fetchall()
    conn.close()
    return rows
