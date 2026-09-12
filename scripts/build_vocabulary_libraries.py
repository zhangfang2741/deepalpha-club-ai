#!/usr/bin/env python3
"""构建 WordLens 内置词库数据。

从 kajweb/dict（数据源为有道词典离线包）下载精选词库，转换成 WordLens 生词库
所需的精简字段，落地到 app/data/vocabulary_libraries/ 供后端运行时读取。

- 只保留 42 本「精选核心」词库（每个考试/阶段取最具代表性的 1~2 本；基础教育
  阶段保留人教版整套年级进度），按学习阶段/考试类型分成 8 组。
- 每本词库导出成 <book_id>.json（精简 JSON 数组），另生成 manifest.json 汇总
  分组与每本的元信息（标题/词数），前端/iOS 只需拉 manifest 即可渲染选择列表。
- 字段映射（有道 -> VocabularyWord）：
    headWord                              -> word
    content.word.content.usphone/ukphone  -> phonetic_ipa（优先美音）
    content.word.content.trans[].pos       -> part_of_speech（首个词性）
    content.word.content.trans[].tranCn    -> definition_zh（拼成「pos. 释义」）
    content.word.content.remMethod.val     -> etymology（记忆法/词源，可空）
    content.word.content.sentence...sContent -> example_sentence（首个例句）

这是一次性/可重跑的离线脚本，不在生产运行路径上，允许直接用标准库网络请求。
用法：uv run python scripts/build_vocabulary_libraries.py
"""
from __future__ import annotations

import io
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

# 分组：(分组 key, 分组中文名, [book_id...])。顺序即前端展示顺序。
GROUPS: list[tuple[str, str, list[str]]] = [
    (
        "primary",
        "小学",
        [
            "PEPXiaoXue3_1", "PEPXiaoXue3_2", "PEPXiaoXue4_1", "PEPXiaoXue4_2",
            "PEPXiaoXue5_1", "PEPXiaoXue5_2", "PEPXiaoXue6_1", "PEPXiaoXue6_2",
        ],
    ),
    (
        "junior",
        "初中",
        [
            "PEPChuZhong7_1", "PEPChuZhong7_2", "PEPChuZhong8_1", "PEPChuZhong8_2",
            "PEPChuZhong9_1", "ChuZhongluan_2",
        ],
    ),
    (
        "senior",
        "高中",
        [
            "PEPGaoZhong_1", "PEPGaoZhong_2", "PEPGaoZhong_3", "PEPGaoZhong_4",
            "PEPGaoZhong_5", "PEPGaoZhong_6", "PEPGaoZhong_7", "PEPGaoZhong_8",
            "PEPGaoZhong_9", "PEPGaoZhong_10", "PEPGaoZhong_11", "GaoZhongluan_2",
        ],
    ),
    (
        "cet",
        "四六级",
        ["CET4luan_1", "CET4luan_2", "CET6luan_1", "CET6_2"],
    ),
    (
        "kaoyan",
        "考研",
        ["KaoYanluan_1", "KaoYan_2"],
    ),
    (
        "tem",
        "专四专八",
        ["Level4luan_1", "Level4luan_2", "Level8_1", "Level8luan_2"],
    ),
    (
        "overseas",
        "出国留学",
        ["IELTSluan_2", "TOEFL_2", "GRE_2", "SAT_2", "GMATluan_2"],
    ),
    (
        "business",
        "商务英语",
        ["BEC_2"],
    ),
]

