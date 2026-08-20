from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from auth import (
    INITIAL_ADMIN_PASSWORD,
    INITIAL_ADMIN_USERNAME,
    authenticate,
    change_password,
    ensure_initial_admin,
)
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
    settlement_list,
    update_customer,
    update_product,
)

st.set_page_config(page_title="库存管理系统", page_icon="📦", layout="wide")
init_db()
initial_admin_created = ensure_initial_admin()


def render_login():
    st.title("🔐 库存管理系统登录")
    st.caption("请输入账号和密码后进入系统。")
    with st.form("login_form"):
        username = st.text_input("账号")
        password = st.text_input("密码", type="password")
        submitted = st.form_submit_button("登录", type="primary", width="stretch")
    if submitted:
        user = authenticate(username, password)
        if user:
            st.session_state["auth_user"] = user
            st.rerun()
        else:
            st.error("账号或密码错误")
    if initial_admin_created:
        st.info(
            f"首次登录账号：{INITIAL_ADMIN_USERNAME}，初始密码：{INITIAL_ADMIN_PASSWORD}。"
            "登录后必须立即修改密码。"
        )


def render_forced_password_change(user):
    st.title("🔑 首次登录：修改密码")
    st.warning("为保障数据安全，请先设置新的登录密码。")
    with st.form("forced_password_change"):
        new_password = st.text_input("新密码（至少 8 位）", type="password")
        confirm_password = st.text_input("确认新密码", type="password")
        submitted = st.form_submit_button("保存新密码", type="primary", width="stretch")
    if submitted:
        if new_password != confirm_password:
            st.error("两次输入的密码不一致")
        else:
            try:
                change_password(int(user["id"]), new_password)
                user["must_change_password"] = False
                st.session_state["auth_user"] = user
                st.success("密码修改成功")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))


if "auth_user" not in st.session_state:
    render_login()
    st.stop()

if st.session_state["auth_user"].get("must_change_password"):
    render_forced_password_change(st.session_state["auth_user"])
    st.stop()

INVENTORY_COLUMNS = {
    "product_code": "产品编码",
    "product_name": "产品名称",
    "spec": "规格型号",
    "unit": "单位",
    "warehouse": "仓库",
    "current_qty": "当前库存",
    "available_qty": "可用库存",
}

INBOUND_COLUMNS = {
    "order_no": "入库单号",
    "order_date": "入库日期",
    "supplier": "供应商",
    "warehouse": "仓库",
    "total_amount": "入库总金额",
    "operator": "经办人",
    "status": "单据状态",
}

OUTBOUND_COLUMNS = {
    "order_no": "出库单号",
    "order_date": "出库日期",
    "customer_name": "客户名称",
    "total_amount": "出库总金额",
    "settled_amount": "已结算金额",
    "outstanding": "未收金额",
    "settlement_status": "结算状态",
    "status": "单据状态",
}

SETTLEMENT_COLUMNS = {
    "settlement_no": "结算单号",
    "settlement_date": "结算日期",
    "customer_name": "客户名称",
    "method": "结算方式",
    "amount": "结算金额",
    "operator": "经办人",
    "remark": "备注",
}


def rows_df(rows):
    return pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()


def inventory_df():
    return rows_df(inventory_rows()).rename(columns=INVENTORY_COLUMNS)


def product_options():
    products = list_products(active_only=True)
    return products, {f"{p['code']} - {p['name']}": p["id"] for p in products}


def product_master_df():
    return pd.DataFrame([
        {
            "产品ID": product["id"],
            "产品编码": product["code"],
            "产品名称": product["name"],
            "规格型号": product["spec"] or "",
            "单位": product["unit"],
            "默认单价": float(product["default_price"]),
            "状态": product["status"],
            "备注": product["remark"] or "",
        }
        for product in list_products()
    ])


def customer_master_df():
    return pd.DataFrame([
        {
            "客户ID": customer["id"],
            "客户编码": customer["code"],
            "客户名称": customer["name"],
            "联系人": customer["contact"] or "",
            "联系电话": customer["phone"] or "",
            "地址": customer["address"] or "",
            "结算方式": customer["settlement_method"],
            "状态": customer["status"],
            "备注": customer["remark"] or "",
        }
        for customer in list_customers()
    ])


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


def current_operator():
    user = st.session_state["auth_user"]
    return user.get("display_name") or user.get("username") or "管理员"


def _set_line_default_price(prefix, line_id, price_map):
    product_label = st.session_state.get(f"{prefix}_product_{line_id}")
    if product_label in price_map:
        st.session_state[f"{prefix}_price_{line_id}"] = float(price_map[product_label])


