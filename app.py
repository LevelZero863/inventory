from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from db import DB_PATH, backup_database, init_db, integrity_check
from services import (
    add_customer,
    add_product,
    create_inbound,
    create_outbound,
    dashboard,
    inbound_list,
    inventory_rows,
    list_customers,
    list_products,
    list_warehouses,
    open_receivables,
    outbound_list,
    receivable_summary,
    settle,
)

st.set_page_config(page_title="库存管理系统", page_icon="📦", layout="wide")
init_db()

INVENTORY_COLUMNS = {
    "product_code": "产品编码",
    "product_name": "产品名称",
    "spec": "规格型号",
    "unit": "单位",
    "warehouse": "仓库",
    "current_qty": "当前库存",
    "available_qty": "可用库存",
}


def rows_df(rows):
    return pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()


def inventory_df():
    return rows_df(inventory_rows()).rename(columns=INVENTORY_COLUMNS)


def product_options():
    products = list_products()
    return products, {f"{p['code']} - {p['name']}": p["id"] for p in products}


def parse_product_items(edited: pd.DataFrame, product_map: dict[str, int]):
    items = []
    for _, row in edited.iterrows():
        label = row.get("产品")
        quantity = row.get("数量")
        price = row.get("单价")
        if (not isinstance(label, str) or not label) and pd.isna(quantity) and pd.isna(price):
            continue
        if label not in product_map:
            raise ValueError("每条明细都必须选择产品")
        if pd.isna(quantity) or float(quantity) <= 0:
            raise ValueError(f"{label} 的数量必须大于 0")
        if pd.isna(price) or float(price) < 0:
            raise ValueError(f"{label} 的单价不得小于 0")
        items.append({"product_id": product_map[label], "quantity": float(quantity), "price": float(price)})
    if not items:
        raise ValueError("至少需要一条有效明细")
    return items


def product_item_editor(products, product_map, key):
    labels = list(product_map)
    first_price = float(products[0]["default_price"]) if products else 0.0
    initial = pd.DataFrame([{"产品": labels[0] if labels else None, "数量": 1.0, "单价": first_price}])
    st.caption("可在表格底部新增明细行，也可删除不需要的行。")
    return st.data_editor(
        initial,
        key=key,
        num_rows="dynamic",
        hide_index=True,
        width="stretch",
        column_config={
            "产品": st.column_config.SelectboxColumn("产品", options=labels, required=True),
            "数量": st.column_config.NumberColumn("数量", min_value=0.01, step=1.0, required=True),
            "单价": st.column_config.NumberColumn("单价", min_value=0.0, step=0.01, format="¥ %.2f", required=True),
        },
    )


@st.dialog("新增入库单", width="large")
def inbound_dialog():
    products, product_map = product_options()
    warehouses = list_warehouses()
    if not product_map or not warehouses:
        st.warning("请先维护产品和仓库资料。")
        return
    c1, c2, c3, c4 = st.columns(4)
    order_date = c1.date_input("入库日期", date.today(), key="inbound_date")
    supplier = c2.text_input("供应商", key="inbound_supplier")
    warehouse = c3.selectbox("仓库", warehouses, key="inbound_warehouse")
    operator = c4.text_input("经办人", "管理员", key="inbound_operator")
    remark = st.text_input("备注", key="inbound_remark")
    st.markdown("#### 入库明细")
    edited = product_item_editor(products, product_map, "inbound_items_editor")
    if st.button("提交并生效", type="primary", key="submit_inbound"):
        try:
            no = create_inbound(order_date.isoformat(), supplier, warehouse, operator, remark, parse_product_items(edited, product_map))
            st.session_state["flash"] = f"入库单 {no} 已提交并生效"
            st.rerun()
        except Exception as exc:
            st.error(str(exc))


@st.dialog("新增出库单", width="large")
def outbound_dialog():
    products, product_map = product_options()
    customers = list_customers()
    warehouses = list_warehouses()
    customer_map = {f"{c['code']} - {c['name']}": c["id"] for c in customers}
    if not product_map or not customer_map or not warehouses:
        st.warning("请先维护产品、客户和仓库资料。")
        return
    c1, c2, c3, c4 = st.columns(4)
    order_date = c1.date_input("出库日期", date.today(), key="outbound_date")
    customer_label = c2.selectbox("客户", list(customer_map), key="outbound_customer")
    warehouse = c3.selectbox("仓库", warehouses, key="outbound_warehouse")
    operator = c4.text_input("经办人", "管理员", key="outbound_operator")
    remark = st.text_input("备注", key="outbound_remark")
    st.markdown("#### 出库明细")
    edited = product_item_editor(products, product_map, "outbound_items_editor")
    if st.button("提交并生效", type="primary", key="submit_outbound"):
        try:
            no = create_outbound(
                order_date.isoformat(), customer_map[customer_label], warehouse, operator, remark,
                parse_product_items(edited, product_map),
            )
            st.session_state["flash"] = f"出库单 {no} 已提交并生效"
            st.rerun()
        except Exception as exc:
            st.error(str(exc))


