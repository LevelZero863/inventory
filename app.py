from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from audit import list_audit_logs, write_audit
from auth import (
    INITIAL_ADMIN_PASSWORD,
    INITIAL_ADMIN_USERNAME,
    authenticate,
    change_password,
    create_user,
    ensure_initial_admin,
    get_active_user,
    list_users,
    reset_user_password,
    update_user,
)
from db import DB_PATH, backup_database, init_db, integrity_check
from pdf_exports import inbound_pdf, outbound_pdf, settlement_pdf
from permissions import ROLE_LABELS, has_permission
from services import (
    add_customer,
    add_product,
    create_inbound,
    create_outbound,
    dashboard,
    inbound_detail,
    inbound_list,
    inventory_rows,
    list_customers,
    list_products,
    list_warehouses,
    open_receivables,
    outbound_detail,
    outbound_list,
    receivable_summary,
    settle,
    settlement_detail,
    settlement_list,
    update_customer,
    update_product,
    void_inbound,
    void_outbound,
    void_settlement,
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
                change_password(int(user["id"]), new_password, actor=user)
                user["must_change_password"] = False
                st.session_state["auth_user"] = user
                st.success("密码修改成功")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))


if "auth_user" not in st.session_state:
    render_login()
    st.stop()

fresh_user = get_active_user(int(st.session_state["auth_user"]["id"]))
if not fresh_user:
    st.session_state.pop("auth_user", None)
    st.warning("账号已停用，请联系管理员。")
    render_login()
    st.stop()
st.session_state["auth_user"] = fresh_user

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
    "id": "单据ID",
    "order_no": "入库单号",
    "order_date": "入库日期",
    "supplier": "供应商",
    "warehouse": "仓库",
    "total_amount": "入库总金额",
    "operator": "经办人",
    "status": "单据状态",
}

OUTBOUND_COLUMNS = {
    "id": "单据ID",
    "order_no": "出库单号",
    "order_date": "出库日期",
    "outbound_type": "出库类型",
    "customer_name": "客户/领料人",
    "warehouse": "仓库",
    "total_amount": "出库总金额",
    "settled_amount": "已结算金额",
    "outstanding": "未收金额",
    "settlement_status": "结算状态",
    "operator": "经办人",
    "status": "单据状态",
}

SETTLEMENT_COLUMNS = {
    "id": "单据ID",
    "settlement_no": "结算单号",
    "settlement_date": "结算日期",
    "customer_name": "客户名称",
    "method": "结算方式",
    "amount": "结算金额",
    "operator": "经办人",
    "status": "单据状态",
    "remark": "备注",
}


def rows_df(rows):
    return pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()


def inventory_df():
    return rows_df(inventory_rows()).rename(columns=INVENTORY_COLUMNS)


def date_filter(prefix: str, label="按日期筛选"):
    enabled = st.checkbox(label, key=f"{prefix}_date_enabled")
    if not enabled:
        return None, None
    c1, c2 = st.columns(2)
    start = c1.date_input("开始日期", date.today().replace(day=1), key=f"{prefix}_start")
    end = c2.date_input("结束日期", date.today(), key=f"{prefix}_end")
    if start > end:
        st.error("开始日期不能晚于结束日期")
        return "9999-12-31", "0001-01-01"
    return start.isoformat(), end.isoformat()


