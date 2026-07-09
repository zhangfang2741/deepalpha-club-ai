"""Celery application for background supply-chain jobs."""

from celery import Celery

from app.core.config import settings

celery_app = Celery("deepalpha", broker=settings.CELERY_BROKER_URL, backend=settings.CELERY_RESULT_BACKEND)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    task_default_queue="supply_chain",
    task_default_rate_limit="30/m",
    worker_concurrency=settings.SUPPLY_CHAIN_WORKER_CONCURRENCY,
    imports=("app.tasks.supply_chain",),
)

# 注册 worker 心跳信号（worker 进程 import 本模块时生效）。
from app.services.supply_chain import worker_heartbeat  # noqa: E402,F401