@st.dialog("新增结算单", width="large")
def settlement_dialog():
    customers = list_customers()
    customer_map = {f"{c['code']} - {c['name']}": c["id"] for c in customers}
    if not customer_map:
        st.warning("请先维护客户资料。")
        return
    customer_label = st.selectbox("客户", list(customer_map), key="settlement_customer")
    customer_id = customer_map[customer_label]
    receivables = open_receivables(customer_id)
    if not receivables:
        st.info("该客户暂无未结算出库单。")
        return
    receivable_map = {f"{r['order_no']}｜未收 ¥{r['outstanding']:,.2f}": r for r in receivables}
    options = list(receivable_map)
    st.markdown("#### 结算明细")
    st.caption("通过表格底部新增多张出库单；每张出库单只能添加一次。")
    edited = st.data_editor(
        pd.DataFrame([{"出库单": options[0], "本次结算金额": 0.0}]),
        key=f"settlement_items_{customer_id}",
        num_rows="dynamic",
        hide_index=True,
        width="stretch",
        column_config={
            "出库单": st.column_config.SelectboxColumn("出库单", options=options, required=True),
            "本次结算金额": st.column_config.NumberColumn(
                "本次结算金额", min_value=0.01, step=0.01, format="¥ %.2f", required=True
            ),
        },
    )
    c1, c2, c3 = st.columns(3)
    settlement_date = c1.date_input("结算日期", date.today(), key="settlement_date")
    method = c2.selectbox("结算方式", ["银行转账", "现金", "其他"], key="settlement_method")
    operator = c3.text_input("经办人", "管理员", key="settlement_operator")
    remark = st.text_input("备注", key="settlement_remark")
    if st.button("提交并生效", type="primary", key="submit_settlement"):
        try:
            allocations = {}
            for _, row in edited.iterrows():
                order_label = row.get("出库单")
                amount = row.get("本次结算金额")
                if (not isinstance(order_label, str) or not order_label) and pd.isna(amount):
                    continue
                if order_label not in receivable_map:
                    raise ValueError("每条结算明细都必须选择出库单")
                if pd.isna(amount) or float(amount) <= 0:
                    raise ValueError(f"{order_label} 的结算金额必须大于 0")
                receivable = receivable_map[order_label]
                order_id = int(receivable["id"])
                if order_id in allocations:
                    raise ValueError("同一张出库单不能重复添加")
                if float(amount) > float(receivable["outstanding"]):
                    raise ValueError(f"{order_label} 的结算金额超过未收金额")
                allocations[order_id] = float(amount)
            no = settle(customer_id, settlement_date.isoformat(), method, operator, remark, allocations)
            st.session_state["flash"] = f"结算单 {no} 已提交并生效"
            st.rerun()
        except Exception as exc:
            st.error(str(exc))


st.title("📦 库存管理系统")
st.caption("AI 安全迭代版 V1.1 · Streamlit + SQLite + Migration")
if message := st.session_state.pop("flash", None):
    st.success(message)

with st.sidebar.expander("🛡️ 数据安全", expanded=False):
    st.caption(f"数据库：{DB_PATH.name}")
    if st.button("立即备份数据库"):
        try:
            path = backup_database(label="manual")
            st.success(f"备份完成：{path.name}")
        except Exception as exc:
            st.error(str(exc))
    st.write("完整性检查：", integrity_check())

menu = st.sidebar.radio("功能菜单", ["首页", "基础资料", "入库管理", "出库管理", "结算管理", "应收账款", "库存查询"])

if menu == "首页":
    data = dashboard()
    cols = st.columns(4)
    cols[0].metric("今日入库单", data["inbound_today"])
    cols[1].metric("今日出库单", data["outbound_today"])
    cols[2].metric("今日结算单", data["settlement_today"])
    cols[3].metric("当前应收", f"¥{data['receivable']:,.2f}")
    st.subheader("经营概览")
    cols = st.columns(4)
    cols[0].metric("产品种类", data["product_types"])
    cols[1].metric("当前库存总量", f"{data['inventory_total']:,.0f}")
    cols[2].metric("本月新增应收", f"¥{data['month_new_ar']:,.2f}")
    cols[3].metric("本月已结算", f"¥{data['month_settled']:,.2f}")
    st.subheader("当前库存")
    st.dataframe(inventory_df(), width="stretch", hide_index=True)

