#!/usr/bin/env bash
# ============================================================
# 一键停止前后端所有服务
# 用法: bash scripts/stop-all.sh
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "  ╔════════════════════════════════════════════╗"
echo "  ║       停止所有 weflow 服务                 ║"
echo "  ╚════════════════════════════════════════════╝"
echo ""

echo ">>> 停止后端..."
bash "$SCRIPT_DIR/stop-backend.sh"
echo ""

echo ">>> 停止前端..."
bash "$SCRIPT_DIR/stop-frontend.sh"
echo ""

echo "  ╔════════════════════════════════════════════╗"
echo "  ║  所有服务已停止                           ║"
echo "  ║  重启: bash scripts/start-all.sh          ║"
echo "  ╚════════════════════════════════════════════╝"
echo ""