def _new_line(prefix, labels, price_map):
    counter_key = f"{prefix}_line_counter"
    line_id = int(st.session_state.get(counter_key, 0))
    st.session_state[counter_key] = line_id + 1
    line_ids = list(st.session_state.get(f"{prefix}_line_ids", []))
    line_ids.append(line_id)
    st.session_state[f"{prefix}_line_ids"] = line_ids
    first_label = labels[0]
    st.session_state[f"{prefix}_product_{line_id}"] = first_label
    st.session_state[f"{prefix}_quantity_{line_id}"] = 1.0
    st.session_state[f"{prefix}_price_{line_id}"] = float(price_map[first_label])


def _remove_line(prefix, line_id):
    line_ids = list(st.session_state.get(f"{prefix}_line_ids", []))
    st.session_state[f"{prefix}_line_ids"] = [item for item in line_ids if item != line_id]


def _clear_lines(prefix):
    st.session_state.pop(f"{prefix}_line_ids", None)


def product_item_editor(products, product_map, prefix):
    labels = list(product_map)
    price_map = {
        f"{product['code']} - {product['name']}": float(product["default_price"])
        for product in products
    }
    if not st.session_state.get(f"{prefix}_line_ids"):
        _new_line(prefix, labels, price_map)

    st.caption("选择产品后自动带出默认单价；单价仍可按本次业务手工调整。")
    header = st.columns([4, 1.4, 1.7, 1.7, 0.8])
    for column, title in zip(header, ["产品", "数量", "单价", "金额", "操作"]):
        column.markdown(f"**{title}**")

    rows = []
    line_ids = list(st.session_state[f"{prefix}_line_ids"])
    for line_id in line_ids:
        product_key = f"{prefix}_product_{line_id}"
        quantity_key = f"{prefix}_quantity_{line_id}"
        price_key = f"{prefix}_price_{line_id}"
        if st.session_state.get(product_key) not in labels:
            st.session_state[product_key] = labels[0]
            st.session_state[price_key] = float(price_map[labels[0]])
        columns = st.columns([4, 1.4, 1.7, 1.7, 0.8])
        label = columns[0].selectbox(
            "产品",
            labels,
            key=product_key,
            label_visibility="collapsed",
            on_change=_set_line_default_price,
            args=(prefix, line_id, price_map),
        )
        quantity = columns[1].number_input(
            "数量", min_value=0.01, step=1.0, key=quantity_key, label_visibility="collapsed"
        )
        price = columns[2].number_input(
            "单价", min_value=0.0, step=0.01, key=price_key, label_visibility="collapsed"
        )
        amount = float(quantity) * float(price)
        columns[3].markdown(f"¥{amount:,.2f}")
        columns[4].button(
            "删除",
            key=f"{prefix}_delete_{line_id}",
            disabled=len(line_ids) == 1,
            width="stretch",
            on_click=_remove_line,
            args=(prefix, line_id),
        )
        rows.append({"产品": label, "数量": float(quantity), "单价": float(price)})

    st.button(
        "＋ 新增明细行",
        key=f"{prefix}_add_line",
        width="content",
        on_click=_new_line,
        args=(prefix, labels, price_map),
    )
    return pd.DataFrame(rows)


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
    operator = c4.text_input("经办人", current_operator(), key="inbound_operator")
    remark = st.text_input("备注", key="inbound_remark")
    st.markdown("#### 入库明细")
    edited = product_item_editor(products, product_map, "inbound_items")
    inbound_total = float((edited["数量"] * edited["单价"]).sum())
    st.metric("入库单总金额", f"¥{inbound_total:,.2f}")
    if st.button("提交并生效", type="primary", key="submit_inbound"):
        try:
            no = create_inbound(order_date.isoformat(), supplier, warehouse, operator, remark, parse_product_items(edited, product_map))
            _clear_lines("inbound_items")
            st.session_state["flash"] = f"入库单 {no} 已提交并生效"
            st.rerun()
        except Exception as exc:
            st.error(str(exc))