elif menu == "基础资料":
    tab1, tab2 = st.tabs(["产品管理", "客户管理"])
    with tab1:
        with st.expander("新增产品", expanded=True):
            with st.form("product"):
                c1, c2, c3, c4 = st.columns(4)
                code = c1.text_input("产品编码")
                name = c2.text_input("产品名称")
                spec = c3.text_input("规格型号")
                unit = c4.text_input("单位", "件")
                price = st.number_input("默认单价", min_value=0.0, step=0.01)
                if st.form_submit_button("保存产品"):
                    try:
                        add_product(code, name, spec, unit, price)
                        st.success("保存成功")
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))
        st.dataframe(rows_df(list_products()), width="stretch", hide_index=True)
    with tab2:
        with st.expander("新增客户", expanded=True):
            with st.form("customer"):
                c1, c2, c3, c4 = st.columns(4)
                code = c1.text_input("客户编码")
                name = c2.text_input("客户名称")
                contact = c3.text_input("联系人")
                phone = c4.text_input("联系电话")
                address = st.text_input("地址")
                method = st.selectbox("结算方式", ["现结", "月结"])
                if st.form_submit_button("保存客户"):
                    try:
                        add_customer(code, name, contact, phone, address, method)
                        st.success("保存成功")
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))
        st.dataframe(rows_df(list_customers()), width="stretch", hide_index=True)

elif menu == "入库管理":
    c1, _ = st.columns([1, 5])
    if c1.button("＋ 新增入库单", type="primary", width="stretch"):
        inbound_dialog()
    st.subheader("入库单列表")
    st.dataframe(rows_df(inbound_list()), width="stretch", hide_index=True)

elif menu == "出库管理":
    c1, _ = st.columns([1, 5])
    if c1.button("＋ 新增出库单", type="primary", width="stretch"):
        outbound_dialog()
    st.subheader("出库单列表")
    st.dataframe(rows_df(outbound_list()), width="stretch", hide_index=True)

elif menu == "结算管理":
    c1, _ = st.columns([1, 5])
    if c1.button("＋ 新增结算单", type="primary", width="stretch"):
        settlement_dialog()
    st.subheader("待结算客户")
    summary = rows_df(receivable_summary())
    if summary.empty:
        st.info("当前没有待结算应收账款。")
    else:
        st.dataframe(
            summary.rename(columns={
                "customer_code": "客户编码", "customer_name": "客户名称", "order_count": "待结算单数",
                "total_amount": "出库金额", "settled_amount": "已结算金额", "outstanding": "未收金额",
            }).drop(columns=["customer_id"]),
            width="stretch",
            hide_index=True,
        )

elif menu == "应收账款":
    st.subheader("客户应收汇总")
    summary = rows_df(receivable_summary())
    if summary.empty:
        st.info("当前没有未收账款。")
    else:
        display_summary = summary.rename(columns={
            "customer_code": "客户编码", "customer_name": "客户名称", "order_count": "未结算单数",
            "total_amount": "出库金额", "settled_amount": "已收金额", "outstanding": "未收金额",
        }).drop(columns=["customer_id"])
        st.metric("应收账款合计", f"¥{float(summary['outstanding'].sum()):,.2f}")
        st.caption("点击某一客户所在行，可在下方查看该客户的应收明细。")
        event = st.dataframe(
            display_summary,
            key="receivable_customer_summary",
            on_select="rerun",
            selection_mode="single-row",
            width="stretch",
            hide_index=True,
        )
        selected_rows = event.selection.rows
        if selected_rows:
            selected = summary.iloc[selected_rows[0]]
            st.subheader(f"{selected['customer_name']}｜应收明细")
            details = rows_df(open_receivables(int(selected["customer_id"]))).rename(columns={
                "order_no": "出库单号", "order_date": "出库日期", "customer_name": "客户名称",
                "total_amount": "出库金额", "settled_amount": "已收金额", "outstanding": "未收金额",
                "settlement_status": "结算状态",
            })
            if "id" in details.columns:
                details = details.drop(columns=["id"])
            st.dataframe(details, width="stretch", hide_index=True)

elif menu == "库存查询":
    st.subheader("当前在库产品明细")
    st.dataframe(inventory_df(), width="stretch", hide_index=True)
