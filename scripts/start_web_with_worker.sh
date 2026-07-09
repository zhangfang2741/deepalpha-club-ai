#!/usr/bin/env bash
# 单容器同时运行 Celery worker（后台）与 uvicorn（前台）。
#
# 适用于 Railway 单服务部署：无需额外的 worker 服务，web 起来时
# worker 一起起，供应链批次任务即可被消费。worker 消费 supply_chain 队列。
#
# 任一进程退出即整体退出，交给平台重启，保证 worker 挂掉时不会静默僵死。
# 可用 SUPPLY_CHAIN_WORKER_CONCURRENCY 调整 worker 并发（默认 4）；
# 若内存吃紧可调小。设 RUN_SUPPLY_CHAIN_WORKER=false 可只跑 web。
set -uo pipefail

VENV=/app/.venv/bin
PORT="${PORT:-8000}"

start_web() {
  exec "${VENV}/python" -c "import os,uvicorn; uvicorn.run('app.main:app', host='0.0.0.0', port=int(os.environ.get('PORT', ${PORT})))"
}

if [ "${RUN_SUPPLY_CHAIN_WORKER:-true}" != "true" ]; then
  start_web
fi

# 后台启动 worker
"${VENV}/celery" -A app.core.celery_app worker --loglevel=info -Q supply_chain &
WORKER_PID=$!

# 前台启动 uvicorn
"${VENV}/python" -c "import os,uvicorn; uvicorn.run('app.main:app', host='0.0.0.0', port=int(os.environ.get('PORT', ${PORT})))" &
WEB_PID=$!

shutdown() {
  kill -TERM "$WORKER_PID" "$WEB_PID" 2>/dev/null || true
  wait "$WORKER_PID" "$WEB_PID" 2>/dev/null || true
}
trap shutdown TERM INT

# 任一子进程退出即退出容器（返回其退出码），由平台重启
wait -n "$WORKER_PID" "$WEB_PID"
EXIT_CODE=$?
shutdown
exit "$EXIT_CODE"
