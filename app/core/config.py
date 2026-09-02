"""Application configuration management.

This module handles environment-specific configuration loading, parsing, and management
for the application. It includes environment detection, .env file loading, and
configuration value parsing.
"""

import os
from enum import Enum
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv


# Define environment types
class Environment(str, Enum):
    """Application environment types.

    Defines the possible environments the application can run in:
    development, staging, production, and test.
    """

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TEST = "test"


# Determine environment
def get_environment() -> Environment:
    """Get the current environment.

    Returns:
        Environment: The current environment (development, staging, production, or test)
    """
    match os.getenv("APP_ENV", "development").lower():
        case "production" | "prod":
            return Environment.PRODUCTION
        case "staging" | "stage":
            return Environment.STAGING
        case "test":
            return Environment.TEST
        case _:
            return Environment.DEVELOPMENT


# Load appropriate .env file based on environment
def load_env_file():
    """Load environment-specific .env file."""
    env = get_environment()
    print(f"Loading environment: {env}")
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

    # Define env files in priority order
    env_files = [
        os.path.join(base_dir, f".env.{env.value}.local"),
        os.path.join(base_dir, f".env.{env.value}"),
        os.path.join(base_dir, ".env.local"),
        os.path.join(base_dir, ".env"),
    ]

    # Load the first env file that exists
    for env_file in env_files:
        if os.path.isfile(env_file):
            load_dotenv(dotenv_path=env_file)
            print(f"Loaded environment from {env_file}")
            return env_file

    # Fall back to default if no env file found
    return None


ENV_FILE = load_env_file()


# Parse list values from environment variables
def parse_list_from_env(env_key, default=None):
    """Parse a comma-separated list from an environment variable."""
    value = os.getenv(env_key)
    if not value:
        return default or []

    # Remove quotes if they exist
    value = value.strip("\"'")
    # Handle single value case
    if "," not in value:
        return [value]
    # Split comma-separated values
    return [item.strip() for item in value.split(",") if item.strip()]


# Parse dict of lists from environment variables with prefix
def parse_dict_of_lists_from_env(prefix, default_dict=None):
    """Parse dictionary of lists from environment variables with a common prefix."""
    result = default_dict or {}

    # Look for all env vars with the given prefix
    for key, value in os.environ.items():
        if key.startswith(prefix):
            endpoint = key[len(prefix) :].lower()  # Extract endpoint name
            # Parse the values for this endpoint
            if value:
                value = value.strip("\"'")
                if "," in value:
                    result[endpoint] = [item.strip() for item in value.split(",") if item.strip()]
                else:
                    result[endpoint] = [value]

    return result


