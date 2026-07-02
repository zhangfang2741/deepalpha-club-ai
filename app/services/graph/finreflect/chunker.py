"""表格感知切片（table-aware chunking）。

论文流水线的第一步：智能文档解析后按约定 token 预算切片，
且**不得截断表格**——10-K 中大量事实（财务指标、分部数据）存在于表格中，
表格被拦腰切断会导致抽取失真。

实现策略：
1. 先将文本划分为「表格块」与「普通文本块」：
   - Markdown 管道表格（连续以 ``|`` 开头/包含 ``|---|`` 分隔行的行）
   - HTML ``<table>...</table>`` 片段
2. 普通文本按句子边界累积；表格块视为原子单元整体放入 chunk。
3. 单个表格超过预算时不切分，独立成一个超额 chunk（保表格完整优先）。
"""

import re

# token 数估算：字符数 / 4（与主流水线一致）
_CHARS_PER_TOKEN = 4

_HTML_TABLE_RE = re.compile(r"<table\b.*?</table>", re.IGNORECASE | re.DOTALL)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _is_md_table_line(line: str) -> bool:
    """判断一行是否属于 Markdown 管道表格（含表头分隔行）。"""
    stripped = line.strip()
    if stripped.count("|") >= 2:
        return True
    return bool(re.fullmatch(r"\|?[\s:|-]+\|?", stripped)) and "-" in stripped


def _split_blocks(text: str) -> list[tuple[str, bool]]:
    """将文本切成 (块文本, 是否表格) 序列，表格块保持原子。"""
    blocks: list[tuple[str, bool]] = []

    # 先摘出 HTML 表格，剩余部分再按行扫描 Markdown 表格
    cursor = 0
    segments: list[tuple[str, bool]] = []
    for m in _HTML_TABLE_RE.finditer(text):
        if m.start() > cursor:
            segments.append((text[cursor : m.start()], False))
        segments.append((m.group(), True))
        cursor = m.end()
    if cursor < len(text):
        segments.append((text[cursor:], False))

    for segment, is_table in segments:
        if is_table:
            blocks.append((segment.strip(), True))
            continue

        # 行扫描聚合 Markdown 表格
        lines = segment.splitlines()
        buf_text: list[str] = []
        buf_table: list[str] = []
        for line in lines:
            if _is_md_table_line(line):
                if buf_text:
                    blocks.append(("\n".join(buf_text).strip(), False))
                    buf_text = []
                buf_table.append(line)
            else:
                if buf_table:
                    # 少于 2 行的"表格"多为误判（正文里带 | 的单行），并回普通文本
                    if len(buf_table) >= 2:
                        blocks.append(("\n".join(buf_table).strip(), True))
                    else:
                        buf_text.extend(buf_table)
                    buf_table = []
                buf_text.append(line)
        if buf_table:
            if len(buf_table) >= 2:
                blocks.append(("\n".join(buf_table).strip(), True))
            else:
                buf_text.extend(buf_table)
        if buf_text:
            blocks.append(("\n".join(buf_text).strip(), False))

    return [(b, t) for b, t in blocks if b]


def chunk_document(text: str, max_tokens: int = 1200) -> list[str]:
    """表格感知切片：普通文本按句子边界切，表格块保持完整。

    Args:
        text: 文档全文（可含 Markdown/HTML 表格）
        max_tokens: 单 chunk 目标 token 上限（估算值）

    Returns:
        chunk 文本列表
    """
    char_limit = max_tokens * _CHARS_PER_TOKEN
    chunks: list[str] = []
    current = ""

    def _flush() -> None:
        nonlocal current
        if current.strip():
            chunks.append(current.strip())
        current = ""

    for block, is_table in _split_blocks(text):
        if is_table:
            # 表格原子放置：放不下当前 chunk 就先落盘，再单独/继续容纳
            if current and len(current) + len(block) + 1 > char_limit:
                _flush()
            current = f"{current}\n{block}".strip() if current else block
            if len(current) >= char_limit:
                _flush()
            continue

        for sent in _SENTENCE_SPLIT_RE.split(block):
            if not sent.strip():
                continue
            if current and len(current) + len(sent) + 1 > char_limit:
                _flush()
            current = f"{current} {sent}".strip() if current else sent

    _flush()
    return chunks
