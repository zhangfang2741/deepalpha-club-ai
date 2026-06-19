"""Long-term memory service using mem0 and pgvector with optional cache layer."""

from mem0 import AsyncMemory

from app.core.cache import (
    cache_key,
    cache_service,
)
from app.core.config import settings
from app.core.logging import logger


class MemoryService:
    """Service for managing long-term memory using mem0 and pgvector."""

    def __init__(self):  # noqa: D107
        self._memory: AsyncMemory | None = None
        self._disabled = False

    def _build_config(self) -> dict | None:
        """Build mem0 config from LLM_PROVIDER; returns None when no embedder key is available."""
        vector_store = {
            "provider": "pgvector",
            "config": {
                "collection_name": settings.LONG_TERM_MEMORY_COLLECTION_NAME,
                "dbname": settings.POSTGRES_DB,
                "user": settings.POSTGRES_USER,
                "password": settings.POSTGRES_PASSWORD,
                "host": settings.POSTGRES_HOST,
                "port": settings.POSTGRES_PORT,
            },
        }

        if settings.LLM_PROVIDER == "claude":
            llm = {
                "provider": "anthropic",
                "config": {
                    "model": settings.LONG_TERM_MEMORY_MODEL,
                    "api_key": settings.ANTHROPIC_API_KEY,
                },
            }
        elif settings.LLM_PROVIDER == "gemini":
            llm = {
                "provider": "gemini",
                "config": {
                    "model": settings.LONG_TERM_MEMORY_MODEL,
                    "api_key": settings.GOOGLE_API_KEY,
                },
            }
        else:
            llm = {
                "provider": "openai",
                "config": {
                    "model": settings.LONG_TERM_MEMORY_MODEL,
                    "openai_api_key": settings.OPENAI_API_KEY,
                },
            }

        # Embedder：优先 OpenAI，降级 Gemini，两者都无则禁用记忆
        if settings.OPENAI_API_KEY:
            embedder = {
                "provider": "openai",
                "config": {
                    "model": settings.LONG_TERM_MEMORY_EMBEDDER_MODEL,
                    "openai_api_key": settings.OPENAI_API_KEY,
                },
            }
        elif settings.GOOGLE_API_KEY:
            embedder = {
                "provider": "gemini",
                "config": {"model": "models/text-embedding-004", "api_key": settings.GOOGLE_API_KEY},
            }
        else:
            return None

        return {"vector_store": vector_store, "llm": llm, "embedder": embedder}

    async def _get_memory(self) -> AsyncMemory | None:
        if self._disabled:
            return None
        if self._memory is None:
            config = self._build_config()
            if config is None:
                self._disabled = True
                logger.warning("memory_service_disabled_no_embedder_configured")
                return None
            self._memory = await AsyncMemory.from_config(config_dict=config)
        return self._memory

    async def initialize(self) -> None:
        """Pre-warm the mem0 AsyncMemory instance at startup."""
        result = await self._get_memory()
        if result is not None:
            logger.info("memory_service_initialized")
        else:
            logger.warning("memory_service_disabled", reason="no_embedder_api_key")

    async def search(self, user_id: str | None, query: str) -> str:
        """Search relevant memories for a user.

        Returns formatted memory string, or empty string on failure or when
        no user_id / no embedder is available.
        """
        if user_id is None:
            return ""
        try:
            key = cache_key("memory", str(user_id), query)
            cached = await cache_service.get(key)
            if cached is not None:
                logger.debug("memory_search_cache_hit", user_id=user_id)
                return cached

            memory = await self._get_memory()
            if memory is None:
                return ""
            results = await memory.search(user_id=str(user_id), query=query)
            result = "\n".join([f"* {r['memory']}" for r in results["results"]])

            if result:
                await cache_service.set(key, result)

            return result
        except Exception as e:
            logger.error("failed_to_get_relevant_memory", error=str(e), user_id=user_id, query=query)
            return ""

    async def add(self, user_id: str | None, messages: list[dict], metadata: dict | None = None) -> None:
        """Add messages to long-term memory for a user."""
        if user_id is None:
            return
        try:
            memory = await self._get_memory()
            if memory is None:
                return
            await memory.add(messages, user_id=str(user_id), metadata=metadata)
            logger.info("long_term_memory_updated_successfully", user_id=user_id)
        except Exception as e:
            logger.exception("failed_to_update_long_term_memory", user_id=user_id, error=str(e))


memory_service = MemoryService()
