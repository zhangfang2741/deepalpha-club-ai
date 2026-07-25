"""生词库去重逻辑单元测试。"""
from app.services.vocabulary.words import filter_new_words


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
