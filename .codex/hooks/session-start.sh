#!/bin/bash
set -euo pipefail

# 仅在远程环境（Claude Code on the web）中运行
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR"

echo "=== 安装后端依赖（uv）==="
if ! command -v uv &>/dev/null; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
uv sync --frozen

echo "=== 安装前端依赖（npm）==="
cd "$CLAUDE_PROJECT_DIR/frontend"
npm install

echo "=== 依赖安装完成 ==="
