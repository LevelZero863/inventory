from __future__ import annotations

from datetime import date
from typing import Iterable

from db import get_conn


def next_no(prefix: str) -> str:
    today = date.today().strftime("%Y%m%d")
    conn = get_conn()
    row = conn.execute("SELECT COUNT(*) FROM operation_logs WHERE source_no LIKE ?", (f"{prefix}{today}%",)).fetchone()
    conn.close()
    return f"{prefix}{today}{row[0] + 1:03d}"


def list_products():
    conn = get_conn(); rows = conn.execute("SELECT * FROM products ORDER BY id DESC").fetchall(); conn.close(); return rows


def list_customers():
    conn = get_conn(); rows = conn.execute("SELECT * FROM customers ORDER BY id DESC").fetchall(); conn.close(); return rows


def list_warehouses():
    conn = get_conn(); rows = conn.execute("SELECT name FROM warehouses ORDER BY id").fetchall(); conn.close(); return [r[0] for r in rows]


def add_product(code, name, spec, unit, price, status="启用", remark=""):
    conn = get_conn(); conn.execute("INSERT INTO products(code,name,spec,unit,default_price,status,remark) VALUES(?,?,?,?,?,?,?)", (code,name,spec,unit,price,status,remark)); conn.commit(); conn.close()


def add_customer(code, name, contact, phone, address, method, status="启用", remark=""):
    conn = get_conn(); conn.execute("INSERT INTO customers(code,name,contact,phone,address,settlement_method,status,remark) VALUES(?,?,?,?,?,?,?,?)", (code,name,contact,phone,address,method,status,remark)); conn.commit(); conn.close()


def inventory_rows():
    conn = get_conn()
    rows = conn.execute("""
        SELECT p.code product_code,p.name product_name,p.spec,p.unit,t.warehouse,
               COALESCE(SUM(t.qty),0) current_qty,COALESCE(SUM(t.qty),0) available_qty
        FROM products p LEFT JOIN inventory_txns t ON t.product_id=p.id
        GROUP BY p.id,t.warehouse ORDER BY p.code,t.warehouse
    """).fetchall()
    conn.close(); return rows


def stock(product_id: int, warehouse: str) -> float:
    conn = get_conn(); row = conn.execute("SELECT COALESCE(SUM(qty),0) FROM inventory_txns WHERE product_id=? AND warehouse=?", (product_id, warehouse)).fetchone(); conn.close(); return float(row[0])


def create_inbound(order_date, supplier, warehouse, operator, remark, items: Iterable[dict], confirm=False):
    items = list(items)
    if not items: raise ValueError("至少需要一条入库明细")
    if any(i["quantity"] <= 0 for i in items): raise ValueError("入库数量必须大于0")
    if any(i["price"] < 0 for i in items): raise ValueError("单价不得小于0")
    total = sum(i["quantity"] * i["price"] for i in items)
    no = next_no("RK")
    conn = get_conn()
    try:
        conn.execute("BEGIN")
        cur = conn.execute("INSERT INTO inbound_orders(order_no,order_date,supplier,warehouse,operator,remark,status,total_amount) VALUES(?,?,?,?,?,?,?,?)", (no,order_date,supplier,warehouse,operator,remark,"已确认" if confirm else "草稿",total))
        oid = cur.lastrowid
        for i in items:
            amount=i["quantity"]*i["price"]
            conn.execute("INSERT INTO inbound_items(order_id,product_id,quantity,price,amount) VALUES(?,?,?,?,?)", (oid,i["product_id"],i["quantity"],i["price"],amount))
            if confirm:
                conn.execute("INSERT INTO inventory_txns(txn_date,warehouse,product_id,qty,txn_type,source_no) VALUES(?,?,?,?,?,?)", (order_date,warehouse,i["product_id"],i["quantity"],"入库",no))
        conn.execute("INSERT INTO operation_logs(action,source_no,operator,detail) VALUES(?,?,?,?)", ("确认入库" if confirm else "保存入库草稿",no,operator,""))
        conn.commit()
    except Exception:
        conn.rollback(); raise
    finally: conn.close()
    return no


