from __future__ import annotations

from datetime import date
import pandas as pd
import streamlit as st

from db import init_db, backup_database, integrity_check, DB_PATH
from services import (
    add_customer, add_product, create_inbound, create_outbound,
    dashboard, inbound_list, inventory_rows, list_customers, list_products,
    list_warehouses, open_receivables, outbound_list, settle,
)

st.set_page_config(page_title="库存管理系统", page_icon="📦", layout="wide")
init_db()

st.title("📦 库存管理系统")
st.caption("AI 安全迭代版 V1.0 · Streamlit + SQLite + Migration")

with st.sidebar.expander("🛡️ 数据安全", expanded=False):
    st.caption(f"数据库：{DB_PATH.name}")
    if st.button("立即备份数据库"):
        try:
            p = backup_database(label="manual")
            st.success(f"备份完成：{p.name}")
        except Exception as e:
            st.error(str(e))
    st.write("完整性检查：", integrity_check())

menu = st.sidebar.radio("功能菜单", ["首页", "基础资料", "入库管理", "出库管理", "结算管理", "应收账款", "库存查询"])


def rows_df(rows):
    return pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()


def product_options():
    products=list_products()
    return products, {f"{p['code']} - {p['name']}": p['id'] for p in products}


if menu == "首页":
    d=dashboard()
    cols=st.columns(4)
    cols[0].metric("今日入库单", d["inbound_today"])
    cols[1].metric("今日出库单", d["outbound_today"])
    cols[2].metric("今日结算单", d["settlement_today"])
    cols[3].metric("当前应收", f"¥{d['receivable']:,.2f}")
    st.subheader("经营概览")
    cols=st.columns(4)
    cols[0].metric("产品种类", d["product_types"])
    cols[1].metric("当前库存总量", f"{d['inventory_total']:,.0f}")
    cols[2].metric("本月新增应收", f"¥{d['month_new_ar']:,.2f}")
    cols[3].metric("本月已结算", f"¥{d['month_settled']:,.2f}")
    st.subheader("当前库存")
    st.dataframe(rows_df(inventory_rows()), use_container_width=True, hide_index=True)

elif menu == "基础资料":
    tab1,tab2=st.tabs(["产品管理","客户管理"])
    with tab1:
        with st.expander("新增产品", expanded=True):
            with st.form("product"):
                c1,c2,c3,c4=st.columns(4)
                code=c1.text_input("产品编码")
                name=c2.text_input("产品名称")
                spec=c3.text_input("规格型号")
                unit=c4.text_input("单位", "件")
                price=st.number_input("默认单价", min_value=0.0, step=0.01)
                if st.form_submit_button("保存产品"):
                    try: add_product(code,name,spec,unit,price); st.success("保存成功"); st.rerun()
                    except Exception as e: st.error(str(e))
        st.dataframe(rows_df(list_products()), use_container_width=True, hide_index=True)
    with tab2:
        with st.expander("新增客户", expanded=True):
            with st.form("customer"):
                c1,c2,c3,c4=st.columns(4)
                code=c1.text_input("客户编码")
                name=c2.text_input("客户名称")
                contact=c3.text_input("联系人")
                phone=c4.text_input("联系电话")
                address=st.text_input("地址")
                method=st.selectbox("结算方式",["现结","月结"])
                if st.form_submit_button("保存客户"):
                    try: add_customer(code,name,contact,phone,address,method); st.success("保存成功"); st.rerun()
                    except Exception as e: st.error(str(e))
        st.dataframe(rows_df(list_customers()), use_container_width=True, hide_index=True)

