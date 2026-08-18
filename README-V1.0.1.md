# AI 安全迭代版库存管理系统 V1.0.1

## 本版本修复
- 修复 `scripts/check_db.py` 从子目录执行时无法导入 `db.py`。
- 统一 `scripts/` 下脚本的项目根目录导入机制。
- 规范 `backup / restore / migrate` 的执行入口。
- 恢复数据库前自动创建安全备份。
- 增加 `run_dev.sh`，统一执行完整性检查、测试并启动 Streamlit。

## 常用命令

```bash
source .venv/bin/activate
python scripts/check_db.py
python scripts/backup.py
python scripts/restore.py backups/xxx.db
python scripts/migrate.py
python -m unittest discover -s tests -v
python -m streamlit run app.py
```

也可以运行：

```bash
./run_dev.sh
```

正式数据库不要提交到 GitHub。
