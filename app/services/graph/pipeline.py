"""文档摄取与事实入库流水线。

流程：获取文档 → 切片（800-1500 tokens） → LLM 抽取 → 实体规范化 → 存储。
"""

import re
from datetime import UTC, datetime
from typing import Optional

import httpx
from sqlmodel import Session

from app.core.config import settings
from app.core.logging import logger
from app.db.session import sync_engine
from app.models.finkg_triple import FinKGTriple
from app.models.graph_entity import EntityType, GraphEntity
from app.models.graph_fact import GraphFact
from app.models.graph_source import DocumentStatus, DocumentType, SourceDocument
from app.services.graph.extractor import ExtractedFact, extract_facts_from_chunk
from app.services.graph.finreflect import chunk_document, extract_triples
from app.services.graph.normalizer import normalize_entity_name

# FinReflectKG 模式前缀 → 论文抽取模式的映射
_FINREFLECT_MODES = {
    "finreflect_single": "single_pass",
    "finreflect_multi": "multi_pass",
    "finreflect_reflection": "reflection",
}


def _finreflect_mode() -> Optional[str]:
    """当前配置若为 FinReflectKG 模式则返回论文模式名，否则 None（走旧版抽取）。"""
    return _FINREFLECT_MODES.get(settings.GRAPH_EXTRACTION_MODE)

_HEADERS = {
    "User-Agent": "DeepAlpha/1.0 (investment research; mailto:research@deepalpha.ai)",
    "Accept-Encoding": "gzip, deflate",
}


def _chunk_text(text: str, max_tokens: int = 1200) -> list[str]:
    """将长文本切分为约 max_tokens 的段落。

    以句子为边界切割（不截断句子），估算 token 数 ≈ 字符数 / 4。
    """
    char_limit = max_tokens * 4
    sentences = re.split(r"(?<=[.!?])\s+", text)

    chunks: list[str] = []
    current = ""
    for sent in sentences:
        if len(current) + len(sent) + 1 > char_limit and current:
            chunks.append(current.strip())
            current = sent
        else:
            current = (current + " " + sent).strip() if current else sent
    if current.strip():
        chunks.append(current.strip())
    return chunks


async def _fetch_text_from_url(url: str) -> str:
    """从 URL 抓取纯文本内容（支持 SEC EDGAR 直链）。"""
    async with httpx.AsyncClient(timeout=60, headers=_HEADERS) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "")
        if "json" in content_type:
            return str(resp.json())
        return resp.text


def _get_or_create_entity_sync(
    session,
    name: str,
    entity_type: EntityType,
) -> GraphEntity:
    """同步事务中获取或创建实体（按规范名称去重）。"""
    from sqlmodel import select

    canonical = normalize_entity_name(name)
    stmt = select(GraphEntity).where(GraphEntity.name == canonical)
    existing = session.exec(stmt).first()
    if existing:
        return existing

    entity = GraphEntity(
        entity_type=entity_type,
        name=canonical,
        aliases=[name] if name != canonical else [],
    )
    session.add(entity)
    session.flush()
    return entity


def _store_facts_sync(
    doc: SourceDocument,
    facts: list[ExtractedFact],
    chunk_id: str,
) -> int:
    """将一批抽取事实写入数据库（同步）。返回实际写入条数。"""
    stored = 0
    with Session(sync_engine) as session:
        for fact in facts:
            try:
                src_entity = _get_or_create_entity_sync(session, fact.source_name, fact.source_type)
                tgt_entity = _get_or_create_entity_sync(session, fact.target_name, fact.target_type)

                graph_fact = GraphFact(
                    source_entity_id=src_entity.id,
                    target_entity_id=tgt_entity.id,
                    relation_type=fact.relation,
                    evidence_text=fact.evidence_text,
                    confidence=fact.confidence,
                    event_time=fact.event_time,
                    ingestion_time=datetime.now(UTC),
                    source_doc_id=doc.id,
                    document_url=doc.url,
                    document_section=doc.section,
                    chunk_id=chunk_id,
                )
                session.add(graph_fact)
                stored += 1
            except Exception as e:
                logger.warning("fact_store_error", error=str(e), chunk=chunk_id)
                continue

        doc.fact_count += stored
        session.add(doc)
        session.commit()

    return stored


def _save_doc_sync(doc: SourceDocument) -> SourceDocument:
    """持久化新建的 SourceDocument，返回已有 id 的对象。"""
    with Session(sync_engine, expire_on_commit=False) as session:
        session.add(doc)
        session.commit()
        session.refresh(doc)
        return doc


