"""内置词库读取逻辑与内置数据完整性测试。"""
from app.services.vocabulary import libraries as library_service
from app.services.vocabulary.words import filter_new_words

_REQUIRED_FIELDS = {
    "word",
    "phonetic_ipa",
    "part_of_speech",
    "definition_zh",
    "etymology",
    "example_sentence",
}


def test_list_groups_has_expected_structure():
    groups = library_service.list_groups()
    assert len(groups) == 8
    keys = [g["key"] for g in groups]
    assert keys == ["primary", "junior", "senior", "cet", "kaoyan", "tem", "overseas", "business"]
    for group in groups:
        assert group["books"]
        for book in group["books"]:
            assert book["id"] and book["title"]
            assert book["word_count"] > 0


def test_get_book_meta_known_and_unknown():
    meta = library_service.get_book_meta("CET4luan_1")
    assert meta is not None
    assert meta["group_key"] == "cet"
    assert meta["title"] == "四级真题核心词"
    assert library_service.get_book_meta("does_not_exist") is None


def test_book_words_match_manifest_count_and_have_required_fields():
    """每本词库文件都存在，词数与 manifest 声明一致，且字段齐全。"""
    for group in library_service.list_groups():
        for book in group["books"]:
            words = library_service.get_book_words(book["id"])
            assert len(words) == book["word_count"], book["id"]
            first = words[0]
            assert _REQUIRED_FIELDS <= set(first.keys())
            # 必填字段（对应生词库 NOT NULL 列）不为空
            assert first["word"]
            assert first["definition_zh"]


def test_book_words_are_deduplicated_within_book():
    """同一本内不应出现大小写不敏感重复的单词。"""
    words = library_service.get_book_words("CET4luan_1")
    lowered = [w["word"].lower() for w in words]
    assert len(lowered) == len(set(lowered))


def test_book_words_respect_column_length_limits():
    """导出词条不得超过 VocabularyWord 各列 max_length，否则写库会报错。"""
    words = library_service.get_book_words("Level8luan_2")  # 最大的一本
    for w in words:
        assert len(w["word"]) <= 100
        assert len(w["phonetic_ipa"]) <= 100
        assert len(w["part_of_speech"]) <= 20
        assert len(w["definition_zh"]) <= 500
        assert len(w["etymology"]) <= 500
        assert len(w["example_sentence"]) <= 1000


def test_unknown_book_returns_empty_words():
    assert library_service.get_book_words("does_not_exist") == ()


def test_library_words_compatible_with_dedup_helper():
    """内置词条能被生词库去重函数正常处理（导入链路的关键前置）。"""
    words = library_service.get_book_words("PEPXiaoXue3_1")
    candidates = [w["word"] for w in words]
    # 生词库为空时全部视为新词
    assert filter_new_words(set(), candidates) == candidates
    # 已存在首词时应被过滤掉
    filtered = filter_new_words({candidates[0]}, candidates)
    assert candidates[0].lower() not in {w.lower() for w in filtered}
