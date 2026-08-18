# 库存管理系统 V1.2

## 本版本更新

- 新增账号密码登录、退出登录和首次登录强制改密。
- 密码使用 PBKDF2-SHA256 加盐哈希保存，不存储明文。
- 出库单根据各明细行的数量与单价实时汇总总金额。
- Mac 双击启动和终端启动前自动执行安全更新。
- 自动更新使用 `git pull --ff-only`，遇到本地代码修改或冲突时停止，不强制覆盖。

## 首次登录

- 默认账号：`admin`
- 默认密码：`admin123`

首次登录后必须修改密码。也可以在首次初始化数据库前，通过环境变量 `INVENTORY_INITIAL_ADMIN_USERNAME` 和 `INVENTORY_INITIAL_ADMIN_PASSWORD` 自定义初始凭据。

## 自动更新前提

项目必须通过 `git clone https://github.com/LevelZero863/inventory.git` 下载。直接解压 ZIP 的目录没有 `.git` 信息，只能正常启动，不能自动拉取更新。