# 每本词库的展示标题。
BOOK_TITLES: dict[str, str] = {
    "PEPXiaoXue3_1": "人教版小学英语·三年级上册",
    "PEPXiaoXue3_2": "人教版小学英语·三年级下册",
    "PEPXiaoXue4_1": "人教版小学英语·四年级上册",
    "PEPXiaoXue4_2": "人教版小学英语·四年级下册",
    "PEPXiaoXue5_1": "人教版小学英语·五年级上册",
    "PEPXiaoXue5_2": "人教版小学英语·五年级下册",
    "PEPXiaoXue6_1": "人教版小学英语·六年级上册",
    "PEPXiaoXue6_2": "人教版小学英语·六年级下册",
    "PEPChuZhong7_1": "人教版初中英语·七年级上册",
    "PEPChuZhong7_2": "人教版初中英语·七年级下册",
    "PEPChuZhong8_1": "人教版初中英语·八年级上册",
    "PEPChuZhong8_2": "人教版初中英语·八年级下册",
    "PEPChuZhong9_1": "人教版初中英语·九年级全册",
    "ChuZhongluan_2": "中考必备词汇",
    "PEPGaoZhong_1": "人教版高中英语·必修1",
    "PEPGaoZhong_2": "人教版高中英语·必修2",
    "PEPGaoZhong_3": "人教版高中英语·必修3",
    "PEPGaoZhong_4": "人教版高中英语·必修4",
    "PEPGaoZhong_5": "人教版高中英语·必修5",
    "PEPGaoZhong_6": "人教版高中英语·选修6",
    "PEPGaoZhong_7": "人教版高中英语·选修7",
    "PEPGaoZhong_8": "人教版高中英语·选修8",
    "PEPGaoZhong_9": "人教版高中英语·选修9",
    "PEPGaoZhong_10": "人教版高中英语·选修10",
    "PEPGaoZhong_11": "人教版高中英语·选修11",
    "GaoZhongluan_2": "高考必备词汇",
    "CET4luan_1": "四级真题核心词",
    "CET4luan_2": "四级英语词汇",
    "CET6luan_1": "六级真题核心词",
    "CET6_2": "六级英语词汇",
    "KaoYanluan_1": "考研必考词汇",
    "KaoYan_2": "考研英语词汇",
    "Level4luan_1": "专四真题高频词",
    "Level4luan_2": "专四核心词汇",
    "Level8_1": "专八真题高频词",
    "Level8luan_2": "专八核心词汇",
    "IELTSluan_2": "雅思词汇",
    "TOEFL_2": "TOEFL 词汇",
    "GRE_2": "GRE 词汇",
    "SAT_2": "SAT 词汇",
    "GMATluan_2": "GMAT 词汇",
    "BEC_2": "商务英语词汇",
}

