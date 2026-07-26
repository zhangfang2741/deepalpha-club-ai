"""LLM 拍照识别单词服务单元测试（mock llm_service.call，不触网）。

识别流程是两阶段：先看图识别出单词列表（_IdentifyResult），再把词表切成小批
并发丰富出 IPA/释义/词根/例句（_RecognizeResult）。mock 按 response_format
分流，模拟这两个阶段各自的行为。
"""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.services.vocabulary.recognizer import (
    _ENRICH_CHUNK_SIZE,
    _IDENTIFY_PROMPT,
    RecognitionFailedError,
    RecognizedWord,
    _build_identify_prompt,
    _IdentifyResult,
    _RecognizeResult,
    recognize_words_from_image,
)


def _mock_llm_call(identify_words: list[str], enrich_words: list[RecognizedWord] | None = None) -> AsyncMock:
    """构造一个按 response_format 分流的 mock。

    identify 阶段返回词列表；enrich 阶段默认把每个词原样回填成只有 word
    字段的实例，也可以指定 enrich_words 覆盖返回内容。
    """

    async def _call(*args, response_format=None, **kwargs):
        if response_format is _IdentifyResult:
            return _IdentifyResult(words=identify_words)
        words = enrich_words if enrich_words is not None else [RecognizedWord(word=w) for w in identify_words]
        return _RecognizeResult(words=words)

    return AsyncMock(side_effect=_call)


async def test_recognize_words_returns_parsed_candidates():
    enrich_words = [
        RecognizedWord(
            word="resilient",
            phonetic_ipa="rɪˈzɪliənt",
            part_of_speech="adj.",
            definition_zh="有韧性的",
        )
    ]
    call = _mock_llm_call(["resilient"], enrich_words)
    with patch("app.services.vocabulary.recognizer.llm_service.call", new=call):
        words = await recognize_words_from_image(b"fake-image-bytes")

    assert len(words) == 1
    assert words[0].word == "resilient"
    assert words[0].phonetic_ipa == "rɪˈzɪliənt"
    assert words[0].part_of_speech == "adj."


async def test_recognize_words_returns_empty_list_when_no_words_found():
    call = _mock_llm_call([])
    with patch("app.services.vocabulary.recognizer.llm_service.call", new=call):
        words = await recognize_words_from_image(b"fake-image-bytes")

    assert words == []


async def test_recognize_words_raises_on_llm_failure():
    """识别阶段（看图识词）彻底失败时，整体应该报错——这一步没有兜底可退。"""
    with patch(
        "app.services.vocabulary.recognizer.llm_service.call",
        new=AsyncMock(side_effect=RuntimeError("llm down")),
    ):
        with pytest.raises(RecognitionFailedError):
            await recognize_words_from_image(b"fake-image-bytes")


async def test_enrich_chunk_failure_falls_back_to_bare_word():
    """丰富阶段调用彻底失败不应该让整个识别报错。

    那个词应该带只有 word 字段的兜底实例出现在结果里（重试耗尽后回退），
    而不是让用户拿到一个 502。
    """

    async def _call(*args, response_format=None, **kwargs):
        if response_format is _IdentifyResult:
            return _IdentifyResult(words=["resilient"])
        raise RuntimeError("enrich llm down")

    with patch("app.services.vocabulary.recognizer.llm_service.call", new=AsyncMock(side_effect=_call)):
        words = await recognize_words_from_image(b"fake-image-bytes")

    assert len(words) == 1
    assert words[0].word == "resilient"
    assert words[0].definition_zh == ""


async def test_enrich_missing_word_in_response_falls_back_to_bare_word():
    """丰富阶段返回结果里如果漏了某个词，也要用兜底实例补回去。

    不能让那个词直接从结果里消失。
    """
    enrich_words = [RecognizedWord(word="resilient", definition_zh="有韧性的")]
    call = _mock_llm_call(["resilient", "serendipity"], enrich_words)
    with patch("app.services.vocabulary.recognizer.llm_service.call", new=call):
        words = await recognize_words_from_image(b"fake-image-bytes")

    by_word = {w.word: w for w in words}
    assert set(by_word) == {"resilient", "serendipity"}
    assert by_word["resilient"].definition_zh == "有韧性的"
    assert by_word["serendipity"].definition_zh == ""


