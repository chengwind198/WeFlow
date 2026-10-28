#!/usr/bin/env bash
# ============================================================
# 启动后端 FastAPI 服务（端口 8000）
# 用法: bash scripts/start-backend.sh
# ============================================================
set -euo pipefail

PORT=8000
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$PROJECT_ROOT/logs"

mkdir -p "$LOG_DIR"

echo "=============================================="
echo "  weflow 后端启动脚本"
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

# --- 启动服务 ---
echo "[2/3] 启动 uvicorn (端口 ${PORT}) ..."
cd "$PROJECT_ROOT/backend"
nohup python -m uvicorn app.main:app --reload --host 127.0.0.1 --port ${PORT} \
    > "$LOG_DIR/backend.log" 2>&1 &
BACKEND_PID=$!
echo "  PID=${BACKEND_PID}"

# 保存 PID
echo "$BACKEND_PID" > "$LOG_DIR/backend.pid"

# --- 等待就绪 ---
echo "[3/3] 等待服务就绪..."
for i in $(seq 1 15); do
    if curl -s http://127.0.0.1:${PORT}/ > /dev/null 2>&1; then
        echo "  后端已就绪 ✓  http://127.0.0.1:${PORT}"
        echo "  API 文档:    http://127.0.0.1:${PORT}/docs"
        echo "  日志文件:    $LOG_DIR/backend.log"
        echo "=============================================="
        exit 0
    fi
    sleep 1
done

echo "  ⚠ 后端启动超时，请检查日志: $LOG_DIR/backend.log"
echo "=============================================="
exit 1
