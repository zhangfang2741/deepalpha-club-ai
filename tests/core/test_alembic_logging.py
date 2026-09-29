"""启动时跑 alembic 迁移不能覆盖应用已配好的日志（否则生产 INFO 日志全部消失）。"""
import logging
from logging.config import fileConfig

import pytest

from app.core.logging import configure_alembic_logging

INI = "alembic.ini"


@pytest.fixture
def isolated_root_logging():
    """保存并恢复根 logger 与已存在 logger 的状态，测试之间互不污染。"""
    root = logging.getLogger()
    saved = (root.level, list(root.handlers))
    app_logger = logging.getLogger("app.core.logging")
    saved_disabled = app_logger.disabled
    yield root
    root.handlers[:] = saved[1]
    root.setLevel(saved[0])
    app_logger.disabled = saved_disabled


def test_app_configured_logging_survives_migrations(isolated_root_logging) -> None:
    """应用已配好日志（根 logger 有 handler）时，迁移不改根级别、不换 handler、不禁用 logger。"""
    root = isolated_root_logging
    handler = logging.StreamHandler()
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)
    app_logger = logging.getLogger("app.core.logging")

    configure_alembic_logging(INI)

    assert root.handlers == [handler]
    assert root.level == logging.INFO
    assert not app_logger.disabled
    assert app_logger.isEnabledFor(logging.INFO)


def test_standalone_alembic_cli_uses_ini_logging(isolated_root_logging) -> None:
    """单独跑 alembic 命令行（根 logger 无 handler）时照常按 alembic.ini 配置。"""
    root = isolated_root_logging
    root.handlers[:] = []

    configure_alembic_logging(INI)

    assert root.handlers  # alembic.ini 的 console handler
    assert root.level == logging.WARNING


def test_plain_fileconfig_is_what_broke_production(isolated_root_logging) -> None:
    """对照：旧写法 fileConfig(ini) 会把根级别打到 WARNING，应用 INFO 日志失效。"""
    root = isolated_root_logging
    root.handlers[:] = [logging.StreamHandler()]
    root.setLevel(logging.INFO)
    fileConfig(INI)
    assert not logging.getLogger("app.core.logging").isEnabledFor(logging.INFO)
