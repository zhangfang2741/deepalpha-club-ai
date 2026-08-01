"""歌单词表校验逻辑单元测试。"""
import uuid

from app.services.vocabulary.playlists import dedupe_word_ids


def _ids(n: int) -> list[uuid.UUID]:
    return [uuid.uuid4() for _ in range(n)]


def test_dedupe_word_ids_preserves_input_order():
    a, b, c = _ids(3)
    owned = {a, b, c}
    assert dedupe_word_ids([c, a, b], owned) == [c, a, b]


def test_dedupe_word_ids_keeps_first_occurrence():
    a, b = _ids(2)
    owned = {a, b}
    assert dedupe_word_ids([a, b, a, b, a], owned) == [a, b]


def test_dedupe_word_ids_drops_ids_not_owned():
    a, b = _ids(2)
    foreign = uuid.uuid4()
    assert dedupe_word_ids([a, foreign, b], {a, b}) == [a, b]


def test_dedupe_word_ids_returns_empty_when_nothing_owned():
    assert dedupe_word_ids(_ids(3), set()) == []


def test_dedupe_word_ids_handles_empty_input():
    assert dedupe_word_ids([], {uuid.uuid4()}) == []
