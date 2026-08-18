# 库存管理系统 Demo

## Mac 一键启动

双击：

**启动库存管理系统.command**

首次启动会自动：
1. 在 Git 克隆目录中安全拉取 GitHub 最新版本
2. 创建 `.venv` 虚拟环境
3. 安装固定版本依赖
4. 检查数据库并启动 Streamlit
5. 自动打开浏览器

以后再次双击即可启动。

自动更新使用 `git pull --ff-only`。如检测到本地代码修改或 Git 历史冲突，启动脚本会停止更新，不会强制覆盖本地文件。`data/` 和 `backups/` 中的业务数据不参与 Git 同步。

## 首次登录

- 账号：`admin`
- 初始密码：`admin123`

首次登录后系统会强制设置新密码。密码仅以哈希形式保存在本地数据库中。

## 终端启动

```bash
cd /你的路径/inventory_demo
./启动库存管理系统.command
```

或者：

```bash
cd /你的路径/inventory_demo
source .venv/bin/activate
python -m streamlit run app.py
```

## 依赖版本

项目固定使用：

- Python 3.11+
- Streamlit 1.49.1
- Pandas 2.2.3
- NumPy 1.26.4
- PyArrow 17.0.0

这样可以避免 NumPy / PyArrow ABI 不兼容导致的：

`ImportError: numpy.core.multiarray failed to import`

## 如果 Mac 提示“无法打开”

第一次双击后，如果 macOS 阻止执行：

打开“系统设置 → 隐私与安全性”，允许该文件运行。

也可以在终端执行：

```bash
chmod +x "启动库存管理系统.command"
```

然后再次双击。

## 停止系统

运行窗口保持打开时，按：

`Control + C`

即可停止。
