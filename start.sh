#!/bin/bash
set -e

cd /app/
plantform="$(uname -m)"
PLANT_PATH=${PLANT_PATH:-/app/env}
plant="${PLANT_PATH}_${plantform}"
source /app/environment.sh
source "$plant/bin/activate"

# Optional one-shot migration for reclaiming legacy raw article pages.
if ! python3 tools/storage_maintenance.py; then
    echo "Storage maintenance failed; preserving the existing database and continuing startup." >&2
fi

# 启动 Xvfb（如果需要非 headless 模式）
if [ "$HEADLESS" != "true" ] || [ "$ENABLE_XVFB" = "true" ]; then
    echo "启动 Xvfb 虚拟 X Server..."
    export DISPLAY=:99
    Xvfb :99 -screen 0 1920x1080x24 -ac &
    XVFB_PID=$!
    echo "Xvfb 已启动 (PID: $XVFB_PID, DISPLAY=$DISPLAY)"
    
    # 等待 Xvfb 启动
    sleep 2
fi

python3 main.py -job True -init True