def _mark_doc_failed(doc_id, error_message: str) -> None:
    """将文档标记为失败并记录原因（用于抓取失败时留痕，便于前端展示）。"""
    from app.models.graph_source import SourceDocument

    with Session(sync_engine, expire_on_commit=False) as session:
        doc = session.get(SourceDocument, doc_id)
        if doc:
            doc.status = DocumentStatus.FAILED
            doc.error_message = error_message[:500]
            session.add(doc)
            session.commit()


def _delete_doc(doc_id) -> None:
    """删除占位文档记录（用于缓存命中时清理重复任务）。"""
    from app.models.graph_source import SourceDocument

    with Session(sync_engine) as session:
        doc = session.get(SourceDocument, doc_id)
        if doc:
            session.delete(doc)
            session.commit()


def _find_cached_done(cache_key: str) -> Optional[tuple[str, int]]:
    """按 cache_key 查找已完成的文档，命中则返回 (doc_id, fact_count)。

    用于缓存去重：同一份文档（相同 SEC 期次 / 电话会议季度 / URL）已摄取完成时，
    跳过重复抓取与 LLM 抽取，直接复用结果。
    """
    from sqlmodel import select

    with Session(sync_engine) as session:
        existing = session.exec(
            select(SourceDocument).where(
                SourceDocument.cache_key == cache_key,
                SourceDocument.status == DocumentStatus.DONE,
            )
        ).first()
        if existing:
            logger.info("ingest_cache_hit", cache_key=cache_key, doc_id=str(existing.id))
            return str(existing.id), existing.fact_count
    return None


