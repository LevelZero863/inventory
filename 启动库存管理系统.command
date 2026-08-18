#!/bin/bash
set -e
cd "$(dirname "$0")"

if [ -d .git ]; then
  echo "正在检查 GitHub 更新……"
  if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "检测到本地代码修改，为避免覆盖，已停止自动更新。"
    echo "请先提交或备份本地修改后再启动。"
    read -r -p "按回车键关闭窗口……"
    exit 1
  fi
  if ! git pull --ff-only origin main; then
    echo "自动更新失败，未覆盖任何本地文件。"
    echo "请检查网络或 Git 状态后重试。"
    read -r -p "按回车键关闭窗口……"
    exit 1
  fi
else
  echo "当前目录不是 Git 仓库，将使用现有本地版本启动。"
  echo "如需自动更新，请使用 git clone 下载项目。"
fi

if [ ! -d .venv ]; then python3 -m venv .venv; fi
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/check_db.py
.venv/bin/python -m streamlit run app.py --server.headless=false