async def test_recognize_splits_large_word_list_into_chunks():
    """识别出的词超过一批的大小时应该分批并发丰富，且所有词都要出现在结果里。

    这是修复"一张图 100+ 词只识别出 30 多个"那个 bug 的核心行为：之前一次性
    调用在 max_tokens 预算耗尽后被截断，分批后单次调用的输出量可控。
    """
    identify_words = [f"word{i}" for i in range(_ENRICH_CHUNK_SIZE * 2 + 3)]

    async def _call(*args, response_format=None, **kwargs):
        if response_format is _IdentifyResult:
            return _IdentifyResult(words=identify_words)
        return _RecognizeResult(words=[])

    mock = AsyncMock(side_effect=_call)
    with patch("app.services.vocabulary.recognizer.llm_service.call", new=mock):
        words = await recognize_words_from_image(b"fake-image-bytes")

    enrich_calls = [c for c in mock.call_args_list if c.kwargs.get("response_format") is _RecognizeResult]
    # 首轮 19 词 / 8 一批 = 3 批；这里 enrich 返回空会触发重试，所以总次数会 > 3。
    # 关键是：3 批首轮调用发生了（不是 1 次超大调用），所有识别出的词都还在结果里。
    assert len(enrich_calls) >= 3
    # enrich mock 对每批都返回空列表，靠兜底实例补全，数量应该还是跟识别出的一样多。
    assert len(words) == len(identify_words)


def test_build_identify_prompt_without_hint_is_base_prompt():
    # 无 OCR 线索（None / 空 / 全空白）时退化为纯看图识别的基础 prompt。
    assert _build_identify_prompt(None) == _IDENTIFY_PROMPT
    assert _build_identify_prompt([]) == _IDENTIFY_PROMPT
    assert _build_identify_prompt(["", "  "]) == _IDENTIFY_PROMPT


def test_build_identify_prompt_appends_hint_words():
    prompt = _build_identify_prompt(["resilient", " ", "serendipity"])
    # 过滤空白后把候选词拼进去，并保留「综合取并集」的指令。
    assert "resilient, serendipity" in prompt
    assert "综合取并集" in prompt


def test_identify_prompt_states_proper_noun_and_compound_rules():
    prompt = _build_identify_prompt(None)
    # 专有名词排除规则。
    assert "专有名词" in prompt
    assert "Google" in prompt and "TikTok" in prompt
    # 连字符复合词整体收录、空格词组拆成实义词。
    assert "e-commerce" in prompt
    assert "拆" in prompt


def test_ocr_hint_reasserts_exclusion_rules_after_union():
    prompt = _build_identify_prompt(["Google", "the", "engine"])
    # 并集之后，排除规则（含专有名词）仍然适用，避免 OCR 线索把 Google 强行带回。
    assert "综合取并集" in prompt
    assert "专有名词" in prompt


async def test_recognize_passes_ocr_hint_into_identify_prompt():
    call = _mock_llm_call(["resilient"])
    with patch("app.services.vocabulary.recognizer.llm_service.call", new=call):
        await recognize_words_from_image(b"fake-image-bytes", ocr_hint=["serendipity"])

    # OCR 候选词应出现在发给 LLM 的图文消息的文本块里（第一次调用，即识别阶段）。
    sent_message = call.await_args_list[0].args[0][0]
    text_block = next(part["text"] for part in sent_message.content if part["type"] == "text")
    assert "serendipity" in text_block


async def test_retry_fills_in_words_skipped_by_first_pass():
    """首轮丰富后还有词 definition_zh 为空（模型"系统跳过"），重试应只针对这些词。

    这是 120 词雅思词表识别不全的根因：模型对 idea/world/third 这种简单词常
    直接不写。重试换一批"上下文压力"之后大概率能补上。
    """
    identified = ["idea", "world", "serendipity"]

    async def _call(*args, response_format=None, **_kwargs):
        if response_format is _IdentifyResult:
            return _IdentifyResult(words=identified)
        if response_format is _RecognizeResult:
            messages = args[0]
            text = messages[0].content if isinstance(messages[0].content, str) else ""
            # 重试批次的 prompt 里只该出现首轮被跳过的词——重试里只剩 world 一个词，
            # 首轮里是三个都在。这里靠抽取 "N. word" 模式列出本批包含的词来判断。
            batch_words = [line.split(". ", 1)[1] for line in text.splitlines() if ". " in line]
            # 重试批次（只剩漏的词）
            if set(batch_words) == {"world"}:
                return _RecognizeResult(words=[RecognizedWord(word="world", definition_zh="世界")])
            # 首轮：只填两个，故意把 world 留空模拟模型跳过
            return _RecognizeResult(
                words=[
                    RecognizedWord(word="idea", definition_zh="想法"),
                    RecognizedWord(word="serendipity", definition_zh="意外的好运"),
                ]
            )

    call = AsyncMock(side_effect=_call)
    with patch("app.services.vocabulary.recognizer.llm_service.call", new=call):
        words = await recognize_words_from_image(b"fake-image-bytes")

    by_word = {w.word: w for w in words}
    assert by_word["idea"].definition_zh == "想法"
    assert by_word["serendipity"].definition_zh == "意外的好运"
    # 重试后被跳过的 world 也应被补上
    assert by_word["world"].definition_zh == "世界"


