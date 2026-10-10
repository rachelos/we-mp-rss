#!/bin/bash
set -e

cd /app/
plantform="$(uname -m)"
PLANT_PATH=${PLANT_PATH:-/app/env}
plant="${PLANT_PATH}_${plantform}"
source /app/environment.sh
source "$plant/bin/activate"

# 启动 Xvfb（如果需要非 headless 模式）
if [ "$HEADLESS" != "true" ] || [ "$ENABLE_XVFB" = "true" ]; then
    echo "启动 Xvfb 虚拟 X Server..."
    export DISPLAY=:99
    # 先清掉可能残留的锁与 socket。`docker compose restart` / `docker restart`
    # **保留容器文件系统**，旧 Xvfb 已被杀掉但 /tmp/.X99-lock 和
    # /tmp/.X11-unix/X99 还在，于是新 Xvfb 启动失败并打印
    #   (EE) Server is already active for display 99
    # 然后**静默退出**，容器仍是 healthy —— 所有依赖浏览器的能力
    # （Playwright、Cookie 自动刷新）就这么哑掉，日志里只有一行 (EE)。
    # 2026-10-06 实测踩到：重启后 ps 里 Xvfb 进程数为 0，锁文件还在。
    rm -f "/tmp/.X${DISPLAY#:}-lock" 2>/dev/null || true
    rm -f "/tmp/.X11-unix/X${DISPLAY#:}" 2>/dev/null || true
    Xvfb :99 -screen 0 1920x1080x24 -ac &
    XVFB_PID=$!
    echo "Xvfb 已启动 (PID: $XVFB_PID, DISPLAY=$DISPLAY)"

    # 等待 Xvfb 启动，并且**确认它真的活着**（sleep 2 后 ps 查不到就是失败）
    sleep 2
    if ! kill -0 "$XVFB_PID" 2>/dev/null; then
        echo "警告: Xvfb 启动失败，依赖浏览器的功能将不可用（详见上方 (EE) 输出）"
    fi
fi

python3 main.py -job True -init True
