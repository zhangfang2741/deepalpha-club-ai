"""文档摄取与事实入库流水线。

流程：获取文档 → 切片（800-1500 tokens） → LLM 抽取 → 实体规范化 → 存储。
"""

import re
from datetime import UTC, datetime
from typing import Optional

import httpx
from sqlmodel import Session

from app.core.logging import logger
from app.db.session import sync_engine
from app.models.graph_entity import EntityType, GraphEntity
from app.models.graph_fact import GraphFact
from app.models.graph_source import DocumentStatus, SourceDocument
from app.services.graph.extractor import ExtractedFact, extract_facts_from_chunk
from app.services.graph.normalizer import normalize_entity_name

_HEADERS = {
    "User-Agent": "DeepAlpha/1.0 (investment research; mailto:research@deepalpha.ai)",
    "Accept-Encoding": "gzip, deflate",
}

# SEC 文档原文抓取基址
_SEC_FULL_TEXT_BASE = "https://efts.sec.gov/LATEST/search-index?q=%22{ticker}%22&dateRange=custom&startdt={start}&enddt={end}&forms=10-K"


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
    logger.info("ingest_pipeline_started", doc_id=str(doc.id), url=doc.url)

    # 1. 更新状态为 processing
    with Session(sync_engine) as session:
        doc.status = DocumentStatus.PROCESSING
        session.add(doc)
        session.commit()

    try:
        # 2. 获取文本
        if raw_text is None:
            raw_text = await _fetch_text_from_url(doc.url)
        logger.info("document_fetched", doc_id=str(doc.id), text_len=len(raw_text))

        # 3. 切片
        chunks = _chunk_text(raw_text)
        logger.info("document_chunked", doc_id=str(doc.id), chunk_count=len(chunks))

        with Session(sync_engine) as session:
            doc.chunk_count = len(chunks)
            session.add(doc)
            session.commit()

        # 4. 逐 chunk 抽取事实
        source_info = f"{doc.company_name or doc.ticker or 'Unknown'} {doc.document_type.value} {doc.period_of_report.year if doc.period_of_report else ''}"
        if doc.section:
            source_info += f", {doc.section}"

        total_stored = 0
        for i, chunk in enumerate(chunks):
            if len(chunk.strip()) < 50:  # 跳过过短 chunk
                continue
            chunk_id = f"{doc.id}:chunk:{i}"
            facts = await extract_facts_from_chunk(chunk, source_info, llm_client)
            if facts:
                stored = _store_facts_sync(doc, facts, chunk_id)
                total_stored += stored

        # 5. 更新状态为 done
        with Session(sync_engine) as session:
            doc.status = DocumentStatus.DONE
            doc.ingested_at = datetime.now(UTC)
            session.add(doc)
            session.commit()

        logger.info(
            "ingest_pipeline_completed",
            doc_id=str(doc.id),
            chunk_count=len(chunks),
            total_facts=total_stored,
        )
        return total_stored

    except Exception as e:
        logger.exception("ingest_pipeline_failed", doc_id=str(doc.id), error=str(e))
        with Session(sync_engine) as session:
            doc.status = DocumentStatus.FAILED
            doc.error_message = str(e)[:500]
            session.add(doc)
            session.commit()
        raise
