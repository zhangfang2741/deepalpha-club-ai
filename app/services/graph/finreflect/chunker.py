"""表格感知语义切片（论文 4.2 节 Table-Aware Semantic Chunking）。

论文要点：
- 任何检测到的表格**独立保留为单个原子 chunk**，行列关系与财务数据
  上下文永不被切断（10-K 的关键量化披露多在表格中）。
- 普通文本采用 section-aware 切分：优先在段落/小节标题等逻辑边界断开，
  保持主题连贯；段落过长时退化到句子边界。
- 单 chunk 上限 CHUNK_SIZE = 2048 tokens。
"""

import re

# 论文 4.2：CHUNK_SIZE = 2048
CHUNK_SIZE_TOKENS = 2048

# token 数估算：字符数 / 4（与主流水线一致）
_CHARS_PER_TOKEN = 4

_HTML_TABLE_RE = re.compile(r"<table\b.*?</table>", re.IGNORECASE | re.DOTALL)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
# 段落/小节边界：空行或 markdown 标题行
_PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n|\n(?=#{1,6}\s)")


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


def _split_text_units(block: str, char_limit: int) -> list[str]:
    """将普通文本块切成累积单元：先段落/标题边界，超限段落再退化到句子。"""
    units: list[str] = []
    for para in _PARAGRAPH_SPLIT_RE.split(block):
        para = para.strip()
        if not para:
            continue
        if len(para) <= char_limit:
            units.append(para)
        else:
            units.extend(s for s in _SENTENCE_SPLIT_RE.split(para) if s.strip())
    return units


def chunk_document(text: str, max_tokens: int = CHUNK_SIZE_TOKENS) -> list[str]:
    """表格感知语义切片。

    表格块独立成 chunk（原子，永不切分）；普通文本在段落/小节边界累积，
    超长段落退化到句子边界。

    Args:
        text: 文档全文（可含 Markdown/HTML 表格）
        max_tokens: 单 chunk 目标 token 上限（论文默认 2048）

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
            # 论文：表格独立保留为单个原子 chunk
            _flush()
            chunks.append(block)
            continue

        for unit in _split_text_units(block, char_limit):
            if current and len(current) + len(unit) + 1 > char_limit:
                _flush()
            current = f"{current}\n{unit}".strip() if current else unit

    _flush()
    return chunks