class Settings:
    """Application settings without using pydantic."""

    def __init__(self):
        """Initialize application settings from environment variables.

        Loads and sets all configuration values from environment variables,
        with appropriate defaults for each setting. Also applies
        environment-specific overrides based on the current environment.
        """
        # Set the environment
        self.ENVIRONMENT = get_environment()

        # Application Settings
        self.PROJECT_NAME = os.getenv("PROJECT_NAME", "FastAPI LangGraph Template")
        self.VERSION = os.getenv("VERSION", "1.0.0")
        self.DESCRIPTION = os.getenv(
            "DESCRIPTION", "A production-ready FastAPI template with LangGraph and Langfuse integration"
        )
        self.API_V1_STR = os.getenv("API_V1_STR", "/api/v1")
        self.DEBUG = os.getenv("DEBUG", "false").lower() in ("true", "1", "t", "yes")

        # 产业图谱：启动时若图谱为空则自动注入 NVIDIA 产业链种子数据
        self.SEED_SUPPLY_CHAIN_ON_STARTUP = os.getenv(
            "SEED_SUPPLY_CHAIN_ON_STARTUP", "true"
        ).lower() in ("true", "1", "t", "yes")

        # 启动时自动执行 alembic upgrade head（release 阶段迁移不可靠时的兜底）
        self.RUN_DB_MIGRATIONS_ON_STARTUP = os.getenv(
            "RUN_DB_MIGRATIONS_ON_STARTUP", "true"
        ).lower() in ("true", "1", "t", "yes")

        # CORS Settings
        self.ALLOWED_ORIGINS = parse_list_from_env("ALLOWED_ORIGINS", ["*"])

        # Langfuse Configuration
        self.LANGFUSE_TRACING_ENABLED = os.getenv("LANGFUSE_TRACING_ENABLED", "true").lower() in (
            "true",
            "1",
            "t",
            "yes",
        )
        self.LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY", "")
        self.LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY", "")
        self.LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")

        # LangGraph Configuration
        self.OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
        self.DEFAULT_LLM_MODEL = os.getenv("DEFAULT_LLM_MODEL", "gpt-5-mini")
        self.SESSION_NAMING_ENABLED = os.getenv("SESSION_NAMING_ENABLED", "true").lower() == "true"
        self.DEFAULT_LLM_TEMPERATURE = float(os.getenv("DEFAULT_LLM_TEMPERATURE", "0.2"))
        self.MAX_TOKENS = int(os.getenv("MAX_TOKENS", "2000"))
        self.MAX_LLM_CALL_RETRIES = int(os.getenv("MAX_LLM_CALL_RETRIES", "3"))
        self.LLM_TOTAL_TIMEOUT = int(os.getenv("LLM_TOTAL_TIMEOUT", "60"))

        # 图谱抽取模式：
        #   single_pass          旧版供应链抽取（现有 5 实体/4 关系 schema，事实入 graph_facts）
        #   finreflect_single    FinReflectKG 论文本体，单次抽取（5 元组入 finkg_triples）
        #   finreflect_multi     FinReflectKG 论文本体，两遍抽取（抽取 → 规范化精炼）
        #   finreflect_reflection FinReflectKG 论文本体，反思智能体（抽取→评审→修正闭环）
        self.GRAPH_EXTRACTION_MODE = os.getenv("GRAPH_EXTRACTION_MODE", "single_pass").lower()
        # reflection 模式最大反思步数 n_max（F=∅ 或达到即停）
        self.GRAPH_REFLECTION_MAX_ITERS = int(os.getenv("GRAPH_REFLECTION_MAX_ITERS", "2"))

        # Long term memory Configuration
        self.LONG_TERM_MEMORY_MODEL = os.getenv("LONG_TERM_MEMORY_MODEL", "gpt-5-nano")
        self.LONG_TERM_MEMORY_EMBEDDER_MODEL = os.getenv("LONG_TERM_MEMORY_EMBEDDER_MODEL", "text-embedding-3-small")
        self.LONG_TERM_MEMORY_COLLECTION_NAME = os.getenv("LONG_TERM_MEMORY_COLLECTION_NAME", "longterm_memory")
        # JWT Configuration
        self.JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
        self.JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
        self.JWT_ACCESS_TOKEN_EXPIRE_DAYS = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_DAYS", "30"))

        # Logging Configuration
        self.LOG_DIR = Path(os.getenv("LOG_DIR", "logs"))
        self.LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
        self.LOG_FORMAT = os.getenv("LOG_FORMAT", "json")  # "json" or "console"

        # Profiling Configuration (DEBUG only)
        self.PROFILING_DIR = Path(os.getenv("PROFILING_DIR", "/tmp/fastapi_profiles"))
        self.PROFILING_THRESHOLD_SECONDS = float(os.getenv("PROFILING_THRESHOLD_SECONDS", "2.0"))

        # Postgres Configuration
        # 优先使用显式 POSTGRES_HOST；若未设置，尝试从 DATABASE_URL（Railway 等平台自动注入）
        # 或 PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE 解析。
        if os.getenv("POSTGRES_HOST"):
            self.POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
            self.POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
            self.POSTGRES_DB = os.getenv("POSTGRES_DB", "food_order_db")
            self.POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
            self.POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
        else:
            database_url = os.getenv("DATABASE_URL", "")
            if database_url:
                parsed = urlparse(database_url)
                self.POSTGRES_HOST = parsed.hostname or "localhost"
                self.POSTGRES_PORT = parsed.port or 5432
                self.POSTGRES_DB = (parsed.path or "/food_order_db").lstrip("/") or "food_order_db"
                self.POSTGRES_USER = parsed.username or "postgres"
                self.POSTGRES_PASSWORD = parsed.password or "postgres"
            else:
                self.POSTGRES_HOST = os.getenv("PGHOST", "localhost")
                self.POSTGRES_PORT = int(os.getenv("PGPORT", "5432"))
                self.POSTGRES_DB = os.getenv("PGDATABASE", os.getenv("POSTGRES_DB", "food_order_db"))
                self.POSTGRES_USER = os.getenv("PGUSER", os.getenv("POSTGRES_USER", "postgres"))
                self.POSTGRES_PASSWORD = os.getenv("PGPASSWORD", os.getenv("POSTGRES_PASSWORD", "postgres"))
        self.POSTGRES_SSL = os.getenv("POSTGRES_SSL", "false").lower() in ("true", "1", "yes")
        self.POSTGRES_POOL_SIZE = int(os.getenv("POSTGRES_POOL_SIZE", "20"))
        self.POSTGRES_MAX_OVERFLOW = int(os.getenv("POSTGRES_MAX_OVERFLOW", "10"))
        self.CHECKPOINT_TABLES = ["checkpoint_blobs", "checkpoint_writes", "checkpoints"]

        # Valkey/Redis Cache Configuration (optional — if host is set, caching is enabled)
        # 优先使用 VALKEY_* 变量；若 VALKEY_HOST 为空，尝试从 REDIS_URL（Railway 等平台自动注入）
        # 或 REDISHOST 解析。
        self.VALKEY_HOST = os.getenv("VALKEY_HOST", "")
        self.VALKEY_PORT = int(os.getenv("VALKEY_PORT", "6379"))
        self.VALKEY_DB = int(os.getenv("VALKEY_DB", "0"))
        self.VALKEY_PASSWORD = os.getenv("VALKEY_PASSWORD", "")
        self.VALKEY_SSL = os.getenv("VALKEY_SSL", "false").lower() in ("true", "1", "yes")

        if not self.VALKEY_HOST:
            redis_url = os.getenv("REDIS_URL", "")
            if redis_url:
                parsed = urlparse(redis_url)
                self.VALKEY_HOST = parsed.hostname or ""
                self.VALKEY_PORT = parsed.port or 6379
                self.VALKEY_PASSWORD = parsed.password or ""
                self.VALKEY_DB = int((parsed.path or "/0").lstrip("/") or "0")
                self.VALKEY_SSL = parsed.scheme == "rediss"
            else:
                self.VALKEY_HOST = os.getenv("REDISHOST", "")
                self.VALKEY_PORT = int(os.getenv("REDISPORT", "6379"))
                self.VALKEY_PASSWORD = os.getenv("REDISPASSWORD", os.getenv("REDIS_PASSWORD", ""))
                if self.VALKEY_HOST and not self.VALKEY_SSL:
                    self.VALKEY_SSL = False

        self.VALKEY_MAX_CONNECTIONS = int(os.getenv("VALKEY_MAX_CONNECTIONS", "20"))
        self.CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "60"))
        self.RATE_LIMIT_USE_VALKEY = os.getenv("RATE_LIMIT_USE_VALKEY", "true").lower() in ("true", "1", "yes")

        redis_scheme = "rediss" if self.VALKEY_SSL else "redis"
        redis_auth = f":{self.VALKEY_PASSWORD}@" if self.VALKEY_PASSWORD else ""
        redis_default = f"{redis_scheme}://{redis_auth}{self.VALKEY_HOST or 'localhost'}:{self.VALKEY_PORT}/{self.VALKEY_DB}"
        self.CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", redis_default)
        self.CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", redis_default)
        if self.CELERY_BROKER_URL.startswith("rediss://") and "ssl_cert_reqs=" not in self.CELERY_BROKER_URL:
            separator = "&" if "?" in self.CELERY_BROKER_URL else "?"
            self.CELERY_BROKER_URL = f"{self.CELERY_BROKER_URL}{separator}ssl_cert_reqs=CERT_REQUIRED"
        if self.CELERY_RESULT_BACKEND.startswith("rediss://") and "ssl_cert_reqs=" not in self.CELERY_RESULT_BACKEND:
            separator = "&" if "?" in self.CELERY_RESULT_BACKEND else "?"
            self.CELERY_RESULT_BACKEND = f"{self.CELERY_RESULT_BACKEND}{separator}ssl_cert_reqs=CERT_REQUIRED"
        self.CELERY_SSL = os.getenv("CELERY_SSL", str(self.VALKEY_SSL)).lower() in ("true", "1", "yes")
        self.SUPPLY_CHAIN_WORKER_CONCURRENCY = int(os.getenv("SUPPLY_CHAIN_WORKER_CONCURRENCY", "4"))
        self.SUPPLY_CHAIN_UNIVERSE = os.getenv("SUPPLY_CHAIN_UNIVERSE", "sp500")
        self.SUPPLY_CHAIN_VERIFY_THRESHOLD = int(os.getenv("SUPPLY_CHAIN_VERIFY_THRESHOLD", "60"))
        self.SUPPLY_CHAIN_GENERIC_SUPPLIERS = parse_list_from_env(
            "SUPPLY_CHAIN_GENERIC_SUPPLIERS", ["TSMC", "Samsung", "Intel", "Google Cloud", "AWS"]
        )
        self.SUPPLY_CHAIN_SMALLCAP_MARKETCAP = float(os.getenv("SUPPLY_CHAIN_SMALLCAP_MARKETCAP", "2e9"))
        self.SUPPLY_CHAIN_SKIP_RECENT_DAYS = int(os.getenv("SUPPLY_CHAIN_SKIP_RECENT_DAYS", "7"))
        self.SUPPLY_CHAIN_DISCOVER_MODEL = os.getenv("SUPPLY_CHAIN_DISCOVER_MODEL", "")
        self.SUPPLY_CHAIN_VERIFY_MODEL = os.getenv("SUPPLY_CHAIN_VERIFY_MODEL", "")
        # 默认关闭：每周全量供应链批处理会遍历整个 universe 逐只调 LLM，
        # 极易在新部署时无意中耗尽 LLM 额度并刷屏超时日志。需要时显式设为 true。
        self.SUPPLY_CHAIN_BEAT_ENABLED = os.getenv("SUPPLY_CHAIN_BEAT_ENABLED", "false").lower() in ("true", "1", "yes")
        self.SUPPLY_CHAIN_WEEKLY_SCHEDULER_INTERVAL_SECONDS = int(
            os.getenv("SUPPLY_CHAIN_WEEKLY_SCHEDULER_INTERVAL_SECONDS", "3600")
        )
        self.SUPPLY_CHAIN_DISCOVER_CACHE_TTL = int(os.getenv("SUPPLY_CHAIN_DISCOVER_CACHE_TTL", "604800"))
        self.SUPPLY_CHAIN_TRANSCRIPT_QUARTERS = int(os.getenv("SUPPLY_CHAIN_TRANSCRIPT_QUARTERS", "4"))
        self.SUPPLY_CHAIN_NEWS_LOOKBACK_DAYS = int(os.getenv("SUPPLY_CHAIN_NEWS_LOOKBACK_DAYS", "730"))
        self.SUPPLY_CHAIN_QUOTA_WINDOW_SECONDS = int(os.getenv("SUPPLY_CHAIN_QUOTA_WINDOW_SECONDS", "18000"))
        self.SUPPLY_CHAIN_MAX_QUOTA_RETRIES = int(os.getenv("SUPPLY_CHAIN_MAX_QUOTA_RETRIES", "10"))
        self.SUPPLY_CHAIN_MAX_PROBE_ATTEMPTS = int(os.getenv("SUPPLY_CHAIN_MAX_PROBE_ATTEMPTS", "10"))
        self.SUPPLY_CHAIN_PROBE_BACKOFF_SECONDS = int(os.getenv("SUPPLY_CHAIN_PROBE_BACKOFF_SECONDS", "60"))

        # 交易台（多智能体分析）
        # LLM 复用平台统一配置：LLM_PROVIDER / *_API_KEY / MAX_TOKENS /
        # DEFAULT_LLM_TEMPERATURE 一律沿用，此处不引入第二套供应商配置。
        # 下面两个是注册表里的「模型名」（非供应商模型 ID），沿用
        # SUPPLY_CHAIN_DISCOVER_MODEL 的先例，留空回落 DEFAULT_LLM_MODEL。
        self.TRADING_DESK_ENGINE = os.getenv("TRADING_DESK_ENGINE", "tradingagents")
        self.TRADING_DESK_DEEP_MODEL = os.getenv("TRADING_DESK_DEEP_MODEL", "")
        self.TRADING_DESK_QUICK_MODEL = os.getenv("TRADING_DESK_QUICK_MODEL", "")
        self.TRADING_DESK_MAX_DEBATE_ROUNDS = int(os.getenv("TRADING_DESK_MAX_DEBATE_ROUNDS", "2"))
        self.TRADING_DESK_MAX_RISK_ROUNDS = int(os.getenv("TRADING_DESK_MAX_RISK_ROUNDS", "1"))
        self.TRADING_DESK_EVENT_TTL_SECONDS = int(os.getenv("TRADING_DESK_EVENT_TTL_SECONDS", "604800"))
        # Anthropic extended thinking。开启后 LangChain ChatAnthropic 会下发
        # thinking blocks，前端可看到 agent 推理链（不仅结论）。
        # 仅对 claude-3-7+ / sonnet-4+ / opus-4+ 起效，其他供应商 / 模型自动跳过。
        self.TRADING_DESK_ENABLE_THINKING = os.getenv("TRADING_DESK_ENABLE_THINKING", "false").lower() in ("true", "1", "yes")
        self.TRADING_DESK_THINK_BUDGET = int(os.getenv("TRADING_DESK_THINK_BUDGET", "2048"))
        # LLM 回复语言。BCP 47 标签。引擎把 BCP 47 翻译成完整 locale 名 +
        # 中文 locale 名（如「请用简体中文（Simplified Chinese, BCP 47: zh-CN）回复」）
        # 拼到 tradingagents 系统提示末尾，强制 LLM 用中文输出。
        # BUY/SELL/HOLD 信号 token 按上游约定保持英文。
        self.TRADING_DESK_RESPONSE_LANGUAGE = os.getenv("TRADING_DESK_RESPONSE_LANGUAGE", "zh-CN")

        # Rate Limiting Configuration
        self.RATE_LIMIT_DEFAULT = parse_list_from_env("RATE_LIMIT_DEFAULT", ["200 per day", "50 per hour"])

        # Rate limit endpoints defaults
        default_endpoints = {
            "chat": ["30 per minute"],
            "chat_stream": ["20 per minute"],
            "messages": ["50 per minute"],
            "register": ["10 per hour"],
            "login": ["20 per minute"],
            "root": ["10 per minute"],
            "health": ["20 per minute"],
            "transcripts": ["1000 per minute"],
            "vocabulary_recognize": ["20 per hour"],
            "vocabulary_change_password": ["10 per hour"],
            # 删号要验密码，限流同时兜住暴力试密码
            "vocabulary_delete_account": ["5 per hour"],
            # 发验证码要花真金白银，且会打扰用户邮箱，按 IP 卡死
            "vocabulary_register_request_code": ["5 per hour"],
            # 短信按条计费且会实际打扰用户，比邮件收得更紧
            "vocabulary_phone_request_code": ["5 per hour"],
            "vocabulary_password_reset_request": ["5 per hour"],
            # 校验侧再兜一层：单个邮箱的错误次数由 Redis 计数管，这里防的是
            # 换着邮箱大批量撞码
            "vocabulary_password_reset_confirm": ["20 per hour"],
            # 缠论：发码要花钱且会打扰用户，按 IP 卡死，额度与 WordLens 同类端点对齐
            "chan_email_request_code": ["5 per hour"],
            "chan_phone_request_code": ["5 per hour"],
            # 校验侧防的是换着账号大批量撞码；单账号的错误次数由 Redis 计数管
            "chan_code_verify": ["20 per hour"],
        }

        # Update rate limit endpoints from environment variables
        self.RATE_LIMIT_ENDPOINTS = default_endpoints.copy()
        for endpoint in default_endpoints:
            env_key = f"RATE_LIMIT_{endpoint.upper()}"
            value = parse_list_from_env(env_key)
            if value:
                self.RATE_LIMIT_ENDPOINTS[endpoint] = value

        # Evaluation Configuration
        self.EVALUATION_LLM = os.getenv("EVALUATION_LLM", "gpt-5")
        self.EVALUATION_BASE_URL = os.getenv("EVALUATION_BASE_URL", "https://api.openai.com/v1")
        self.EVALUATION_API_KEY = os.getenv("EVALUATION_API_KEY", self.OPENAI_API_KEY)
        self.EVALUATION_SLEEP_TIME = int(os.getenv("EVALUATION_SLEEP_TIME", "10"))

        # Financial Modeling Prep API
        self.FMP_API_KEY: str = os.getenv("FMP_API_KEY", "")

        # Alpha Vantage API（电话会议记录抓取备用源）
        self.ALPHA_VANTAGE_KEY: str | None = os.getenv("ALPHA_VANTAGE_KEY", None)

        # News API Key
        self.NEWS_API_KEY: str = os.getenv("NEWS_API_KEY", "")

        # LLM 供应商配置
        self.LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")  # openai | claude | minimax | gemini
        self.ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
        self.ANTHROPIC_BASE_URL = os.getenv("ANTHROPIC_BASE_URL", "")  # 为空则使用官方地址
        # 当 ANTHROPIC_BASE_URL 指向 MiniMax 兼容接口时，注册的 MiniMax 模型 ID 列表
        # （逗号分隔）。列出套餐里真实可用的模型 ID 即可，例如把高速版与推理版并列，
        # 注册后可用 SUPPLY_CHAIN_DISCOVER_MODEL 或 DEFAULT_LLM_MODEL 按名称（小写）选择。
        self.MINIMAX_CLAUDE_MODELS = parse_list_from_env(
            "MINIMAX_CLAUDE_MODELS", default=["MiniMax-M2.7", "MiniMax-M3"]
        )
        self.MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY", "")
        self.MINIMAX_BASE_URL = os.getenv("MINIMAX_BASE_URL", "https://api.minimax.chat/v1")
        # WordLens 英文例句 TTS。支持按优先级配置多个 Key；未配置列表时，
        # 兼容原有单 Key，并最终复用 MiniMax 的通用 API Key。
        self.MINIMAX_TTS_API_KEY = os.getenv("MINIMAX_TTS_API_KEY", "") or self.MINIMAX_API_KEY
        configured_tts_keys = parse_list_from_env("MINIMAX_TTS_API_KEYS")
        if not configured_tts_keys and self.MINIMAX_TTS_API_KEY:
            configured_tts_keys = [self.MINIMAX_TTS_API_KEY]
        self.MINIMAX_TTS_API_KEYS = list(dict.fromkeys(configured_tts_keys))
        self.MINIMAX_TTS_BASE_URL = os.getenv(
            "MINIMAX_TTS_BASE_URL", "https://api.minimaxi.com/v1"
        ).rstrip("/")
        self.MINIMAX_TTS_MODEL = os.getenv("MINIMAX_TTS_MODEL", "speech-2.8-hd")
        self.MINIMAX_TTS_KEY_COOLDOWN_SECONDS = int(
            os.getenv("MINIMAX_TTS_KEY_COOLDOWN_SECONDS", "1800")
        )
        # 官方音色描述：Trustworthy Man 为通用美式口音，Graceful Lady 为经典英式口音。
        self.MINIMAX_TTS_VOICE_US = os.getenv(
            "MINIMAX_TTS_VOICE_US", "English_Trustworthy_Man"
        )
        self.MINIMAX_TTS_VOICE_UK = os.getenv(
            "MINIMAX_TTS_VOICE_UK", "English_Graceful_Lady"
        )
        self.GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")

        # 拍照识别单词（vocabulary/recognizer）专用视觉模型配置。
        # 独立于全局 LLM_PROVIDER：识别是一次性的看图任务，需要一个又快又准的视觉
        # 模型，默认选 Gemini Flash（多语言 OCR 强、秒级延迟、成本低），不跟随聊天/
        # 其它模块的默认 provider。registry.build_vision_llm() 会按下面的 provider/model
        # 独立构建并追加进注册表，复用对应供应商已有的 API key。
        # 默认用 gemini-flash-lite-latest：flash-lite 是 Flash 家族里的轻量档，实测
        # 同一张图识别质量（词表/音标/释义/例句、复合词与变形处理）与标准 Flash 一致，
        # 但端到端快 2~3 倍（24 词整图约 5s vs 标准 Flash 的 12~17s）——拍照识别对延迟
        # 敏感，速度收益远大于那点质量差异。用 -latest 别名而不是钉死具体版本号，是因为
        # 实测具体版本（如 gemini-2.5-flash）会被 Google 对新账号停用直接 404，latest
        # 别名自动跟随当前版本可避免再次踩坑。想固定版本可改成 gemini-3.5-flash-lite 等；
        # 若追求更高识别质量、不在意慢一点可用 gemini-3.5-flash。
        # VOCAB_VISION_PROVIDER 可选 gemini、openai、claude(anthropic)；VOCAB_VISION_MODEL
        # 填对应 provider 下的真实模型 ID。换模型只改这两个环境变量即可，无需动代码。
        self.VOCAB_VISION_PROVIDER = os.getenv("VOCAB_VISION_PROVIDER", "gemini")
        self.VOCAB_VISION_MODEL = os.getenv("VOCAB_VISION_MODEL", "gemini-flash-lite-latest")
        # 视觉模型单次调用的最大输出 token；识别阶段词数近似线性、丰富阶段按 8 词一批，
        # 4096 是实测不被截断的余量值（见 recognizer 里的说明）。
        self.VOCAB_VISION_MAX_TOKENS = int(os.getenv("VOCAB_VISION_MAX_TOKENS", "4096"))
        # 拍照识别专用温度：识别是「看图抠词」的确定性任务，温度非 0 会带来采样随机性
        # ——实测同一张图（尤其专有名词多、边界模糊的截图）在 0.2 下识别结果在「8 词」
        # 和「30 词」之间来回跳，甚至偶尔不遵守专有名词排除。固定 0.0 追求可复现的结果。
        self.VOCAB_VISION_TEMPERATURE = float(os.getenv("VOCAB_VISION_TEMPERATURE", "0.0"))
        # 丰富阶段（配音标/释义/例句）并发批数上限。词多的图分成多批并发跑，这个值越
        # 大墙钟越短，但越容易撞下游 LLM 的速率限制。默认 8（Gemini flash-lite 限额较
        # 宽，8 并发下 100+ 词的整图能把等待砍到 2 波左右）。撞限流就调小，额度富裕
        # 可再调大——改环境变量即可，无需动代码。
        self.VOCAB_ENRICH_CONCURRENCY = int(os.getenv("VOCAB_ENRICH_CONCURRENCY", "8"))

        # 邮件发送（阿里云邮件推送的 SMTP 接入）。
        # 用 SMTP 而不是阿里云 SDK：只发验证码这一种简单邮件，标准库 smtplib 就够，
        # 没必要为此引入一整套 SDK 依赖。凭据留空时发信服务视为未配置，
        # 找回密码接口会明确报错而不是静默失败。
        self.SMTP_HOST = os.getenv("SMTP_HOST", "smtpdm.aliyun.com")
        self.SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))  # 465=SSL，Railway 出网不封
        self.SMTP_USER = os.getenv("SMTP_USER", "")  # 阿里云控制台里的「发信地址」
        self.SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")  # 该发信地址的 SMTP 密码
        self.SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "鹦鹉背单词")
        self.SMTP_TIMEOUT_SECONDS = int(os.getenv("SMTP_TIMEOUT_SECONDS", "15"))

        # 缠论 App 的邮件署名。与 WordLens 共用一套 SMTP 发信，但落款必须各是各的，
        # 否则缠论用户会收到署名「鹦鹉背单词」的验证码邮件，很容易被当成钓鱼邮件。
        # 短信侧不需要这样拆：阿里云号码认证用的是赠送签名，落款本来就不是 App 名。
        self.CHAN_BRAND_NAME = os.getenv("CHAN_BRAND_NAME", "DeepAlpha 缠论")

        # 短信验证码（阿里云号码认证服务 PNVS / Dypnsapi 的「短信认证服务」）。
        # 用这个而不是通用短信服务 dysmsapi：免自建签名和模板的审核，用系统提供的
        # 签名模板开通即用；验证码由阿里云生成、保管和核验，我们不接触明文。
        # 凭据留空则视为未配置，手机号相关接口返回 503，邮箱注册/登录不受影响。
        self.ALIYUN_SMS_ACCESS_KEY_ID = os.getenv("ALIYUN_SMS_ACCESS_KEY_ID", "")
        self.ALIYUN_SMS_ACCESS_KEY_SECRET = os.getenv("ALIYUN_SMS_ACCESS_KEY_SECRET", "")
        self.ALIYUN_SMS_SIGN_NAME = os.getenv("ALIYUN_SMS_SIGN_NAME", "")
        # 按用途选模板。系统赠送模板里 100001 是「登录/注册」、100003 是「重置密码」，
        # 文案会明确写出用户正在做什么——场景和内容对上，用户判断是不是钓鱼短信时
        # 更有依据，也符合运营商对验证码短信的内容要求。
        self.ALIYUN_SMS_TEMPLATE_REGISTER = os.getenv("ALIYUN_SMS_TEMPLATE_REGISTER", "100001")
        self.ALIYUN_SMS_TEMPLATE_PASSWORD_RESET = os.getenv(
            "ALIYUN_SMS_TEMPLATE_PASSWORD_RESET", "100003"
        )
        # 国际/港澳台短信模板。阿里云的国际短信走独立的模板和签名审核，国内的
        # 系统赠送模板（100001/100003）发不到境外号码，必须单独申请。留空则回退到
        # 上面的国内模板——发不出去时会在 codes 层报「渠道不可用」，而不是静默失败。
        self.ALIYUN_SMS_TEMPLATE_REGISTER_INTL = os.getenv(
            "ALIYUN_SMS_TEMPLATE_REGISTER_INTL", ""
        ) or self.ALIYUN_SMS_TEMPLATE_REGISTER
        self.ALIYUN_SMS_TEMPLATE_PASSWORD_RESET_INTL = os.getenv(
            "ALIYUN_SMS_TEMPLATE_PASSWORD_RESET_INTL", ""
        ) or self.ALIYUN_SMS_TEMPLATE_PASSWORD_RESET
        # 控制台「号码认证方案管理」里创建的方案名称。发码和核验必须用同一个，
        # 不填则走阿里云的「默认方案」。
        self.ALIYUN_SMS_SCHEME_NAME = os.getenv("ALIYUN_SMS_SCHEME_NAME", "")
        self.ALIYUN_SMS_ENDPOINT = os.getenv("ALIYUN_SMS_ENDPOINT", "https://dypnsapi.aliyuncs.com/")
        self.ALIYUN_SMS_REGION = os.getenv("ALIYUN_SMS_REGION", "cn-hangzhou")
        self.SMS_TIMEOUT_SECONDS = int(os.getenv("SMS_TIMEOUT_SECONDS", "10"))
        # 默认国家码：用户只填 11 位手机号时按这个补全成 E.164
        self.DEFAULT_PHONE_COUNTRY_CODE = os.getenv("DEFAULT_PHONE_COUNTRY_CODE", "86")

        # 邮箱验证码策略（注册与找回密码共用同一套参数）。
        # 兼容旧的 PASSWORD_RESET_* 变量名：线上已经配过的话不用改环境变量。
        self.EMAIL_CODE_TTL = int(
            os.getenv("EMAIL_CODE_TTL", os.getenv("PASSWORD_RESET_CODE_TTL", "600"))
        )  # 10 分钟
        self.EMAIL_CODE_RESEND_COOLDOWN = int(
            os.getenv("EMAIL_CODE_RESEND_COOLDOWN", os.getenv("PASSWORD_RESET_RESEND_COOLDOWN", "60"))
        )
        self.EMAIL_CODE_MAX_ATTEMPTS = int(
            os.getenv("EMAIL_CODE_MAX_ATTEMPTS", os.getenv("PASSWORD_RESET_MAX_ATTEMPTS", "5"))
        )

        # 短信成本闸（只对短信生效，邮箱不花钱不受限）。60 秒冷却挡的是「连点重发」，
        # 挡不住「同一个号一天被发几十次」或「换 IP 轰炸大量不同号码」——后者才是真正
        # 烧钱的短信 pumping 攻击。这里加两道按天的闸：
        #   - 单号每日上限：一个号码 24 小时内最多发几条，正常用户一两条就够了。
        #   - 全局每日预算：全站一天的短信总条数硬上限，相当于一个熔断，防止被刷爆账单。
        # 触发任一都返回 429，让用户/攻击者明确知道被限了，而不是静默吞掉。
        self.SMS_PER_PHONE_DAILY_LIMIT = int(os.getenv("SMS_PER_PHONE_DAILY_LIMIT", "10"))
        self.SMS_GLOBAL_DAILY_LIMIT = int(os.getenv("SMS_GLOBAL_DAILY_LIMIT", "300"))

        # JWT 补充配置（与现有 JWT_ACCESS_TOKEN_EXPIRE_DAYS 对齐）
        self.ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
        self.REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

        # Sign in with Apple：iOS App 的 Bundle ID，用作校验 Apple 身份令牌的 aud
        self.APPLE_CLIENT_ID = os.getenv("APPLE_CLIENT_ID", "club.deepalpha.chan")

        # CORS（别名，兼容 ALLOWED_ORIGINS）
        cors_env = os.getenv("CORS_ORIGINS", "")
        if cors_env:
            self.CORS_ORIGINS = parse_list_from_env("CORS_ORIGINS", ["http://localhost:3000"])
        else:
            self.CORS_ORIGINS = self.ALLOWED_ORIGINS

        # Always allow local frontend during desktop/dev workflows. Some local
        # env files intentionally use production-like APP_ENV values while the
        # browser still runs on localhost:3000.
        for origin in ("http://localhost:3000", "http://127.0.0.1:3000"):
            if origin not in self.CORS_ORIGINS:
                self.CORS_ORIGINS.append(origin)

        # HTTP Proxy Configuration
        self.HTTP_PROXY = os.getenv("HTTP_PROXY", os.getenv("http_proxy", ""))
        self.HTTPS_PROXY = os.getenv("HTTPS_PROXY", os.getenv("https_proxy", ""))

        # Apply environment-specific settings
        self.apply_environment_settings()

    def apply_environment_settings(self):
        """Apply environment-specific settings based on the current environment."""
        env_settings = {
            Environment.DEVELOPMENT: {
                "DEBUG": True,
                "LOG_LEVEL": "DEBUG",
                "LOG_FORMAT": "console",
                "RATE_LIMIT_DEFAULT": ["1000 per day", "200 per hour"],
            },
            Environment.STAGING: {
                "DEBUG": False,
                "LOG_LEVEL": "INFO",
                "RATE_LIMIT_DEFAULT": ["500 per day", "100 per hour"],
            },
            Environment.PRODUCTION: {
                "DEBUG": False,
                # INFO 便于线上观测请求/成功日志；如需降噪可用环境变量 LOG_LEVEL=WARNING 覆盖
                "LOG_LEVEL": "INFO",
                "RATE_LIMIT_DEFAULT": ["200 per day", "50 per hour"],
            },
            Environment.TEST: {
                "DEBUG": True,
                "LOG_LEVEL": "DEBUG",
                "LOG_FORMAT": "console",
                "RATE_LIMIT_DEFAULT": ["1000 per day", "1000 per hour"],  # Relaxed for testing
            },
        }

        # Get settings for current environment
        current_env_settings = env_settings.get(self.ENVIRONMENT, {})

        # Apply settings if not explicitly set in environment variables
        for key, value in current_env_settings.items():
            env_var_name = key.upper()
            # Only override if environment variable wasn't explicitly set
            if env_var_name not in os.environ:
                setattr(self, key, value)


# Create settings instance
settings = Settings()
