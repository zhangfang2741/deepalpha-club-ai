#!/bin/sh
# Docker CMD 入口：同时后台运行 Celery worker 与前台 uvicorn。
# 详见 scripts/start_web_with_worker.sh（可用 RUN_SUPPLY_CHAIN_WORKER=false 只跑 web）。
exec bash /app/scripts/start_web_with_worker.sh