def audit_pdf_export(entity_type, entity_id, source_no):
    write_audit(
        "导出PDF", st.session_state.get("auth_user"), entity_type=entity_type,
        entity_id=int(entity_id), source_no=source_no,
    )


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
            no = create_inbound(
                order_date.isoformat(), supplier, warehouse, operator, remark,
                parse_product_items(edited, product_map), actor=st.session_state["auth_user"],
            )
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
    if not product_map or not warehouses:
        st.warning("请先维护产品和仓库资料。")
        return
    outbound_type = st.radio(
        "出库类型", ["销售出库", "领料出库"], horizontal=True, key="outbound_type",
        help="领料出库用于内部领用或非正常销售出库，不产生应收账款。",
    )
    if outbound_type == "销售出库" and not customer_map:
        st.warning("销售出库前请先维护至少一个启用客户。")
        return
    c1, c2, c3, c4 = st.columns(4)
    order_date = c1.date_input("出库日期", date.today(), key="outbound_date")
    if outbound_type == "销售出库":
        customer_label = c2.selectbox("客户", list(customer_map), key="outbound_customer")
        customer_id = customer_map[customer_label]
        material_recipient = ""
    else:
        material_recipient = c2.text_input(
            "领料人/部门（选填）", key="outbound_material_recipient"
        )
        customer_id = None
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
                order_date.isoformat(), customer_id, warehouse, operator, remark,
                parse_product_items(edited, product_map), actor=st.session_state["auth_user"],
                outbound_type=outbound_type, material_recipient=material_recipient,
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
            no = settle(
                customer_id, settlement_date.isoformat(), method, operator, remark, allocations,
                actor=st.session_state["auth_user"],
            )
            st.session_state["flash"] = f"结算单 {no} 已提交并生效"
            st.rerun()
        except Exception as exc:
            st.error(str(exc))


def render_void_form(label, entity_id, status, permission, handler, actor, key):
    if status not in {"已确认", "已生效"} or not has_permission(actor, permission):
        return
    with st.form(f"void_{key}_{entity_id}"):
        st.markdown(f"#### 作废{label}")
        reason = st.text_input("作废原因（必填，至少 3 个字）")
        confirmed = st.checkbox("我确认该操作将生成反向业务记录，原单据和审计记录会永久保留")
        submitted = st.form_submit_button(f"确认作废{label}", type="primary")
        if submitted:
            if not confirmed:
                st.error("请先勾选确认项")
            else:
                try:
                    handler(int(entity_id), reason, actor=actor)
                    st.session_state["flash"] = f"{label}已作废，反向业务记录已生成"
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))


def detail_items_df(items):
    return rows_df(items).rename(columns={
        "product_code": "产品编码", "product_name": "产品名称", "spec": "规格型号",
        "unit": "单位", "quantity": "数量", "price": "单价", "amount": "金额",
        "order_no": "出库单号", "order_date": "出库日期",
    })


st.title("📦 库存管理系统")
st.caption("AI 安全迭代版 V1.5 · 单据打印/PDF + 多字段筛选 + 领料出库")
if message := st.session_state.pop("flash", None):
    st.success(message)

user = st.session_state["auth_user"]
st.sidebar.write(f"👤 {user['display_name'] or user['username']}")
st.sidebar.caption(f"角色：{ROLE_LABELS.get(user['role'], user['role'])}")
if st.sidebar.button("退出登录", width="stretch"):
    write_audit("退出登录", user, entity_type="用户", entity_id=user["id"], source_no=user["username"])
    st.session_state.pop("auth_user", None)
    st.rerun()

with st.sidebar.expander("🛡️ 数据安全", expanded=False):
    st.caption(f"数据库：{DB_PATH.name}")
    if has_permission(user, "backup_database") and st.button("立即备份数据库"):
        try:
            path = backup_database(label="manual")
            write_audit("手工备份数据库", user, entity_type="系统", source_no=path.name)
            st.success(f"备份完成：{path.name}")
        except Exception as exc:
            st.error(str(exc))
    st.write("完整性检查：", integrity_check())

menu_options = ["首页"]
if has_permission(user, "manage_master"):
    menu_options.append("基础资料")
menu_options.extend(["入库管理", "出库管理", "结算管理", "应收账款", "库存查询"])
if has_permission(user, "manage_users"):
    menu_options.append("用户与权限")
if has_permission(user, "view_audit"):
    menu_options.append("审计日志")
