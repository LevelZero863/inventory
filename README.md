# 库存管理系统 Demo

基于 Streamlit + SQLite + Pandas 的可运行库存管理系统 Demo。

## 功能

- 首页经营看板
- 产品、客户基础资料新增与编辑，支持启用/停用
- 仓库基础资料新增与编辑，支持编码、启用/停用及历史业务保护
- 产品、客户、仓库、入库单、出库单、结算单和库存支持 Excel 批量导入
- 提供统一 Excel 模板、上传预览、字段校验、权限控制和导入审计
- 入库单：弹窗录入、多行明细、自动带出产品默认单价，提交后立即增加库存
- 出库单：弹窗录入、多行明细、库存校验、自动带出产品默认单价和汇总金额，支持销售出库与领料出库
- 结算管理：弹窗录入，按客户选择未结算出库单，支持部分结算
- 入库单、出库单、结算单支持下载标准 A4 PDF，可在浏览器 PDF 查看器中直接打印
- 入库单、出库单、结算单支持日期、状态、仓库、类型、客户及关键词筛选
- 库存支持仓库、产品关键词及历史截止日期筛选
- 领料出库无需客户，不生成应收账款，也不会进入结算范围
- 应收账款按客户汇总，点击客户可查看单据明细
- 中文库存查询
- 账号密码登录、首次登录强制改密
- 管理员、仓库人员、财务人员、只读人员四级角色权限
- 已生效单据通过作废和反向业务记录纠错，不删除历史单据
- 登录、用户权限、基础资料、单据和备份操作的完整审计日志
- 深色业务导航、浅色工作区、经营指标卡和统一页面标题的现代化界面
- SQLite 本地数据库，首次运行自动初始化并生成演示数据

业务规则与《库存管理系统开发需求说明书》保持一致：库存由已生效的入库/出库业务形成；应收仅由已生效的销售出库形成，等于销售出库金额减已结算金额；领料出库只影响库存；结算支持部分结算。

## 环境要求

- Python 3.11+
- macOS / Windows / Linux

## 安装

```bash
cd inventory_demo
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\\Scripts\\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 启动

```bash
streamlit run app.py
```

浏览器打开 Streamlit 输出的地址即可。

## 数据库

数据库文件自动创建在 `data/inventory.db`。

系统更新不会覆盖该文件，并会在数据库结构迁移前自动备份。只有在明确不需要现有业务数据时，才应手工删除该文件。

## 测试

```bash
python -m unittest discover -s tests -v
```

## 项目结构

```text
inventory_demo/
├── app.py
├── audit.py
├── auth.py
├── db.py
├── permissions.py
├── pdf_exports.py
├── excel_imports.py
├── services.py
├── requirements.txt
├── README.md
├── .gitignore
├── .streamlit/
│   └── config.toml
├── assets/fonts/
│   └── NotoSansSC-Regular.ttf
├── assets/templates/
│   └── 库存系统批量导入模板.xlsx
├── database/migrations/
│   ├── 004_material_issue_and_filters.sql
│   └── 005_warehouse_master.sql
├── data/
│   └── .gitkeep
└── tests/
    └── test_services.py
```
