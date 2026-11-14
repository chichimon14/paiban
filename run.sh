#!/bin/sh
# 示例科室排班系统启动脚本（Mac / Linux）
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  echo "首次运行：创建虚拟环境并安装依赖……"
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi
echo "排班系统启动： http://localhost:3000"
exec .venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 3000