menu = st.sidebar.radio("功能菜单", menu_options)

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
                        add_product(code, name, spec, unit, price, status, remark, actor=user)
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
                        product["状态"], product["备注"], actor=user,
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
                        add_customer(
                            code, name, contact, phone, address, method, status, remark, actor=user
                        )
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
                        customer["结算方式"], customer["状态"], customer["备注"], actor=user,
                    )
                st.session_state["flash"] = "客户资料已更新"
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

elif menu == "入库管理":
    c1, _ = st.columns([1, 5])
    if has_permission(user, "create_inbound") and c1.button(
        "＋ 新增入库单", type="primary", width="stretch"
    ):
        inbound_dialog()
    elif not has_permission(user, "create_inbound"):
        st.caption("当前角色可查看入库单，但无权新增或作废。")
    st.subheader("入库单列表")
    with st.expander("筛选条件", expanded=False):
        inbound_start, inbound_end = date_filter("inbound_filter", "按入库日期筛选")
        f1, f2, f3 = st.columns(3)
        inbound_warehouse = f1.selectbox(
            "仓库", ["全部"] + list_warehouses(), key="inbound_filter_warehouse"
        )
        inbound_status = f2.selectbox(
            "单据状态", ["全部", "已生效", "已作废"], key="inbound_filter_status"
        )
        inbound_keyword = f3.text_input(
            "关键词", placeholder="单号、供应商或经办人", key="inbound_filter_keyword"
        )
    inbound_df = rows_df(inbound_list(
        inbound_start, inbound_end, inbound_status, inbound_warehouse, inbound_keyword
    )).rename(columns=INBOUND_COLUMNS)
    if inbound_df.empty:
        st.info("暂无入库单。")
    else:
        event = st.dataframe(
            inbound_df,
            key="inbound_order_list",
            on_select="rerun",
            selection_mode="single-row",
            width="stretch",
            hide_index=True,
            column_config={
                "单据ID": None,
                "入库总金额": st.column_config.NumberColumn("入库总金额", format="¥ %.2f")
            },
        )
        if event.selection.rows:
            selected = inbound_df.iloc[event.selection.rows[0]]
            header, items = inbound_detail(int(selected["单据ID"]))
            st.subheader(f"{header['order_no']}｜入库明细")
            st.caption(
                f"日期：{header['order_date']}　供应商：{header['supplier'] or '-'}　"
                f"仓库：{header['warehouse']}　状态：{header['status']}"
            )
            st.dataframe(
                detail_items_df(items), width="stretch", hide_index=True,
                column_config={
                    "单价": st.column_config.NumberColumn("单价", format="¥ %.2f"),
                    "金额": st.column_config.NumberColumn("金额", format="¥ %.2f"),
                },
            )
            st.download_button(
                "下载/打印 PDF", data=inbound_pdf(header, items),
                file_name=f"{header['order_no']}_入库单.pdf", mime="application/pdf",
                key=f"inbound_pdf_{header['id']}",
                on_click=audit_pdf_export,
                args=("入库单", header["id"], header["order_no"]),
            )
            if header["status"] == "已作废":
                st.warning(f"作废原因：{header['void_reason']}｜操作人：{header['voided_by']}")
            render_void_form(
                "入库单", header["id"], header["status"], "void_inbound",
                void_inbound, user, "inbound",
            )

