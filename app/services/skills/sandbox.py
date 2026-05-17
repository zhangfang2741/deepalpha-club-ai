"""subprocess 沙箱：通过独立 Python 子进程执行因子代码，Linux 上 setrlimit 限资源。"""
from __future__ import annotations

import asyncio
import json
import os
import sys

from app.services.skills.errors import SkillSandboxError, SkillTimeoutError

# 用文件路径代替 `-m` 避免 `__package__` 链触发 app/ 包初始化（日志污染 stdout）
_WORKER_PATH = os.path.join(os.path.dirname(__file__), "sandbox_worker.py")


async def run_in_subprocess(
    code: str,
    price_records: list[dict],
    symbol: str,
    start_date: str,
    end_date: str,
    *,
    timeout: float = 30.0,
) -> tuple[list[dict], str]:
    """以独立 Python 子进程执行 skill，Linux 上 setrlimit 限 CPU/内存/fd。"""
    payload = json.dumps({
        "code": code,
        "price": price_records,
        "symbol": symbol,
        "start_date": start_date,
        "end_date": end_date,
    }).encode()

    preexec = _apply_rlimits if sys.platform.startswith("linux") else None

    proc = await asyncio.create_subprocess_exec(
        sys.executable, _WORKER_PATH,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        preexec_fn=preexec,
    )

    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=payload), timeout=timeout,
        )
    except asyncio.TimeoutError:
        proc.kill()
        raise SkillTimeoutError(f"Skill 执行超时（>{int(timeout)}s），请简化逻辑")

    if proc.returncode != 0:
        raise SkillSandboxError(stderr.decode("utf-8", errors="replace")[:500])

    result = json.loads(stdout)
    return result["records"], result.get("output_type", "factor")


def _apply_rlimits() -> None:
    """Linux only：设置资源限制（CPU/内存/fd/子进程数）。"""
    import resource  # noqa: PLC0415
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_FSIZE, (10 * 1024 * 1024, 10 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    resource.setrlimit(resource.RLIMIT_NPROC, (1, 1))
