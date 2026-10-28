#!/usr/bin/env bash
# ============================================================
# 一键启动前后端所有服务
# 用法: bash scripts/start-all.sh
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "  ╔════════════════════════════════════════════╗"
echo "  ║       weflow 一键启动（前后端）            ║"
echo "  ╚════════════════════════════════════════════╝"
echo ""

echo ">>> 启动后端..."
bash "$SCRIPT_DIR/start-backend.sh"
echo ""

echo ">>> 启动前端..."
bash "$SCRIPT_DIR/start-frontend.sh"
echo ""

echo "  ╔════════════════════════════════════════════╗"
echo "  ║  全部服务已启动                           ║"
echo "  ║                                            ║"
echo "  ║  前端: http://127.0.0.1:5173               ║"
echo "  ║  后端: http://127.0.0.1:8000               ║"
echo "  ║  API:  http://127.0.0.1:8000/docs          ║"
echo "  ║  日志: logs/                                ║"
echo "  ║                                            ║"
echo "  ║  停止: bash scripts/stop-all.sh            ║"
echo "  ╚════════════════════════════════════════════╝"
echo ""