# 有道离线包下载地址（数据源：kajweb/dict）。
BOOK_SOURCES: dict[str, str] = {
    "PEPXiaoXue3_1": "http://ydschool-online.nos.netease.com/1521164661774_PEPXiaoXue3_1.zip",
    "PEPXiaoXue3_2": "http://ydschool-online.nos.netease.com/1521164656604_PEPXiaoXue3_2.zip",
    "PEPXiaoXue4_1": "http://ydschool-online.nos.netease.com/1521164677447_PEPXiaoXue4_1.zip",
    "PEPXiaoXue4_2": "http://ydschool-online.nos.netease.com/1521164663086_PEPXiaoXue4_2.zip",
    "PEPXiaoXue5_1": "http://ydschool-online.nos.netease.com/1530101080610_PEPXiaoXue5_1.zip",
    "PEPXiaoXue5_2": "http://ydschool-online.nos.netease.com/1530101073491_PEPXiaoXue5_2.zip",
    "PEPXiaoXue6_1": "http://ydschool-online.nos.netease.com/1530101075331_PEPXiaoXue6_1.zip",
    "PEPXiaoXue6_2": "http://ydschool-online.nos.netease.com/1521164632445_PEPXiaoXue6_2.zip",
    "PEPChuZhong7_1": "http://ydschool-online.nos.netease.com/1530101067588_PEPChuZhong7_1.zip",
    "PEPChuZhong7_2": "http://ydschool-online.nos.netease.com/1521164677043_PEPChuZhong7_2.zip",
    "PEPChuZhong8_1": "http://ydschool-online.nos.netease.com/1530101070747_PEPChuZhong8_1.zip",
    "PEPChuZhong8_2": "http://ydschool-online.nos.netease.com/1521164666522_PEPChuZhong8_2.zip",
    "PEPChuZhong9_1": "http://ydschool-online.nos.netease.com/1530101078234_PEPChuZhong9_1.zip",
    "ChuZhongluan_2": "http://ydschool-online.nos.netease.com/1521164669076_ChuZhongluan_2.zip",
    "PEPGaoZhong_1": "http://ydschool-online.nos.netease.com/1521164674793_PEPGaoZhong_1.zip",
    "PEPGaoZhong_2": "http://ydschool-online.nos.netease.com/1521164678610_PEPGaoZhong_2.zip",
    "PEPGaoZhong_3": "http://ydschool-online.nos.netease.com/1521164676690_PEPGaoZhong_3.zip",
    "PEPGaoZhong_4": "http://ydschool-online.nos.netease.com/1521164657462_PEPGaoZhong_4.zip",
    "PEPGaoZhong_5": "http://ydschool-online.nos.netease.com/1521164657147_PEPGaoZhong_5.zip",
    "PEPGaoZhong_6": "http://ydschool-online.nos.netease.com/1521164629184_PEPGaoZhong_6.zip",
    "PEPGaoZhong_7": "http://ydschool-online.nos.netease.com/1521164648940_PEPGaoZhong_7.zip",
    "PEPGaoZhong_8": "http://ydschool-online.nos.netease.com/1521164666266_PEPGaoZhong_8.zip",
    "PEPGaoZhong_9": "http://ydschool-online.nos.netease.com/1521164670293_PEPGaoZhong_9.zip",
    "PEPGaoZhong_10": "http://ydschool-online.nos.netease.com/1521164634796_PEPGaoZhong_10.zip",
    "PEPGaoZhong_11": "http://ydschool-online.nos.netease.com/1521164639915_PEPGaoZhong_11.zip",
    "GaoZhongluan_2": "http://ydschool-online.nos.netease.com/1521164673602_GaoZhongluan_2.zip",
    "CET4luan_1": "http://ydschool-online.nos.netease.com/1523620217431_CET4luan_1.zip",
    "CET4luan_2": "http://ydschool-online.nos.netease.com/1524052539052_CET4luan_2.zip",
    "CET6luan_1": "http://ydschool-online.nos.netease.com/1521164660466_CET6luan_1.zip",
    "CET6_2": "http://ydschool-online.nos.netease.com/1524052554766_CET6_2.zip",
    "KaoYanluan_1": "http://ydschool-online.nos.netease.com/1521164661106_KaoYanluan_1.zip",
    "KaoYan_2": "http://ydschool-online.nos.netease.com/1521164654696_KaoYan_2.zip",
    "Level4luan_1": "http://ydschool-online.nos.netease.com/1521164630387_Level4luan_1.zip",
    "Level4luan_2": "http://ydschool-online.nos.netease.com/1521164625401_Level4luan_2.zip",
    "Level8_1": "http://ydschool-online.nos.netease.com/1521164635290_Level8_1.zip",
    "Level8luan_2": "http://ydschool-online.nos.netease.com/1521164650006_Level8luan_2.zip",
    "IELTSluan_2": "http://ydschool-online.nos.netease.com/1521164624473_IELTSluan_2.zip",
    "TOEFL_2": "http://ydschool-online.nos.netease.com/1521164640451_TOEFL_2.zip",
    "GRE_2": "http://ydschool-online.nos.netease.com/1521164637271_GRE_2.zip",
    "SAT_2": "http://ydschool-online.nos.netease.com/1521164670910_SAT_2.zip",
    "GMATluan_2": "http://ydschool-online.nos.netease.com/1521164629611_GMATluan_2.zip",
    "BEC_2": "http://ydschool-online.nos.netease.com/1521164626760_BEC_2.zip",
}

