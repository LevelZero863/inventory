# 库存管理系统 Demo

基于 Streamlit + SQLite + Pandas 的可运行库存管理系统 Demo。

## 功能

- 首页经营看板
- 产品管理
- 客户管理
- 入库单：草稿、确认、库存增加
- 出库单：库存校验、确认、库存减少、形成应收
- 结算管理：按客户选择未结算出库单，支持部分结算
- 应收账款查询
- 当前库存查询
- SQLite 本地数据库，首次运行自动初始化并生成演示数据

业务规则与《库存管理系统开发需求说明书》保持一致：库存由入库/出库业务形成；应收=已确认出库金额-已结算金额；结算与出库支持部分结算。

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

删除该文件后重新启动，系统会重新初始化演示数据。

## 测试

```bash
python -m unittest discover -s tests -v
```

## 项目结构

```text
inventory_demo/
├── app.py
├── db.py
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
