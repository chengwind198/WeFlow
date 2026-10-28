#!/usr/bin/env bash
# ============================================================
# 停止后端 FastAPI 服务（端口 8000）
# 用法: bash scripts/stop-backend.sh
# ============================================================
set -euo pipefail

PORT=8000
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PID_FILE="$PROJECT_ROOT/logs/backend.pid"

echo "=============================================="
echo "  停止后端服务"
echo "=============================================="

# 优先用 PID 文件
if [ -f "$PID_FILE" ]; then
    saved_pid=$(cat "$PID_FILE")
    if [ -n "$saved_pid" ]; then
        echo "[1] 通过 PID 文件终止 PID=${saved_pid} ..."
        taskkill //PID "$saved_pid" //F 2>/dev/null && echo "  已终止" || echo "  进程已不存在"
        rm -f "$PID_FILE"
    fi
fi

# 兜底：通过端口查找
echo "[2] 检查端口 ${PORT} ..."
pid=$(netstat -ano 2>/dev/null | awk -v p=":${PORT} " '$0 ~ p && /LISTENING/ {print $NF; exit}')
if [ -n "$pid" ] && [ "$pid" != "0" ]; then
    echo "  端口 ${PORT} 被 PID=${pid} 占用，正在终止..."
    taskkill //PID "$pid" //F 2>/dev/null && echo "  已终止 PID=${pid}" || echo "  终止失败"
else
    echo "  端口 ${PORT} 空闲 ✓"
fi

echo "  后端已停止"
echo "=============================================="