# VocabularyWord 各列的 max_length，导出时截断，避免运行时写库超长报错。
MAX_WORD = 100
MAX_PHONETIC = 100
MAX_POS = 20
MAX_DEFINITION = 500
MAX_ETYMOLOGY = 500
MAX_EXAMPLE = 1000

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "app" / "data" / "vocabulary_libraries"


def _clip(text: str, limit: int) -> str:
    """去首尾空白并按上限截断。"""
    text = (text or "").strip()
    return text[:limit]


def _build_definition(trans: list[dict]) -> str:
    """把多条释义拼成「pos. 释义；pos. 释义」，无词性则只放释义。"""
    parts: list[str] = []
    for t in trans:
        cn = (t.get("tranCn") or "").strip()
        if not cn:
            continue
        pos = (t.get("pos") or "").strip()
        parts.append(f"{pos}. {cn}" if pos else cn)
    return _clip("；".join(parts), MAX_DEFINITION)


def _transform_entry(entry: dict) -> dict | None:
    """把有道单条词表项转换成 WordLens 精简词条；无效则返回 None。"""
    head = (entry.get("headWord") or "").strip()
    if not head:
        return None
    content = (entry.get("content") or {}).get("word", {}).get("content", {})
    trans = content.get("trans") or []
    definition = _build_definition(trans)
    if not definition:
        return None  # 没有中文释义的条目对背单词无意义，跳过

    us = (content.get("usphone") or "").strip()
    uk = (content.get("ukphone") or "").strip()
    phonetic = us or uk

    pos = ""
    for t in trans:
        if (t.get("pos") or "").strip():
            pos = t["pos"].strip()
            break

    etymology = _clip((content.get("remMethod") or {}).get("val", ""), MAX_ETYMOLOGY)

    example = ""
    sentences = (content.get("sentence") or {}).get("sentences") or []
    if sentences:
        example = _clip(sentences[0].get("sContent", ""), MAX_EXAMPLE)

    return {
        "word": _clip(head, MAX_WORD),
        "phonetic_ipa": _clip(phonetic, MAX_PHONETIC),
        "part_of_speech": _clip(pos, MAX_POS),
        "definition_zh": definition,
        "etymology": etymology,
        "example_sentence": example,
    }


def _download_and_parse(book_id: str, url: str) -> list[dict]:
    """下载并解析一本词库，返回精简词条列表（内部按小写去重）。"""
    with urllib.request.urlopen(url, timeout=60) as resp:  # noqa: S310  离线构建脚本，源固定
        raw = resp.read()
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        name = next(n for n in zf.namelist() if n.endswith(".json"))
        text = zf.read(name).decode("utf-8")

    words: list[dict] = []
    seen: set[str] = set()
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        entry = json.loads(line)
        record = _transform_entry(entry)
        if record is None:
            continue
        key = record["word"].lower()
        if key in seen:
            continue
        seen.add(key)
        words.append(record)
    return words


def main() -> int:
    """下载全部精选词库、转换落地，并生成 manifest.json。"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest_groups: list[dict] = []

    for group_key, group_title, book_ids in GROUPS:
        books_meta: list[dict] = []
        for book_id in book_ids:
            url = BOOK_SOURCES[book_id]
            print(f"下载 {book_id} ...", flush=True)
            words = _download_and_parse(book_id, url)
            out_path = OUTPUT_DIR / f"{book_id}.json"
            out_path.write_text(
                json.dumps(words, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
            books_meta.append(
                {"id": book_id, "title": BOOK_TITLES[book_id], "word_count": len(words)}
            )
            print(f"  {book_id}: {len(words)} 词 -> {out_path.name}", flush=True)
        manifest_groups.append({"key": group_key, "title": group_title, "books": books_meta})

    manifest = {"groups": manifest_groups}
    (OUTPUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    total = sum(b["word_count"] for g in manifest_groups for b in g["books"])
    book_count = sum(len(g["books"]) for g in manifest_groups)
    print(f"完成：{book_count} 本词库，共 {total} 词，manifest.json 已生成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