async def ingest_sec_filing(
    ticker: str,
    form_type: str,
    llm_client,
    section: Optional[str] = None,
) -> tuple[int, Optional[str]]:
    """一键抓取并摄取 ticker 最新一份 SEC 文件。

    Args:
        ticker: 股票代码（如 NVDA）
        form_type: 文件类型（10-K / 10-Q / 8-K）
        llm_client: LangChain BaseChatModel
        section: 可选章节提示（用于 source_info）

    Returns:
        (存储事实条数, doc_id 字符串) 或 (0, None)
    """
    from app.services.graph.sec_fetcher import sec_fetcher

    doc_type = DocumentType(form_type) if form_type in ("10-K", "10-Q", "8-K") else DocumentType.SEC_10K

    # 先建一条 pending 记录，保证任务一提交就在「摄取记录」中可见（抓取失败也留痕）
    doc = _save_doc_sync(SourceDocument(
        url=f"sec-pending://{ticker.upper()}/{form_type}",
        document_type=doc_type,
        ticker=ticker.upper(),
        section=section,
        title=f"{ticker} {form_type}",
        status=DocumentStatus.PROCESSING,
    ))

    try:
        text, filing_info = await sec_fetcher.fetch_latest_filing_text(
            ticker=ticker,
            form_type=form_type,
            section_hint=section,
        )
    except Exception as e:
        logger.exception("sec_fetch_failed", ticker=ticker, form=form_type, error=str(e))
        _mark_doc_failed(doc.id, f"抓取 SEC 文件失败：{e}")
        return 0, str(doc.id)

    if not text:
        logger.warning("sec_filing_no_text", ticker=ticker, form=form_type)
        _mark_doc_failed(doc.id, f"未获取到 {ticker} 的 {form_type} 文件文本（可能无网络访问 SEC 或该文件不存在）")
        return 0, str(doc.id)

    filing_date_str = filing_info.get("filing_date", "")
    period_str = filing_info.get("period_of_report", "")

    # 缓存去重：同一 ticker + 文件类型 + 期次已摄取完成则跳过 LLM 抽取
    cache_key = f"sec:{ticker.upper()}:{form_type}:{period_str or filing_date_str}"
    cached = _find_cached_done(cache_key)
    if cached:
        _delete_doc(doc.id)  # 命中缓存：删除占位记录，复用已有结果
        return cached[1], cached[0]

    try:
        filing_date = datetime.strptime(filing_date_str, "%Y-%m-%d") if filing_date_str else None
        period_date = datetime.strptime(period_str, "%Y-%m-%d") if period_str else None
    except ValueError:
        filing_date, period_date = None, None

    # 用抓取到的真实元信息补全 pending 记录，再跑流水线
    doc.url = filing_info.get("doc_url", f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={ticker}")
    doc.company_name = filing_info.get("entity_name")
    doc.filing_date = filing_date
    doc.period_of_report = period_date
    doc.title = f"{ticker} {form_type} {period_str}"
    doc.cache_key = cache_key
    count = await run_ingest_pipeline(doc, llm_client, raw_text=text)
    return count, str(doc.id)


async def ingest_earnings_call(
    ticker: str,
    year: int,
    quarter: int,
    llm_client,
) -> tuple[int, Optional[str]]:
    """一键抓取并摄取电话会议记录（FMP 优先，失败时级联多源抓取）。

    Returns:
        (存储事实条数, doc_id 字符串) 或 (0, None)
    """
    from app.services.graph.fmp_fetcher import fmp_transcript_fetcher

    # 缓存去重：该季度电话会议已摄取完成则直接跳过下载与抽取
    cache_key = f"ec:{ticker.upper()}:{year}:{quarter}"
    cached = _find_cached_done(cache_key)
    if cached:
        return cached[1], cached[0]

    try:
        period_date = datetime(year, (quarter - 1) * 3 + 1, 1)
    except ValueError:
        period_date = None

    # 先建 pending 记录，保证任务一提交就在「摄取记录」中可见（抓取失败也留痕）
    doc = _save_doc_sync(SourceDocument(
        url=f"transcript-pending://{ticker.upper()}/{year}Q{quarter}",
        document_type=DocumentType.EARNINGS_CALL,
        ticker=ticker.upper(),
        company_name=ticker.upper(),
        period_of_report=period_date,
        title=f"{ticker} Earnings Call {year} Q{quarter}",
        section="Full Transcript",
        cache_key=cache_key,
        status=DocumentStatus.PROCESSING,
    ))

    # 抓取：FMP 优先，失败时用多源抓取器兜底
    source_url = f"https://financialmodelingprep.com/financial-summaries/earning-call-transcript/{ticker}"
    try:
        text = await fmp_transcript_fetcher.get_transcript(ticker, year, quarter)
        if not text:
            logger.warning("fmp_transcript_empty", ticker=ticker, year=year, quarter=quarter)
            from app.services.graph.transcript_scraper import transcript_scraper
            text = await transcript_scraper.get_transcript(ticker, year, quarter)
            source_url = f"transcript://{ticker}/{year}Q{quarter}"
    except Exception as e:
        logger.exception("transcript_fetch_failed", ticker=ticker, year=year, quarter=quarter, error=str(e))
        _mark_doc_failed(doc.id, f"抓取电话会议记录失败：{e}")
        return 0, str(doc.id)

    if not text:
        logger.warning("all_transcript_sources_failed", ticker=ticker, year=year, quarter=quarter)
        _mark_doc_failed(doc.id, f"未获取到 {ticker} {year}Q{quarter} 电话会议文本（可能无 FMP 权限或该季度记录不存在）")
        return 0, str(doc.id)

    doc.url = source_url
    count = await run_ingest_pipeline(doc, llm_client, raw_text=text)
    return count, str(doc.id)


async def ingest_raw_text(
    raw_text: str,
    document_type: DocumentType,
    llm_client,
    ticker: Optional[str] = None,
    company_name: Optional[str] = None,
    period_of_report: Optional[datetime] = None,
    section: Optional[str] = None,
    title: Optional[str] = None,
) -> tuple[int, Optional[str]]:
    """直接接收原始文本并执行摄取流水线（无需 URL）。

    适用场景：用户从 Seeking Alpha、公司 IR 网站等处复制的电话会议记录文本。

    Returns:
        (存储事实条数, doc_id 字符串) 或 (0, None)
    """
    if not raw_text or len(raw_text.strip()) < 100:
        logger.warning("ingest_raw_text_too_short", length=len(raw_text))
        return 0, None

    placeholder_url = f"text://manual/{ticker or 'unknown'}/{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"

    doc = SourceDocument(
        url=placeholder_url,
        document_type=document_type,
        ticker=ticker.upper() if ticker else None,
        company_name=company_name or ticker,
        period_of_report=period_of_report,
        section=section,
        title=title or f"{ticker or 'Manual'} {document_type.value}",
    )
    doc = _save_doc_sync(doc)
    count = await run_ingest_pipeline(doc, llm_client, raw_text=raw_text)
    return count, str(doc.id)


def _store_finkg_triples_sync(
    doc: SourceDocument,
    triples: list[dict],
    chunk_id: str,
    mode: str,
) -> int:
    """将一批 FinReflectKG 5 元组写入 finkg_triples 表（同步）。返回实际写入条数。"""
    stored = 0
    with Session(sync_engine) as session:
        for triple in triples:
            try:
                session.add(FinKGTriple(
                    head=triple["head"][:300],
                    head_type=triple["head_type"][:50],
                    relation=triple["relation"][:50],
                    tail=triple["tail"][:300],
                    tail_type=triple["tail_type"][:50],
                    evidence=triple.get("evidence", ""),
                    compliant=bool(triple.get("compliant", True)),
                    violations=triple.get("violations", []),
                    extraction_mode=mode,
                    chunk_id=chunk_id,
                    source_doc_id=doc.id,
                    document_url=doc.url,
                    ticker=doc.ticker,
                ))
                stored += 1
            except Exception as e:
                logger.warning("finkg_triple_store_error", error=str(e), chunk=chunk_id)
                continue

        doc.fact_count += stored
        session.add(doc)
        session.commit()

    return stored


async def _extract_and_store_chunk(
    doc: SourceDocument,
    chunk: str,
    chunk_id: str,
    source_info: str,
    llm_client,
) -> int:
    """按配置的抽取模式处理单个 chunk：抽取并入库，返回存储条数。

    - ``finreflect_*``：FinReflectKG 论文本体（24 实体/29 关系），5 元组入 finkg_triples。
    - 其他（默认 ``single_pass``）：旧版供应链抽取，事实入 graph_facts。
    """
    mode = _finreflect_mode()
    if mode:
        triples = await extract_triples(
            chunk,
            source_info,
            llm_client,
            mode=mode,
            max_iterations=settings.GRAPH_REFLECTION_MAX_ITERS,
        )
        if not triples:
            return 0
        return _store_finkg_triples_sync(doc, triples, chunk_id, mode)

    facts = await extract_facts_from_chunk(chunk, source_info, llm_client)
    if not facts:
        return 0
    return _store_facts_sync(doc, facts, chunk_id)


async def run_ingest_pipeline(
    doc: SourceDocument,
    llm_client,
    raw_text: Optional[str] = None,
) -> int:
    """执行完整摄取流水线。

    Args:
        doc: 已保存到数据库的 SourceDocument 对象
        llm_client: LangChain BaseChatModel 实例
        raw_text: 若已有文本则直接使用，否则从 doc.url 抓取

    Returns:
        总存储事实条数
    """
    # 在任何 session 操作前缓存关键属性，避免 detach 后的 DetachedInstanceError
    doc_id = doc.id
    doc_url = doc.url

    logger.info("ingest_pipeline_started", doc_id=str(doc_id), url=doc_url)

    # 1. 更新状态为 processing
    with Session(sync_engine, expire_on_commit=False) as session:
        doc.status = DocumentStatus.PROCESSING
        session.add(doc)
        session.commit()

    try:
        # 2. 获取文本
        if raw_text is None:
            raw_text = await _fetch_text_from_url(doc_url)
        logger.info("document_fetched", doc_id=str(doc_id), text_len=len(raw_text))

        # 3. 切片（FinReflectKG 模式用表格感知切片，不截断表格）
        chunks = chunk_document(raw_text) if _finreflect_mode() else _chunk_text(raw_text)
        logger.info("document_chunked", doc_id=str(doc_id), chunk_count=len(chunks))

        with Session(sync_engine, expire_on_commit=False) as session:
            doc.chunk_count = len(chunks)
            session.add(doc)
            session.commit()

        # 4. 逐 chunk 抽取事实
        source_info = f"{doc.company_name or doc.ticker or 'Unknown'} {doc.document_type.value} {doc.period_of_report.year if doc.period_of_report else ''}"
        if doc.section:
            source_info += f", {doc.section}"

        total_stored = 0
        for i, chunk in enumerate(chunks):
            if len(chunk.strip()) >= 50:  # 过短 chunk 只更新进度、不抽取
                chunk_id = f"{doc_id}:chunk:{i}"
                total_stored += await _extract_and_store_chunk(doc, chunk, chunk_id, source_info, llm_client)

            # 更新进度（已处理切片数），供前端进度条展示
            with Session(sync_engine, expire_on_commit=False) as session:
                doc.processed_chunks = i + 1
                session.add(doc)
                session.commit()

        # 5. 更新状态为 done
        with Session(sync_engine, expire_on_commit=False) as session:
            doc.status = DocumentStatus.DONE
            doc.ingested_at = datetime.now(UTC)
            session.add(doc)
            session.commit()

        logger.info(
            "ingest_pipeline_completed",
            doc_id=str(doc_id),
            chunk_count=len(chunks),
            total_facts=total_stored,
        )
        return total_stored

    except Exception as e:
        logger.exception("ingest_pipeline_failed", doc_id=str(doc_id), error=str(e))
        with Session(sync_engine, expire_on_commit=False) as session:
            doc.status = DocumentStatus.FAILED
            doc.error_message = str(e)[:500]
            session.add(doc)
            session.commit()
        raise