async def test_on_partial_called_once_per_chunk_as_it_completes():
    """on_partial 应该在每个 enrich chunk 完成时就回调一次，而不是等首轮全部跑完。

    这是修复"124 词的图，第一批进度要等 50+ 秒才出现"这个体验问题的核心行为：
    124 词按 8 一批要分 16 批，并发上限 4，等*全部*批次跑完往往要几十秒；改成
    每批一跑完就报进度，用户几秒钟就能看到数字往上跳，不用干等一整轮。
    """
    identified = [f"word{i}" for i in range(_ENRICH_CHUNK_SIZE * 2)]  # 两个首轮 chunk
    chunk1 = set(identified[:_ENRICH_CHUNK_SIZE])
    chunk2 = set(identified[_ENRICH_CHUNK_SIZE:])

    async def _call(*args, response_format=None, **kwargs):
        if response_format is _IdentifyResult:
            return _IdentifyResult(words=identified)
        messages = args[0]
        text = messages[0].content if isinstance(messages[0].content, str) else ""
        batch_words = {line.split(". ", 1)[1] for line in text.splitlines() if ". " in line}
        if batch_words == chunk2:
            # chunk2 故意慢一点跑完，让 chunk1 的回调先发生，测试断言才有确定的顺序。
            await asyncio.sleep(0.02)
        return _RecognizeResult(words=[RecognizedWord(word=w, definition_zh=f"释义:{w}") for w in batch_words])

    call = AsyncMock(side_effect=_call)
    snapshots: list[list[RecognizedWord]] = []
    with patch("app.services.vocabulary.recognizer.llm_service.call", new=call):
        words = await recognize_words_from_image(b"fake-image-bytes", on_partial=snapshots.append)

    # chunk1 完成时只应该看到 chunk1 的 8 个词；chunk2 完成时（累积）应该看到全部 16 个；
    # 最后再补一次跟最终结果一致的收尾回调。
    assert len(snapshots) == 3
    assert {w.word for w in snapshots[0]} == chunk1
    assert {w.word for w in snapshots[1]} == chunk1 | chunk2
    assert {w.word for w in snapshots[2]} == chunk1 | chunk2
    assert {w.word for w in words} == chunk1 | chunk2


async def test_on_partial_called_per_retry_chunk_too():
    """漏词重试阶段也要按 chunk 逐个回调进度，不是等整轮重试跑完才报一次。"""
    identified = ["idea", "world"]

    async def _call(*args, response_format=None, **kwargs):
        if response_format is _IdentifyResult:
            return _IdentifyResult(words=identified)
        # 首轮把 world 留空，触发一轮重试；重试轮把 world 填上。
        messages = args[0]
        text = messages[0].content if isinstance(messages[0].content, str) else ""
        batch_words = [line.split(". ", 1)[1] for line in text.splitlines() if ". " in line]
        if batch_words == ["world"]:
            return _RecognizeResult(words=[RecognizedWord(word="world", definition_zh="世界")])
        return _RecognizeResult(
            words=[
                RecognizedWord(word="idea", definition_zh="想法"),
                RecognizedWord(word="world"),
            ]
        )

    call = AsyncMock(side_effect=_call)
    snapshots: list[list[RecognizedWord]] = []
    with patch("app.services.vocabulary.recognizer.llm_service.call", new=call):
        words = await recognize_words_from_image(b"fake-image-bytes", on_partial=snapshots.append)

    # 首轮 1 个 chunk 完成一次 + 重试 1 个 chunk 完成一次 + 最终收尾一次 = 3 次
    assert len(snapshots) == 3
    first_pass_words = {w.word: w.definition_zh for w in snapshots[0]}
    assert first_pass_words == {"idea": "想法", "world": ""}
    after_retry_words = {w.word: w.definition_zh for w in snapshots[1]}
    assert after_retry_words == {"idea": "想法", "world": "世界"}
    final_words = {w.word: w.definition_zh for w in snapshots[2]}
    assert final_words == {"idea": "想法", "world": "世界"}
    assert {w.word: w.definition_zh for w in words} == final_words


async def test_on_partial_called_once_with_empty_list_when_no_words_found():
    call = _mock_llm_call([])
    snapshots: list[list[RecognizedWord]] = []
    with patch("app.services.vocabulary.recognizer.llm_service.call", new=call):
        await recognize_words_from_image(b"fake-image-bytes", on_partial=snapshots.append)

    assert snapshots == [[]]