elif menu == "出库管理":
    c1, _ = st.columns([1, 5])
    if has_permission(user, "create_outbound") and c1.button(
        "＋ 新增出库单", type="primary", width="stretch"
    ):
        outbound_dialog()
    elif not has_permission(user, "create_outbound"):
        st.caption("当前角色可查看出库单，但无权新增或作废。")
    st.subheader("出库单列表")
    with st.expander("筛选条件", expanded=False):
        outbound_start, outbound_end = date_filter("outbound_filter", "按出库日期筛选")
        f1, f2, f3, f4 = st.columns(4)
        outbound_warehouse = f1.selectbox(
            "仓库", ["全部"] + list_warehouses(), key="outbound_filter_warehouse"
        )
        outbound_status = f2.selectbox(
            "单据状态", ["全部", "已生效", "已作废"], key="outbound_filter_status"
        )
        outbound_kind = f3.selectbox(
            "出库类型", ["全部", "销售出库", "领料出库"], key="outbound_filter_type"
        )
        outbound_keyword = f4.text_input(
            "关键词", placeholder="单号、客户、领料人或经办人", key="outbound_filter_keyword"
        )
    outbound_df = rows_df(outbound_list(
        outbound_start, outbound_end, outbound_status, outbound_warehouse,
        outbound_kind, outbound_keyword,
    )).rename(columns=OUTBOUND_COLUMNS)
    if outbound_df.empty:
        st.info("暂无出库单。")
    else:
        event = st.dataframe(
            outbound_df,
            key="outbound_order_list",
            on_select="rerun",
            selection_mode="single-row",
            width="stretch",
            hide_index=True,
            column_config={
                "单据ID": None,
                "出库总金额": st.column_config.NumberColumn("出库总金额", format="¥ %.2f"),
                "已结算金额": st.column_config.NumberColumn("已结算金额", format="¥ %.2f"),
                "未收金额": st.column_config.NumberColumn("未收金额", format="¥ %.2f"),
            },
        )
        if event.selection.rows:
            selected = outbound_df.iloc[event.selection.rows[0]]
            header, items = outbound_detail(int(selected["单据ID"]))
            st.subheader(f"{header['order_no']}｜出库明细")
            party_label = "领料人/部门" if header["outbound_type"] == "领料出库" else "客户"
            st.caption(
                f"日期：{header['order_date']}　类型：{header['outbound_type']}　"
                f"{party_label}：{header['customer_name']}　仓库：{header['warehouse']}　"
                f"状态：{header['status']}"
            )
            st.dataframe(
                detail_items_df(items), width="stretch", hide_index=True,
                column_config={
                    "单价": st.column_config.NumberColumn("单价", format="¥ %.2f"),
                    "金额": st.column_config.NumberColumn("金额", format="¥ %.2f"),
                },
            )
            if header["outbound_type"] == "领料出库":
                st.info("该单为领料出库，不产生应收账款，也不能加入结算单。")
            st.download_button(
                "下载/打印 PDF", data=outbound_pdf(header, items),
                file_name=f"{header['order_no']}_{header['outbound_type']}.pdf",
                mime="application/pdf", key=f"outbound_pdf_{header['id']}",
                on_click=audit_pdf_export,
                args=("出库单", header["id"], header["order_no"]),
            )
            if header["status"] == "已作废":
                st.warning(f"作废原因：{header['void_reason']}｜操作人：{header['voided_by']}")
            render_void_form(
                "出库单", header["id"], header["status"], "void_outbound",
                void_outbound, user, "outbound",
            )

