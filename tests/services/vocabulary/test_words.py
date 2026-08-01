"""生词库去重逻辑单元测试。"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from app.schemas.vocabulary import WordsBatchDeleteRequest
from app.services.vocabulary.words import delete_words_batch, filter_new_words


def test_filter_new_words_excludes_existing_case_insensitive():
    existing = {"Apple", "Resilient"}
    candidates = ["apple", "Paradigm", "RESILIENT", "banana"]
    result = filter_new_words(existing, candidates)
    assert result == ["Paradigm", "banana"]


def test_filter_new_words_dedupes_within_candidates():
    existing: set[str] = set()
    candidates = ["apple", "Apple", "APPLE", "banana"]
    result = filter_new_words(existing, candidates)
    assert result == ["apple", "banana"]


def test_filter_new_words_returns_empty_when_all_exist():
    existing = {"apple", "banana"}
    candidates = ["Apple", "BANANA"]
    result = filter_new_words(existing, candidates)
    assert result == []


async def test_delete_words_batch_uses_one_transaction_for_all_owned_ids():
    user_id = uuid.uuid4()
    first_id = uuid.uuid4()
    second_id = uuid.uuid4()
    owned_result = MagicMock()
    owned_result.scalars.return_value.all.return_value = [first_id, second_id]
    session = AsyncMock()
    session.execute.side_effect = [owned_result, MagicMock(), MagicMock(), MagicMock()]

    deleted_count = await delete_words_batch(
        session,
        user_id,
        [first_id, second_id, first_id],
    )

    assert deleted_count == 2
    assert session.execute.await_count == 4
    session.commit.assert_awaited_once()

    statements = [str(call.args[0]) for call in session.execute.await_args_list]
    assert "vocabulary_review_logs" in statements[1]
    assert "vocabulary_playlist_items" in statements[2]
    assert "DELETE FROM vocabulary_words" in statements[3]


async def test_delete_words_batch_is_idempotent_when_ids_no_longer_exist():
    owned_result = MagicMock()
    owned_result.scalars.return_value.all.return_value = []
    session = AsyncMock()
    session.execute.return_value = owned_result

    deleted_count = await delete_words_batch(
        session,
        uuid.uuid4(),
        [uuid.uuid4()],
    )

    assert deleted_count == 0
    session.execute.assert_awaited_once()
    session.commit.assert_not_awaited()


def test_batch_delete_request_limits_each_transaction_to_5000_ids():
    with pytest.raises(ValidationError):
        WordsBatchDeleteRequest(word_ids=[uuid.uuid4() for _ in range(5001)])