async def test_retry_skipped_when_first_pass_fills_all_words():
    """首轮丰富就全部填满了，就不应该再发重试请求。"""
    identified = ["idea", "world"]

    async def _call(*args, response_format=None, **kwargs):
        if response_format is _IdentifyResult:
            return _IdentifyResult(words=identified)
        return _RecognizeResult(
            words=[
                RecognizedWord(word="idea", definition_zh="想法"),
                RecognizedWord(word="world", definition_zh="世界"),
            ]
        )

    call = AsyncMock(side_effect=_call)
    with patch("app.services.vocabulary.recognizer.llm_service.call", new=call):
        await recognize_words_from_image(b"fake-image-bytes")

    enrich_calls = [c for c in call.call_args_list if c.kwargs.get("response_format") is _RecognizeResult]
    # 只有首轮那一次丰富调用
    assert len(enrich_calls) == 1


async def test_retry_capped_at_max_rounds_even_if_words_stay_empty():
    """重试封顶：模型持续跳过同一个词时，应停止再调，不能无限循环。"""
    identified = ["stubborn_word"]

    async def _call(*args, response_format=None, **kwargs):
        if response_format is _IdentifyResult:
            return _IdentifyResult(words=identified)
        # 首轮和所有重试都故意返回空 definition_zh，模拟模型顽固跳过。
        return _RecognizeResult(words=[RecognizedWord(word="stubborn_word")])

    call = AsyncMock(side_effect=_call)
    with patch("app.services.vocabulary.recognizer.recognizer.llm_service.call" if False else "app.services.vocabulary.recognizer.llm_service.call", new=call):
        words = await recognize_words_from_image(b"fake-image-bytes")

    enrich_calls = [c for c in call.call_args_list if c.kwargs.get("response_format") is _RecognizeResult]
    # 1 次首轮 + 最多 2 轮重试 = 最多 3 次丰富调用
    from app.services.vocabulary.recognizer import _ENRICH_MAX_RETRIES
    assert len(enrich_calls) <= 1 + _ENRICH_MAX_RETRIES
    # 词仍在，但 definition_zh 留空，不能因为模型顽固跳过就把词丢了。
    assert len(words) == 1
    assert words[0].word == "stubborn_word"
    assert words[0].definition_zh == ""


async def test_120_word_ielts_table_end_to_end_with_retry_recovers_skipped_words():
    """模拟用户那张 120 词雅思词表真图的实际场景。

    识别阶段返回 120 个词；首轮丰富模拟模型对若干简单词（典型：idea/world/Tuesday）
    "系统跳过"，留空 definition_zh；预期重试会把这些词补齐，最终结果 120 个全在，
    释义完整的词数量等于识别出的词数。
    """
    identified = [f"word{i}" for i in range(120)]
    # 模拟模型顽固跳过的"简单词"：每 7 个留一个空（120 个里约 17 个），刚好覆盖
    # 之前观察到的"~12% 漏"那一档，作为重试必须兜底的尾部。
    skipped = {w for i, w in enumerate(identified) if i % 7 == 0}

    async def _call(*args, response_format=None, **kwargs):
        if response_format is _IdentifyResult:
            return _IdentifyResult(words=identified)
        # 从 prompt 编号行里抽出本批包含的词。
        messages = args[0]
        text = messages[0].content if isinstance(messages[0].content, str) else ""
        batch_words = [line.split(". ", 1)[1] for line in text.splitlines() if ". " in line]
        batch_set = set(batch_words)
        # 重试批次的特征：本批里所有词都是之前跳过的——重试只针对漏词；
        # 首轮包含全部词。
        if batch_set and batch_set <= skipped:
            # 重试：模拟模型这次"心情好了"全填上
            return _RecognizeResult(
                words=[RecognizedWord(word=w, definition_zh=f"释义:{w}") for w in batch_words]
            )
        # 首轮：跳过集留空，其它词填上
        return _RecognizeResult(
            words=[
                RecognizedWord(word=w, definition_zh="" if w in skipped else f"释义:{w}")
                for w in batch_words
            ]
        )

    call = AsyncMock(side_effect=_call)
    with patch("app.services.vocabulary.recognizer.llm_service.call", new=call):
        words = await recognize_words_from_image(b"fake-image-bytes")

    by_word = {w.word: w for w in words}
    # 120 个词一个都不能丢
    assert len(by_word) == 120
    # 重试后所有词的 definition_zh 都应被补齐
    empty = [w for w, rw in by_word.items() if not rw.definition_zh]
    assert empty == [], f"重试后仍有 {len(empty)} 个词释义为空: {empty[:5]}"