elif menu == "结算管理":
    c1, _ = st.columns([1, 5])
    if has_permission(user, "create_settlement") and c1.button(
        "＋ 新增结算单", type="primary", width="stretch"
    ):
        settlement_dialog()
    elif not has_permission(user, "create_settlement"):
        st.caption("当前角色可查看结算数据，但无权新增或作废结算单。")
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
    with st.expander("筛选条件", expanded=False):
        settlement_start, settlement_end = date_filter("settlement_filter", "按结算日期筛选")
        settlement_customers = list_customers()
        settlement_customer_map = {
            f"{customer['code']} - {customer['name']}": customer["id"]
            for customer in settlement_customers
        }
        f1, f2, f3 = st.columns(3)
        settlement_status = f1.selectbox(
            "单据状态", ["全部", "已生效", "已作废"], key="settlement_filter_status"
        )
        settlement_customer = f2.selectbox(
            "客户", ["全部"] + list(settlement_customer_map), key="settlement_filter_customer"
        )
        settlement_keyword = f3.text_input(
            "关键词", placeholder="单号、客户或经办人", key="settlement_filter_keyword"
        )
    settlement_customer_id = (
        None if settlement_customer == "全部" else settlement_customer_map[settlement_customer]
    )
    settlements_df = rows_df(settlement_list(
        settlement_start, settlement_end, settlement_status,
        settlement_customer_id, settlement_keyword,
    )).rename(columns=SETTLEMENT_COLUMNS)
    if settlements_df.empty:
        st.info("暂无结算单。")
    else:
        event = st.dataframe(
            settlements_df,
            key="settlement_order_list",
            on_select="rerun",
            selection_mode="single-row",
            width="stretch",
            hide_index=True,
            column_config={
                "单据ID": None,
                "结算金额": st.column_config.NumberColumn("结算金额", format="¥ %.2f")
            },
        )
        if event.selection.rows:
            selected = settlements_df.iloc[event.selection.rows[0]]
            header, items = settlement_detail(int(selected["单据ID"]))
            st.subheader(f"{header['settlement_no']}｜结算明细")
            st.caption(
                f"日期：{header['settlement_date']}　客户：{header['customer_name']}　"
                f"方式：{header['method']}　状态：{header['status']}"
            )
            settlement_items = detail_items_df(items)
            st.dataframe(
                settlement_items, width="stretch", hide_index=True,
                column_config={"金额": st.column_config.NumberColumn("金额", format="¥ %.2f")},
            )
            st.download_button(
                "下载/打印 PDF", data=settlement_pdf(header, items),
                file_name=f"{header['settlement_no']}_结算单.pdf", mime="application/pdf",
                key=f"settlement_pdf_{header['id']}",
                on_click=audit_pdf_export,
                args=("结算单", header["id"], header["settlement_no"]),
            )
            if header["status"] == "已作废":
                st.warning(f"作废原因：{header['void_reason']}｜操作人：{header['voided_by']}")
            render_void_form(
                "结算单", header["id"], header["status"], "void_settlement",
                void_settlement, user, "settlement",
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
    st.subheader("库存情况")
    with st.expander("筛选条件", expanded=False):
        inventory_as_of_enabled = st.checkbox("查询历史时点库存", key="inventory_as_of_enabled")
        inventory_as_of = (
            st.date_input("库存截止日期", date.today(), key="inventory_as_of").isoformat()
            if inventory_as_of_enabled else None
        )
        f1, f2, f3 = st.columns(3)
        inventory_warehouse = f1.selectbox(
            "仓库", ["全部"] + list_warehouses(), key="inventory_filter_warehouse"
        )
        inventory_keyword = f2.text_input(
            "产品关键词", placeholder="产品编码、名称或规格", key="inventory_filter_keyword"
        )
        inventory_nonzero = f3.checkbox("仅显示非零库存", key="inventory_nonzero")
    if inventory_as_of:
        st.caption(f"显示截至 {inventory_as_of}（含当日）的历史库存。")
    current_inventory = rows_df(inventory_rows(
        as_of_date=inventory_as_of, warehouse=inventory_warehouse,
        keyword=inventory_keyword, include_zero=not inventory_nonzero,
    )).rename(columns=INVENTORY_COLUMNS)
    if current_inventory.empty:
        st.info("暂无库存数据。")
    else:
        st.dataframe(current_inventory, width="stretch", hide_index=True)

elif menu == "用户与权限":
    st.subheader("用户与权限")
    st.caption("角色权限固定分级；新增用户首次登录后必须修改初始密码。")
    with st.expander("新增用户", expanded=False):
        with st.form("create_user_form"):
            c1, c2, c3, c4 = st.columns(4)
            username = c1.text_input("登录账号")
            display_name = c2.text_input("姓名")
            role_label = c3.selectbox("角色", list(ROLE_LABELS.values()))
            initial_password = c4.text_input("初始密码（至少 8 位）", type="password")
            if st.form_submit_button("创建用户", type="primary"):
                try:
                    role = next(key for key, value in ROLE_LABELS.items() if value == role_label)
                    create_user(username, display_name, role, initial_password, actor=user)
                    st.session_state["flash"] = "用户已创建，首次登录必须修改密码"
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

    users_df = rows_df(list_users(actor=user))
    users_display = users_df.assign(
        role=users_df["role"].map(ROLE_LABELS),
        is_active=users_df["is_active"].map({1: "启用", 0: "停用"}),
        must_change_password=users_df["must_change_password"].map({1: "是", 0: "否"}),
    ).rename(columns={
        "id": "用户ID", "username": "登录账号", "display_name": "姓名", "role": "角色",
        "is_active": "状态", "must_change_password": "需修改密码",
        "last_login_at": "最后登录时间", "created_at": "创建时间", "updated_at": "更新时间",
    })
    event = st.dataframe(
        users_display,
        key="user_list",
        on_select="rerun",
        selection_mode="single-row",
        width="stretch",
        hide_index=True,
        column_config={"用户ID": None},
    )
    if event.selection.rows:
        selected = users_df.iloc[event.selection.rows[0]]
        st.markdown(f"#### 管理用户：{selected['username']}")
        c1, c2, c3 = st.columns(3)
        new_name = c1.text_input("姓名", selected["display_name"], key=f"user_name_{selected['id']}")
        role_keys = list(ROLE_LABELS)
        new_role = c2.selectbox(
            "角色", role_keys, index=role_keys.index(selected["role"]),
            format_func=lambda value: ROLE_LABELS[value], key=f"user_role_{selected['id']}",
        )
        new_active = c3.checkbox(
            "账号启用", value=bool(selected["is_active"]), key=f"user_active_{selected['id']}"
        )
        if st.button("保存用户权限", type="primary", key=f"save_user_{selected['id']}"):
            try:
                update_user(selected["id"], new_name, new_role, new_active, actor=user)
                st.session_state["flash"] = "用户权限已更新"
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
        with st.form(f"reset_password_{selected['id']}"):
            reset_password = st.text_input("重置为新密码（至少 8 位）", type="password")
            confirm_reset = st.checkbox("确认重置；该用户下次登录必须修改密码")
            if st.form_submit_button("重置密码"):
                if not confirm_reset:
                    st.error("请先勾选确认项")
                else:
                    try:
                        reset_user_password(selected["id"], reset_password, actor=user)
                        st.success("密码已重置")
                    except Exception as exc:
                        st.error(str(exc))

elif menu == "审计日志":
    st.subheader("完整审计日志")
    st.caption("记录登录、基础资料、用户权限、单据生效/作废、密码及备份操作。审计记录只读。")
    logs = rows_df(list_audit_logs(actor=user))
    if logs.empty:
        st.info("暂无审计记录。")
    else:
        c1, c2, c3 = st.columns(3)
        user_filter = c1.text_input("按账号筛选")
        action_options = ["全部"] + sorted(logs["action"].dropna().unique().tolist())
        action_filter = c2.selectbox("按操作筛选", action_options)
        entity_options = ["全部"] + sorted(logs["entity_type"].dropna().unique().tolist())
        entity_filter = c3.selectbox("按业务类型筛选", entity_options)
        filtered = logs.copy()
        if user_filter:
            filtered = filtered[filtered["username"].str.contains(user_filter, case=False, na=False)]
        if action_filter != "全部":
            filtered = filtered[filtered["action"] == action_filter]
        if entity_filter != "全部":
            filtered = filtered[filtered["entity_type"] == entity_filter]
        audit_display = filtered.rename(columns={
            "id": "日志ID", "created_at": "操作时间", "username": "操作账号",
            "action": "操作", "entity_type": "业务类型", "entity_id": "业务ID",
            "source_no": "业务单号", "detail": "原因/说明",
            "before_json": "修改前", "after_json": "修改后",
        })
        st.dataframe(audit_display, width="stretch", hide_index=True)
