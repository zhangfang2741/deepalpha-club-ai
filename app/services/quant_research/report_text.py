"""从财报原文里挑出值得喂给大模型的几段：管理层讨论与分析（MD&A）+ 财务概要 / 利润表。

美股：SEC 网页文档（10-K / 10-Q / 20-F）；A 股 / 港股：PDF。整份财报几十万字，全喂既贵又容易漏重点，所以只取最有信息量的章节、
封顶约 3 万字。找不到章节标题时退回正文开头一段。纯函数，便于测试。
"""

from __future__ import annotations

import io
import re

from bs4 import BeautifulSoup

MAX_CHARS = 30_000
_SPACES = re.compile(r"[ \t\xa0 ​]+")

# ---------- 美股（SEC 网页） ----------

_US_START = {
    "10-K": re.compile(r"item\s*7\s*[\.\-–—:]?\s*management.{0,3}s\s+discussion\s+and\s+analysis", re.I),
    "10-Q": re.compile(r"item\s*2\s*[\.\-–—:]?\s*management.{0,3}s\s+discussion\s+and\s+analysis", re.I),
    "20-F": re.compile(r"item\s*5\s*[\.\-–—:]?\s*operating\s+and\s+financial\s+review", re.I),
    "40-F": re.compile(r"management.{0,3}s\s+discussion\s+and\s+analysis", re.I),
}
_US_END = {
    "10-K": re.compile(r"item\s*7a\s*[\.\-–—:]?\s*quantitative|item\s*8\s*[\.\-–—:]?\s*financial\s+statements", re.I),
    "10-Q": re.compile(r"item\s*3\s*[\.\-–—:]?\s*quantitative", re.I),
    "20-F": re.compile(r"item\s*6\s*[\.\-–—:]?\s*directors", re.I),
    "40-F": re.compile(r"controls\s+and\s+procedures", re.I),
}
_US_INCOME = re.compile(r"statements?\s+of\s+(?:consolidated\s+)?(?:operations|income|comprehensive\s+income)", re.I)


def html_to_text(html: str) -> str:
    """网页 → 纯文本（去脚本样式与 iXBRL 隐藏头），行内空白压成一个空格、空行去掉。"""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "ix:header"]):
        tag.decompose()
    text = soup.get_text("\n")
    lines = (_SPACES.sub(" ", ln).strip() for ln in text.split("\n"))
    return "\n".join(ln for ln in lines if ln)


def us_sections(text: str, form: str) -> str:
    """MD&A（取各候选里最长的一段，目录里那次出现只有几行会被淘汰）+ 一小段利润表。"""
    start_re = _US_START.get(form, _US_START["10-Q"])
    end_re = _US_END.get(form)
    best = ""
    for m in start_re.finditer(text):
        tail = text[m.start():]
        end = end_re.search(tail, pos=len(m.group(0))) if end_re else None
        section = tail[: end.start()] if end else tail[:MAX_CHARS]
        if len(section) > len(best):
            best = section
    parts: list[str] = []
    if best:
        parts.append(best[: MAX_CHARS - 4000])
    # 利润表：取后面跟着一大片数字的那次出现（目录里的标题后面没有数字）
    for m in _US_INCOME.finditer(text):
        window = text[m.start(): m.start() + 3500]
        if sum(ch.isdigit() for ch in window) > 250:
            parts.append(window)
            break
    if not parts:
        return text[:MAX_CHARS]
    return "\n\n".join(parts)[:MAX_CHARS]


# ---------- A 股 / 港股（PDF） ----------

_MDA = re.compile(r"^\s*(?:第[一二三四五六七八九十]+[节章]\s*)?(?:管理层讨论(?:与|及)分析|管理層討論(?:與|及)分析|经营情况讨论与分析|經營情況討論與分析|业务回顾|業務回顧|財務回顧|财务回顾)")
_SUMMARY = re.compile(r"^\s*(?:第[一二三四五六七八九十]+[节章]\s*)?(?:主要会计数据和财务指标|主要财务指标|公司简介和主要财务指标|财务概要|財務概要|財務表現摘要|财务表现摘要|財務摘要|财务摘要|財務資料概要)")
_STOP = re.compile(r"^\s*(?:第[一二三四五六七八九十]+[节章]\s*)?(?:公司治理|企业管治|企業管治|董事會報告|董事会报告|重要事项|股份变动|審計報告|审计报告|财务报告|財務報告|环境和社会责任|环境、社会)")
_TOC_HINT = re.compile(r"目录|目錄|CONTENTS", re.I)
_HEAD_LINES = 5
MAX_SCAN_PAGES = 100
MDA_PAGES = 12
SUMMARY_PAGES = 3


def _heads(page_text: str) -> list[str]:
    return [ln.strip() for ln in page_text.split("\n") if ln.strip()][:_HEAD_LINES]


def _is_toc(page_text: str, pattern: re.Pattern) -> bool:
    """目录页会把多个章节名一起列出来，不是正文起点。"""
    lines = [ln.strip() for ln in page_text.split("\n") if ln.strip()]
    hits = sum(1 for ln in lines if pattern.match(ln) or _MDA.match(ln) or _SUMMARY.match(ln) or _STOP.match(ln))
    return hits >= 3 or any(_TOC_HINT.fullmatch(ln) for ln in lines[:3])


def pick_pdf_sections(pages: list[str]) -> str:
    """pages：每页文字。取「财务概要」几页 + 「管理层讨论与分析」十几页；找不到就取开头几页。"""
    def find(pattern: re.Pattern) -> int | None:
        for i, text in enumerate(pages):
            if any(pattern.match(h) for h in _heads(text)) and not _is_toc(text, pattern):
                return i
        return None

    out: list[str] = []
    s = find(_SUMMARY)
    if s is not None:
        out.append("\n".join(pages[s: s + SUMMARY_PAGES])[:8_000])
    m = find(_MDA)
    if m is not None:
        end = m + 1
        while end < min(len(pages), m + MDA_PAGES):
            if any(_STOP.match(h) for h in _heads(pages[end])):
                break
            end += 1
        out.append("\n".join(pages[m:end]))
    if not out:
        # 季报这类短报告往往没有章节标题：跳过封面取开头
        out.append("\n".join(pages[1:15]))
    return "\n\n".join(out)[:MAX_CHARS]


def pdf_pages(data: bytes, max_pages: int = MAX_SCAN_PAGES) -> list[str]:
    """逐页提取文字（只读前 max_pages 页：要找的章节都在前半部分）。单页失败当空页。"""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    pages: list[str] = []
    for page in reader.pages[:max_pages]:
        try:
            pages.append(page.extract_text() or "")
        except Exception:  # noqa: BLE001
            pages.append("")
    return pages


def looks_readable(text: str) -> bool:
    """文字是否可读：部分 PDF 的字体没带字符映射，提取出来是一串乱码符号（实测腾讯港股中期报告就是这样），这种喂给大模型只会胡编。"""
    sample = text[:20_000]
    if len(sample) < 500:
        return False
    ok = sum(1 for c in sample if c.isascii() or "一" <= c <= "鿿" or c in "，。、；：（）％“”‘’—…·％℃")
    return ok / len(sample) >= 0.9
