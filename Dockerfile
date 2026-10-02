# ---- 阶段 1：编译带自有信号（dp_*）的 czsc 分叉（rust/czsc，约 10 分钟）----
# 与运行镜像同为 Debian bookworm（glibc 2.36），否则 wheel 在 slim 镜像里加载不了。
# 层缓存只取决于 rust/czsc 的内容，应用代码改动不会触发重新编译。
FROM rust:1.90-slim-bookworm AS czsc-build
RUN apt-get update && apt-get install -y python3 python3-pip python3-venv \
    && python3 -m venv /opt/mt && /opt/mt/bin/pip install maturin \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY rust/czsc ./
RUN /opt/mt/bin/maturin build --release --out /dist

FROM python:3.13.2-slim

# Set working directory
WORKDIR /app

# Set non-sensitive environment variables
ARG APP_ENV=production

ENV APP_ENV=${APP_ENV} \
    PYTHONFAULTHANDLER=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=random \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && pip install --upgrade pip \
    && pip install uv \
    && rm -rf /var/lib/apt/lists/*

# 先只拷依赖清单，利用 Docker 层缓存。
# 必须按 uv.lock 精确安装：原来的 `uv pip install -e .` 不读锁文件，每次部署都装
# 最新版，曾把 sqlmodel 从 0.0.38 静默升到 0.0.47（强制 datetime 带时区），
# 导致生词本评分 / 待复习 / 统计接口全部 500。
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy the application
COPY . .
RUN uv sync --frozen --no-dev

# 用自编译的 czsc 分叉替换 PyPI 版（代码里按能力探测自动切换 Rust 路径；PyPI 版仍可回退）。
# 装完立刻断言原生函数在，编译或安装出问题时让构建失败，而不是悄悄退回慢路径。
COPY --from=czsc-build /dist /tmp/czsc_dist
RUN uv pip install --python /app/.venv/bin/python --reinstall --no-deps /tmp/czsc_dist/*.whl \
    && /app/.venv/bin/python -c "import czsc._native as n; assert hasattr(n, 'dp_scan_bs') and hasattr(n, 'dp_structures') and hasattr(n, 'dp_macd')" \
    && rm -rf /tmp/czsc_dist

# Make entrypoint script executable - do this before changing user
RUN chmod +x /app/scripts/docker-entrypoint.sh /app/start.sh /app/scripts/start_web_with_worker.sh

# Create a non-root user
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# Create log directory
RUN mkdir -p /app/logs

# Default port
EXPOSE 8000

# Log the environment we're using
RUN echo "Using ${APP_ENV} environment"

# Command to run the application
ENTRYPOINT ["/app/scripts/docker-entrypoint.sh"]
CMD ["/app/start.sh"]