elif menu == "入库管理":
    st.subheader("新增入库单")
    products, pmap=product_options(); warehouses=list_warehouses()
    with st.form("inbound"):
        c1,c2,c3,c4=st.columns(4)
        order_date=c1.date_input("入库日期", date.today())
        supplier=c2.text_input("供应商")
        warehouse=c3.selectbox("仓库",warehouses)
        operator=c4.text_input("经办人","管理员")
        remark=st.text_input("备注")
        product_label=st.selectbox("产品",list(pmap))
        quantity=st.number_input("数量",min_value=0.0,step=1.0)
        price=st.number_input("单价",min_value=0.0,step=0.01,value=float(products[0]["default_price"]) if products else 0.0)
        confirm=st.checkbox("保存后直接确认入库")
        if st.form_submit_button("保存"):
            try:
                no=create_inbound(order_date.isoformat(),supplier,warehouse,operator,remark,[{"product_id":pmap[product_label],"quantity":quantity,"price":price}],confirm)
                st.success(f"入库单 {no} 已保存")
                st.rerun()
            except Exception as e: st.error(str(e))
    st.subheader("入库单列表")
    st.dataframe(rows_df(inbound_list()),use_container_width=True,hide_index=True)

elif menu == "出库管理":
    st.subheader("新增出库单")
    products,pmap=product_options(); customers=list_customers(); warehouses=list_warehouses()
    cmap={f"{c['code']} - {c['name']}":c['id'] for c in customers}
    with st.form("outbound"):
        c1,c2,c3,c4=st.columns(4)
        order_date=c1.date_input("出库日期",date.today())
        customer_label=c2.selectbox("客户",list(cmap))
        warehouse=c3.selectbox("仓库",warehouses)
        operator=c4.text_input("经办人","管理员")
        remark=st.text_input("备注")
        product_label=st.selectbox("产品",list(pmap))
        quantity=st.number_input("数量",min_value=0.0,step=1.0)
        price=st.number_input("单价",min_value=0.0,step=0.01,value=float(products[0]["default_price"]) if products else 0.0)
        confirm=st.checkbox("保存后直接确认出库")
        if st.form_submit_button("保存"):
            try:
                no=create_outbound(order_date.isoformat(),cmap[customer_label],warehouse,operator,remark,[{"product_id":pmap[product_label],"quantity":quantity,"price":price}],confirm)
                st.success(f"出库单 {no} 已保存")
                st.rerun()
            except Exception as e: st.error(str(e))
    st.subheader("出库单列表")
    st.dataframe(rows_df(outbound_list()),use_container_width=True,hide_index=True)

elif menu == "结算管理":
    customers=list_customers(); cmap={f"{c['code']} - {c['name']}":c['id'] for c in customers}
    if not cmap: st.warning("请先维护客户"); st.stop()
    customer_label=st.selectbox("选择客户",list(cmap))
    customer_id=cmap[customer_label]
    receivables=open_receivables(customer_id)
    if not receivables: st.info("该客户暂无未结算出库单"); st.stop()
    st.dataframe(rows_df(receivables),use_container_width=True,hide_index=True)
    allocations={}
    with st.form("settlement"):
        st.write("填写本次结算金额（不填写表示不结算）")
        for r in receivables:
            allocations[r["id"]]=st.number_input(f"{r['order_no']} 未结算 ¥{r['outstanding']:,.2f}",min_value=0.0,max_value=float(r["outstanding"]),step=0.01,key=f"set_{r['id']}")
        method=st.selectbox("结算方式",["银行转账","现金","其他"])
        settlement_date=st.date_input("结算日期",date.today())
        operator=st.text_input("经办人","管理员")
        remark=st.text_input("备注")
        if st.form_submit_button("生成结算单"):
            try:
                no=settle(customer_id,settlement_date.isoformat(),method,operator,remark,allocations)
                st.success(f"结算单 {no} 已生成")
                st.rerun()
            except Exception as e: st.error(str(e))

elif menu == "应收账款":
    customers=list_customers(); cmap={"全部":None,**{f"{c['code']} - {c['name']}":c['id'] for c in customers}}
    selected=st.selectbox("客户",list(cmap))
    rows=open_receivables(cmap[selected])
    df=rows_df(rows)
    if not df.empty:
        st.metric("未收金额",f"¥{df['outstanding'].sum():,.2f}")
    st.dataframe(df,use_container_width=True,hide_index=True)

elif menu == "库存查询":
    df=rows_df(inventory_rows())
    st.subheader("当前在库产品明细")
    st.dataframe(df,use_container_width=True,hide_index=True)
