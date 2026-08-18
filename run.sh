#!/bin/bash
set -e
cd "$(dirname "$0")"

if [ -d .git ]; then
  echo "正在检查 GitHub 更新……"
  if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "检测到本地代码修改，为避免覆盖，已停止自动更新。"
    exit 1
  fi
  git pull --ff-only origin main
fi

if [ ! -d .venv ]; then python3 -m venv .venv; fi
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m streamlit run app.py --server.headless=false
