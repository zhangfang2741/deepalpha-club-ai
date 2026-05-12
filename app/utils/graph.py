"""This file contains the graph utilities for the application."""

import tiktoken
from langchain_core.messages import BaseMessage
from langchain_core.messages import trim_messages as _trim_messages

from app.core.config import settings
from app.core.logging import logger
from app.schemas import Message

# Cache tiktoken encoding at module level — thread-safe and reusable
_TIKTOKEN_ENCODING = None
try:
    _TIKTOKEN_ENCODING = tiktoken.encoding_for_model(settings.DEFAULT_LLM_MODEL)
except KeyError:
    try:
        _TIKTOKEN_ENCODING = tiktoken.get_encoding("cl100k_base")
    except Exception:
        logger.warning("tiktoken_encoding_unavailable_using_char_fallback")


def _count_tokens_tiktoken(messages: list) -> int:
    """Count tokens locally using tiktoken — no API call needed."""

    def _encode_len(text: str) -> int:
        if _TIKTOKEN_ENCODING is not None:
            return len(_TIKTOKEN_ENCODING.encode(text))
        return len(text) // 4  # rough char-based fallback (~4 chars per token)

    num_tokens = 0
    for message in messages:
        # Every message has overhead tokens for role/name
        num_tokens += 4
        if isinstance(message, dict):
            for _, value in message.items():
                if isinstance(value, str):
                    num_tokens += _encode_len(value)
        elif isinstance(message, BaseMessage):
            content = message.content
            if isinstance(content, str):
                num_tokens += _encode_len(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, str):
                        num_tokens += _encode_len(block)
                    elif isinstance(block, dict) and "text" in block:
                        num_tokens += _encode_len(block["text"])
    num_tokens += 2  # every reply is primed with assistant
    return num_tokens


def dump_messages(messages: list[Message]) -> list[dict]:
    """Dump the messages to a list of dictionaries.

    Args:
        messages (list[Message]): The messages to dump.

    Returns:
        list[dict]: The dumped messages.
    """
    return [message.model_dump() for message in messages]


def extract_text_content(content: str | list) -> str:
    """Extract plain text from an LLM content value.

    Handles both the simple string format and the structured block list returned
    by GPT-5 / Responses API models:
        [{'type': 'reasoning', ...}, {'type': 'text', 'text': '...'}]

    Args:
        content: Raw content from a LangChain BaseMessage.

    Returns:
        Plain text string (empty string when nothing extractable is present).
    """
    if isinstance(content, str):
        return content

    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict):
            if block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif block.get("type") == "reasoning":
                logger.debug(
                    "reasoning_block_received",
                    reasoning_id=block.get("id"),
                    has_summary=bool(block.get("summary")),
                )
    return "".join(parts)


def process_llm_response(response: BaseMessage) -> BaseMessage:
    """Normalise a raw LLM response so that ``response.content`` is always a plain string, regardless of the provider's content format.

    Args:
        response: The raw response from the LLM.

    Returns:
        The same BaseMessage instance with ``content`` set to a plain string.
    """
    if isinstance(response.content, list):
        response.content = extract_text_content(response.content)
        logger.debug(
            "processed_structured_content",
            content_block_count=len(response.content),
            extracted_length=len(response.content),
        )
    return response


def prepare_messages(messages: list[Message], system_prompt: str) -> list[Message]:
    """Prepare the messages for the LLM.

    Args:
        messages (list[Message]): The messages to prepare.
        system_prompt (str): The system prompt to use.

    Returns:
        list[Message]: The prepared messages.
    """
    try:
        trimmed_messages = _trim_messages(
            dump_messages(messages),
            strategy="last",
            token_counter=_count_tokens_tiktoken,
            max_tokens=settings.MAX_TOKENS,
            start_on="human",
            include_system=False,
            allow_partial=False,
        )
    except ValueError as e:
        # Handle unrecognized content blocks (e.g., reasoning blocks from GPT-5)
        if "Unrecognized content block type" in str(e):
            logger.warning(
                "token_counting_failed_skipping_trim",
                error=str(e),
                message_count=len(messages),
            )
            # Skip trimming and return all messages
            trimmed_messages = messages
        else:
            raise

    return [Message(role="system", content=system_prompt)] + trimmed_messages