@st.dialog("新增出库单", width="large")
def outbound_dialog():
    products, product_map = product_options()
    customers = list_customers(active_only=True)
    warehouses = list_warehouses()
    customer_map = {f"{c['code']} - {c['name']}": c["id"] for c in customers}
    if not product_map or not customer_map or not warehouses:
        st.warning("请先维护产品、客户和仓库资料。")
        return
    c1, c2, c3, c4 = st.columns(4)
    order_date = c1.date_input("出库日期", date.today(), key="outbound_date")
    customer_label = c2.selectbox("客户", list(customer_map), key="outbound_customer")
    warehouse = c3.selectbox("仓库", warehouses, key="outbound_warehouse")
    operator = c4.text_input("经办人", current_operator(), key="outbound_operator")
    remark = st.text_input("备注", key="outbound_remark")
    st.markdown("#### 出库明细")
    edited = product_item_editor(products, product_map, "outbound_items")
    quantities = pd.to_numeric(edited.get("数量"), errors="coerce").fillna(0)
    prices = pd.to_numeric(edited.get("单价"), errors="coerce").fillna(0)
    total_amount = float((quantities * prices).sum())
    st.metric("出库单总金额", f"¥{total_amount:,.2f}")
    if st.button("提交并生效", type="primary", key="submit_outbound"):
        try:
            no = create_outbound(
                order_date.isoformat(), customer_map[customer_label], warehouse, operator, remark,
                parse_product_items(edited, product_map),
            )
            _clear_lines("outbound_items")
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
    operator = c3.text_input("经办人", current_operator(), key="settlement_operator")
    remark = st.text_input("备注", key="settlement_remark")
    settlement_total = pd.to_numeric(edited["本次结算金额"], errors="coerce").fillna(0).sum()
    st.metric("本次结算总金额", f"¥{float(settlement_total):,.2f}")
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
st.caption("AI 安全迭代版 V1.3 · Streamlit + SQLite + Migration")
if message := st.session_state.pop("flash", None):
    st.success(message)

user = st.session_state["auth_user"]
st.sidebar.write(f"👤 {user['display_name'] or user['username']}")
if st.sidebar.button("退出登录", width="stretch"):
    st.session_state.pop("auth_user", None)
    st.rerun()

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
    home_inventory = inventory_df()
    if home_inventory.empty:
        st.info("暂无库存数据。")
    else:
        st.dataframe(home_inventory, width="stretch", hide_index=True)

elif menu == "基础资料":
    tab1, tab2 = st.tabs(["产品管理", "客户管理"])
    with tab1:
        with st.expander("新增产品", expanded=False):
            with st.form("product"):
                c1, c2, c3, c4 = st.columns(4)
                code = c1.text_input("产品编码")
                name = c2.text_input("产品名称")
                spec = c3.text_input("规格型号")
                unit = c4.text_input("单位", "件")
                c5, c6 = st.columns([1, 3])
                price = c5.number_input("默认单价", min_value=0.0, step=0.01)
                status = c5.selectbox("状态", ["启用", "停用"])
                remark = c6.text_input("备注")
                if st.form_submit_button("保存产品"):
                    try:
                        add_product(code, name, spec, unit, price, status, remark)
                        st.success("保存成功")
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))
        st.subheader("产品列表")
        st.caption("可以直接修改产品信息和状态；停用产品不会再出现在新建入库单、出库单中。")
        products_edited = st.data_editor(
            product_master_df(),
            key="product_master_editor",
            hide_index=True,
            num_rows="fixed",
            width="stretch",
            column_config={
                "产品ID": None,
                "产品编码": st.column_config.TextColumn("产品编码", required=True),
                "产品名称": st.column_config.TextColumn("产品名称", required=True),
                "规格型号": st.column_config.TextColumn("规格型号"),
                "单位": st.column_config.TextColumn("单位", required=True),
                "默认单价": st.column_config.NumberColumn(
                    "默认单价", min_value=0.0, step=0.01, format="¥ %.2f", required=True
                ),
                "状态": st.column_config.SelectboxColumn(
                    "状态", options=["启用", "停用"], required=True
                ),
                "备注": st.column_config.TextColumn("备注"),
            },
        )
        if st.button("保存产品修改", type="primary"):
            try:
                for _, product in products_edited.iterrows():
                    update_product(
                        product["产品ID"], product["产品编码"], product["产品名称"],
                        product["规格型号"], product["单位"], product["默认单价"],
                        product["状态"], product["备注"],
                    )
                st.session_state["flash"] = "产品资料已更新"
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
    with tab2:
        with st.expander("新增客户", expanded=False):
            with st.form("customer"):
                c1, c2, c3, c4 = st.columns(4)
                code = c1.text_input("客户编码")
                name = c2.text_input("客户名称")
                contact = c3.text_input("联系人")
                phone = c4.text_input("联系电话")
                address = st.text_input("地址")
                c5, c6 = st.columns([1, 3])
                method = c5.selectbox("结算方式", ["现结", "月结"])
                status = c5.selectbox("状态", ["启用", "停用"])
                remark = c6.text_input("备注")
                if st.form_submit_button("保存客户"):
                    try:
                        add_customer(code, name, contact, phone, address, method, status, remark)
                        st.success("保存成功")
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))
        st.subheader("客户列表")
        st.caption("可以直接修改客户信息和状态；停用客户不能再新建出库单，但历史应收仍可结算。")
        customers_edited = st.data_editor(
            customer_master_df(),
            key="customer_master_editor",
            hide_index=True,
            num_rows="fixed",
            width="stretch",
            column_config={
                "客户ID": None,
                "客户编码": st.column_config.TextColumn("客户编码", required=True),
                "客户名称": st.column_config.TextColumn("客户名称", required=True),
                "联系人": st.column_config.TextColumn("联系人"),
                "联系电话": st.column_config.TextColumn("联系电话"),
                "地址": st.column_config.TextColumn("地址"),
                "结算方式": st.column_config.SelectboxColumn(
                    "结算方式", options=["现结", "月结"], required=True
                ),
                "状态": st.column_config.SelectboxColumn(
                    "状态", options=["启用", "停用"], required=True
                ),
                "备注": st.column_config.TextColumn("备注"),
            },
        )
        if st.button("保存客户修改", type="primary"):
            try:
                for _, customer in customers_edited.iterrows():
                    update_customer(
                        customer["客户ID"], customer["客户编码"], customer["客户名称"],
                        customer["联系人"], customer["联系电话"], customer["地址"],
                        customer["结算方式"], customer["状态"], customer["备注"],
                    )
                st.session_state["flash"] = "客户资料已更新"
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