def create_outbound(order_date, customer_id, warehouse, operator, remark, items: Iterable[dict], confirm=False):
    items = list(items)
    if not items: raise ValueError("至少需要一条出库明细")
    if any(i["quantity"] <= 0 for i in items): raise ValueError("出库数量必须大于0")
    if confirm:
        for i in items:
            if stock(i["product_id"], warehouse) < i["quantity"]:
                raise ValueError(f"产品ID {i['product_id']} 当前库存不足")
    total=sum(i["quantity"]*i["price"] for i in items)
    no=next_no("CK")
    conn=get_conn()
    try:
        conn.execute("BEGIN")
        cur=conn.execute("INSERT INTO outbound_orders(order_no,order_date,customer_id,warehouse,operator,remark,status,total_amount) VALUES(?,?,?,?,?,?,?,?)", (no,order_date,customer_id,warehouse,operator,remark,"已确认" if confirm else "草稿",total))
        oid=cur.lastrowid
        for i in items:
            amount=i["quantity"]*i["price"]
            conn.execute("INSERT INTO outbound_items(order_id,product_id,quantity,price,amount) VALUES(?,?,?,?,?)", (oid,i["product_id"],i["quantity"],i["price"],amount))
            if confirm:
                conn.execute("INSERT INTO inventory_txns(txn_date,warehouse,product_id,qty,txn_type,source_no) VALUES(?,?,?,?,?,?)", (order_date,warehouse,i["product_id"],-i["quantity"],"出库",no))
        conn.execute("INSERT INTO operation_logs(action,source_no,operator,detail) VALUES(?,?,?,?)", ("确认出库" if confirm else "保存出库草稿",no,operator,""))
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
           WHERE o.status='已确认' AND o.total_amount-o.settled_amount>0"""
    params=[]
    if customer_id is not None: sql += " AND o.customer_id=?"; params.append(customer_id)
    sql += " ORDER BY o.order_date,o.id"
    rows=conn.execute(sql,params).fetchall(); conn.close(); return rows


def settle(customer_id, settlement_date, method, operator, remark, allocations: dict[int,float]):
    allocations={int(k):float(v) for k,v in allocations.items() if float(v)>0}
    if not allocations: raise ValueError("至少选择一张出库单并填写结算金额")
    conn=get_conn()
    try:
        conn.execute("BEGIN")
        total=0
        for oid, amount in allocations.items():
            row=conn.execute("SELECT customer_id,total_amount,settled_amount,status FROM outbound_orders WHERE id=?",(oid,)).fetchone()
            if not row: raise ValueError("出库单不存在")
            if row[0] != customer_id: raise ValueError("只能结算当前客户的出库单")
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
        conn.commit()
    except Exception:
        conn.rollback(); raise
    finally: conn.close()
    return no


def dashboard():
    conn=get_conn()
    today=date.today().isoformat(); month=date.today().strftime("%Y-%m")
    vals={
        "inbound_today": conn.execute("SELECT COUNT(*) FROM inbound_orders WHERE order_date=? AND status='已确认'",(today,)).fetchone()[0],
        "outbound_today": conn.execute("SELECT COUNT(*) FROM outbound_orders WHERE order_date=? AND status='已确认'",(today,)).fetchone()[0],
        "settlement_today": conn.execute("SELECT COUNT(*) FROM settlements WHERE settlement_date=?",(today,)).fetchone()[0],
        "outbound_today_amount": conn.execute("SELECT COALESCE(SUM(total_amount),0) FROM outbound_orders WHERE order_date=? AND status='已确认'",(today,)).fetchone()[0],
        "inventory_total": conn.execute("SELECT COALESCE(SUM(qty),0) FROM inventory_txns").fetchone()[0],
        "product_types": conn.execute("SELECT COUNT(*) FROM products WHERE status='启用'").fetchone()[0],
        "receivable": conn.execute("SELECT COALESCE(SUM(total_amount-settled_amount),0) FROM outbound_orders WHERE status='已确认'").fetchone()[0],
        "month_new_ar": conn.execute("SELECT COALESCE(SUM(total_amount),0) FROM outbound_orders WHERE status='已确认' AND substr(order_date,1,7)=?",(month,)).fetchone()[0],
        "month_settled": conn.execute("SELECT COALESCE(SUM(amount),0) FROM settlements WHERE substr(settlement_date,1,7)=?",(month,)).fetchone()[0],
    }
    conn.close(); return vals


def outbound_list():
    conn=get_conn(); rows=conn.execute("""SELECT o.order_no,o.order_date,c.name customer_name,o.total_amount,o.settled_amount,
    o.total_amount-o.settled_amount outstanding,CASE WHEN o.settled_amount<=0 THEN '未结算' WHEN o.settled_amount<o.total_amount THEN '部分结算' ELSE '已结算' END settlement_status,o.status
    FROM outbound_orders o JOIN customers c ON c.id=o.customer_id ORDER BY o.id DESC""").fetchall(); conn.close(); return rows


def inbound_list():
    conn=get_conn(); rows=conn.execute("SELECT order_no,order_date,supplier,warehouse,total_amount,operator,status FROM inbound_orders ORDER BY id DESC").fetchall(); conn.close(); return rows
