# 库存管理系统 Demo

基于 Streamlit + SQLite + Pandas 的可运行库存管理系统 Demo。

## 功能

- 首页经营看板
- 产品、客户基础资料新增与编辑，支持启用/停用
- 入库单：弹窗录入、多行明细、自动带出产品默认单价，提交后立即增加库存
- 出库单：弹窗录入、多行明细、库存校验、自动带出产品默认单价和汇总金额，提交后立即减少库存并形成应收
- 结算管理：弹窗录入，按客户选择未结算出库单，支持部分结算
- 应收账款按客户汇总，点击客户可查看单据明细
- 中文库存查询
- 账号密码登录、首次登录强制改密
- 管理员、仓库人员、财务人员、只读人员四级角色权限
- 已生效单据通过作废和反向业务记录纠错，不删除历史单据
- 登录、用户权限、基础资料、单据和备份操作的完整审计日志
- SQLite 本地数据库，首次运行自动初始化并生成演示数据

业务规则与《库存管理系统开发需求说明书》保持一致：库存由已生效的入库/出库业务形成；应收=已生效出库金额-已结算金额；结算支持部分结算。

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
├── services.py
├── requirements.txt
├── README.md
├── .gitignore
├── .streamlit/
│   └── config.toml
├── data/
│   └── .gitkeep
└── tests/
    └── test_services.py
```