elif menu == "入库管理":
    c1, _ = st.columns([1, 5])
    if c1.button("＋ 新增入库单", type="primary", width="stretch"):
        inbound_dialog()
    st.subheader("入库单列表")
    inbound_df = rows_df(inbound_list()).rename(columns=INBOUND_COLUMNS)
    if inbound_df.empty:
        st.info("暂无入库单。")
    else:
        st.dataframe(
            inbound_df,
            width="stretch",
            hide_index=True,
            column_config={
                "入库总金额": st.column_config.NumberColumn("入库总金额", format="¥ %.2f")
            },
        )

elif menu == "出库管理":
    c1, _ = st.columns([1, 5])
    if c1.button("＋ 新增出库单", type="primary", width="stretch"):
        outbound_dialog()
    st.subheader("出库单列表")
    outbound_df = rows_df(outbound_list()).rename(columns=OUTBOUND_COLUMNS)
    if outbound_df.empty:
        st.info("暂无出库单。")
    else:
        st.dataframe(
            outbound_df,
            width="stretch",
            hide_index=True,
            column_config={
                "出库总金额": st.column_config.NumberColumn("出库总金额", format="¥ %.2f"),
                "已结算金额": st.column_config.NumberColumn("已结算金额", format="¥ %.2f"),
                "未收金额": st.column_config.NumberColumn("未收金额", format="¥ %.2f"),
            },
        )

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
            column_config={
                "出库金额": st.column_config.NumberColumn("出库金额", format="¥ %.2f"),
                "已结算金额": st.column_config.NumberColumn("已结算金额", format="¥ %.2f"),
                "未收金额": st.column_config.NumberColumn("未收金额", format="¥ %.2f"),
            },
        )
    st.subheader("结算单列表")
    settlements_df = rows_df(settlement_list()).rename(columns=SETTLEMENT_COLUMNS)
    if settlements_df.empty:
        st.info("暂无结算单。")
    else:
        st.dataframe(
            settlements_df,
            width="stretch",
            hide_index=True,
            column_config={
                "结算金额": st.column_config.NumberColumn("结算金额", format="¥ %.2f")
            },
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
            column_config={
                "出库金额": st.column_config.NumberColumn("出库金额", format="¥ %.2f"),
                "已收金额": st.column_config.NumberColumn("已收金额", format="¥ %.2f"),
                "未收金额": st.column_config.NumberColumn("未收金额", format="¥ %.2f"),
            },
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
            st.dataframe(
                details,
                width="stretch",
                hide_index=True,
                column_config={
                    "出库金额": st.column_config.NumberColumn("出库金额", format="¥ %.2f"),
                    "已收金额": st.column_config.NumberColumn("已收金额", format="¥ %.2f"),
                    "未收金额": st.column_config.NumberColumn("未收金额", format="¥ %.2f"),
                },
            )

elif menu == "库存查询":
    st.subheader("当前在库产品明细")
    current_inventory = inventory_df()
    if current_inventory.empty:
        st.info("暂无库存数据。")
    else:
        st.dataframe(current_inventory, width="stretch", hide_index=True)
