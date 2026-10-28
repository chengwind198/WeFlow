#!/usr/bin/env bash
# ============================================================
# 启动前端 Vite 开发服务器（端口 5173）
# 用法: bash scripts/start-frontend.sh
# ============================================================
set -euo pipefail

PORT=5173
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$PROJECT_ROOT/logs"

mkdir -p "$LOG_DIR"

echo "=============================================="
echo "  weflow 前端启动脚本"
echo "=============================================="

# --- 检查并释放端口 ---
echo "[1/3] 检查端口 ${PORT} ..."
pid=$(netstat -ano 2>/dev/null | awk -v p=":${PORT} " '$0 ~ p && /LISTENING/ {print $NF; exit}')
if [ -n "$pid" ] && [ "$pid" != "0" ]; then
    echo "  端口 ${PORT} 被 PID=${pid} 占用，正在终止..."
    taskkill //PID "$pid" //F 2>/dev/null && echo "  已终止 PID=${pid}" || echo "  终止失败（可能需要管理员权限）"
    sleep 1
else
    echo "  端口 ${PORT} 空闲 ✓"
fi

# --- 检查 node_modules ---
echo "[2/3] 检查依赖..."
cd "$PROJECT_ROOT/frontend"
if [ ! -d "node_modules" ]; then
    echo "  正在安装依赖 (npm install)..."
    npm install --silent
fi
echo "  依赖就绪 ✓"

# --- 启动服务 ---
echo "[3/3] 启动 Vite 开发服务器 (端口 ${PORT}) ..."
nohup npx vite --host 127.0.0.1 --port ${PORT} \
    > "$LOG_DIR/frontend.log" 2>&1 &
FRONTEND_PID=$!
echo "  PID=${FRONTEND_PID}"

# 保存 PID
echo "$FRONTEND_PID" > "$LOG_DIR/frontend.pid"

# 等待就绪
echo "  等待服务就绪..."
for i in $(seq 1 20); do
    if curl -s http://127.0.0.1:${PORT}/ > /dev/null 2>&1; then
        echo "  前端已就绪 ✓  http://127.0.0.1:${PORT}"
        echo "  日志文件:       $LOG_DIR/frontend.log"
        echo "  正在打开浏览器..."
        cmd.exe /c start http://127.0.0.1:${PORT} 2>/dev/null || true
        echo "=============================================="
        exit 0
    fi
    sleep 1
done

echo "  ⚠ 前端启动超时，请检查日志: $LOG_DIR/frontend.log"
echo "=============================================="
exit 1
