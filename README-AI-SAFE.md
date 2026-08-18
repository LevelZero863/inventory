# AI 安全迭代版库存管理系统 V1.0

这是在原库存 Demo 基础上增加“代码、数据、数据库结构”三层保护的版本。

## 核心原则

- Git 管代码，不管业务数据库。
- SQLite migration 管数据库结构。
- 自动备份保护正式数据。
- 开发库与正式库分离。
- 自动化测试保护核心业务规则。
- AI 不得直接重建正式数据库。

## 日常开发

```bash
source .venv/bin/activate
export INVENTORY_DB_PATH="$(pwd)/data/inventory_dev.db"
python -m unittest discover -s tests -v
```

## 正式启动

```bash
unset INVENTORY_DB_PATH
python -m streamlit run app.py
```

## 手工备份

```bash
python scripts/backup.py
```

## 检查数据库

```bash
python scripts/check_db.py
```

## 恢复

恢复前脚本会自动再做一次 `before_restore` 备份：

```bash
python scripts/restore.py backups/xxx.db
```

## 新需求开发规则

新增数据库字段或表时，只能新增 migration：

```text
database/migrations/
├── 001_initial.sql
├── 002_add_supplier.sql
└── 003_add_inventory_adjustment.sql
```

不要修改 `001_initial.sql` 来适配新需求。

详细 AI 规则见 `AI_RULES.md`。
