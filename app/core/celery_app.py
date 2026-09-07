"""Celery application for background supply-chain jobs."""

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings


def _beijing_crontab(hour: int, minute: int) -> crontab:
    """按北京时间 hour:minute 生成 UTC crontab。

    当前安装的 celery 5.6.3 的 crontab 不支持按任务单独传 timezone 参数
    （BaseSchedule.__init__ 只接受 nowfun/app），而全局 timezone 固定为 UTC
    （供应链任务已依赖这个假设，不能改），所以这里手动换算成 UTC 时刻。
    北京时间全年无夏令时（UTC+8），故只需简单减 8 小时并处理跨天。
    """
    utc_hour = (hour - 8) % 24
    return crontab(hour=utc_hour, minute=minute)


celery_app = Celery("deepalpha", broker=settings.CELERY_BROKER_URL, backend=settings.CELERY_RESULT_BACKEND)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    task_default_queue="supply_chain",
    # 编排任务/晨报任务各自单独一个队列，避免排在某批次几百个公司任务后面被饿死
    # （worker 对多队列轮询消费）。
    task_routes={
        "supply_chain.run_batch": {"queue": "supply_chain_orchestration"},
        "morning_report.generate": {"queue": "morning_report"},
    },
    task_default_rate_limit="30/m",
    worker_concurrency=settings.SUPPLY_CHAIN_WORKER_CONCURRENCY,
    imports=("app.tasks.supply_chain", "app.tasks.morning_report"),
    # beat 进程（Procfile 独立的 beat 行）自动读取本 schedule，无需额外起进程。
    beat_schedule={
        "morning_report_us": {
            "task": "morning_report.generate",
            "schedule": _beijing_crontab(hour=6, minute=30),
            "args": (["us"],),
        },
        "morning_report_cn_hk": {
            "task": "morning_report.generate",
            "schedule": _beijing_crontab(hour=7, minute=10),
            "args": (["cn", "hk"],),
        },
    },
)

# 注册 worker 心跳信号（worker 进程 import 本模块时生效）。
from app.services.supply_chain import worker_heartbeat  # noqa: E402,F401
