"""产业供应链因果图谱 API。

提供事实摄取、实体管理、图谱查询、瓶颈分析与需求链路分析端点。
"""

import uuid
from datetime import UTC, datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from app.core.logging import logger
from app.db.session import get_sync_session
from app.models.graph_entity import EntityType, GraphEntity
from app.models.graph_fact import GraphFact, RelationType
from app.models.graph_source import DocumentStatus, DocumentType, SourceDocument
from app.schemas.supply_chain import (
    BottleneckReport,
    DemandChain,
    EntityCreate,
    EntityOut,
    FactCreate,
    FactOut,
    GraphData,
    GraphQueryParams,
    IngestDocumentRequest,
    IngestDocumentResponse,
    IngestTextRequest,
)
from app.services.graph.pipeline import (
    ingest_earnings_call,
    ingest_raw_text,
    ingest_sec_filing,
    run_ingest_pipeline,
)
from app.services.graph.query import (
    get_bottleneck_report,
    get_demand_chain,
    get_entity_facts,
    get_graph_data,
)

router = APIRouter()


def _get_llm():
    """获取 LLM 客户端（惰性初始化，避免循环依赖）。"""
    from app.services.llm.registry import llm_registry

    return llm_registry.get_default()


# ──────────────────────────────────────────────
# 文档摄取
# ──────────────────────────────────────────────


@router.post(
    "/ingest",
    response_model=IngestDocumentResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="触发文档摄取",
)
async def ingest_document(
    request: IngestDocumentRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_sync_session),
):
    """提交文档 URL，异步执行：抓取→切片→LLM 抽取→入库。

    文档状态从 pending → processing → done（或 failed）。
    """
    # 缓存去重：同一 URL 已摄取完成则直接返回缓存结果，不重复抓取/抽取
    cache_key = f"url:{request.url}"
    cached = session.exec(
        select(SourceDocument).where(
            SourceDocument.cache_key == cache_key,
            SourceDocument.status == DocumentStatus.DONE,
        )
    ).first()
    if cached:
        return IngestDocumentResponse(
            doc_id=cached.id,
            status="cached",
            message=f"该文档已摄取（{cached.fact_count} 条事实），返回缓存结果",
        )

    doc = SourceDocument(
        url=request.url,
        document_type=request.document_type,
        ticker=request.ticker,
        company_name=request.company_name,
        filing_date=request.filing_date,
        period_of_report=request.period_of_report,
        section=request.section,
        title=request.title,
        status=DocumentStatus.PENDING,
        cache_key=cache_key,
    )
    session.add(doc)
    session.commit()
    session.refresh(doc)

    logger.info("ingest_document_queued", doc_id=str(doc.id), url=request.url)

    llm = _get_llm()
    background_tasks.add_task(run_ingest_pipeline, doc, llm)

    return IngestDocumentResponse(
        doc_id=doc.id,
        status="queued",
        message=f"文档已加入处理队列，doc_id={doc.id}",
    )


@router.get("/documents", response_model=list[dict], summary="列出来源文档")
def list_documents(
    ticker: Optional[str] = Query(default=None),
    document_type: Optional[DocumentType] = Query(default=None),
    status_filter: Optional[DocumentStatus] = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_sync_session),
):
    """列出已摄取或处理中的文档。"""
    stmt = select(SourceDocument)
    if ticker:
        stmt = stmt.where(SourceDocument.ticker == ticker.upper())
    if document_type:
        stmt = stmt.where(SourceDocument.document_type == document_type)
    if status_filter:
        stmt = stmt.where(SourceDocument.status == status_filter)
    stmt = stmt.order_by(SourceDocument.created_at.desc()).limit(limit)

    docs = session.exec(stmt).all()
    return [
        {
            "id": str(d.id),
            "url": d.url,
            "document_type": d.document_type.value,
            "ticker": d.ticker,
            "company_name": d.company_name,
            "status": d.status.value,
            "chunk_count": d.chunk_count,
            "processed_chunks": d.processed_chunks,
            "fact_count": d.fact_count,
            "created_at": d.created_at.isoformat(),
            "ingested_at": d.ingested_at.isoformat() if d.ingested_at else None,
        }
        for d in docs
    ]


# ──────────────────────────────────────────────
# 实体管理
# ──────────────────────────────────────────────


@router.get("/entities", response_model=list[EntityOut], summary="列出实体")
def list_entities(
    entity_type: Optional[EntityType] = Query(default=None),
    ticker: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None, description="名称模糊搜索"),
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_sync_session),
):
    """列出知识图谱中的实体节点，支持按类型、股票代码、名称过滤。"""
    stmt = select(GraphEntity)
    if entity_type:
        stmt = stmt.where(GraphEntity.entity_type == entity_type)
    if ticker:
        stmt = stmt.where(GraphEntity.ticker == ticker.upper())
    if search:
        stmt = stmt.where(GraphEntity.name.ilike(f"%{search}%"))
    stmt = stmt.order_by(GraphEntity.name).limit(limit)

    entities = session.exec(stmt).all()
    return [EntityOut.model_validate(e) for e in entities]


@router.post("/entities", response_model=EntityOut, status_code=status.HTTP_201_CREATED)
def create_entity(
    request: EntityCreate,
    session: Session = Depends(get_sync_session),
):
    """手动创建实体节点（用于种子数据或手动修正）。"""
    existing = session.exec(
        select(GraphEntity).where(GraphEntity.name == request.name)
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"实体 '{request.name}' 已存在")

    entity = GraphEntity(
        entity_type=request.entity_type,
        name=request.name,
        aliases=request.aliases,
        description=request.description,
        ticker=request.ticker,
    )
    session.add(entity)
    session.commit()
    session.refresh(entity)
    logger.info("entity_created", name=entity.name, type=entity.entity_type.value)
    return EntityOut.model_validate(entity)


@router.get("/entities/{entity_id}", response_model=EntityOut)
def get_entity(entity_id: uuid.UUID, session: Session = Depends(get_sync_session)):
    """获取单个实体详情。"""
    entity = session.get(GraphEntity, entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="实体不存在")
    return EntityOut.model_validate(entity)


@router.get("/entities/{entity_id}/facts", response_model=list[FactOut])
def get_entity_facts_endpoint(
    entity_id: uuid.UUID,
    direction: str = Query(default="both", pattern="^(inbound|outbound|both)$"),
    session: Session = Depends(get_sync_session),
):
    """获取实体的所有关联事实（出向/入向/双向）。"""
    entity = session.get(GraphEntity, entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="实体不存在")
    return get_entity_facts(session, entity_id, direction)


# ──────────────────────────────────────────────
# 事实管理
# ──────────────────────────────────────────────


@router.get("/facts", response_model=list[FactOut], summary="列出事实关系")
def list_facts(
    relation_type: Optional[RelationType] = Query(default=None),
    min_confidence: float = Query(default=0.0, ge=0.0, le=1.0),
    doc_id: Optional[uuid.UUID] = Query(default=None, description="按来源文档 ID 过滤"),
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_sync_session),
):
    """列出知识图谱中的事实关系，支持按类型、置信度和来源文档过滤。"""
    stmt = select(GraphFact)
    if relation_type:
        stmt = stmt.where(GraphFact.relation_type == relation_type)
    if doc_id:
        stmt = stmt.where(GraphFact.source_doc_id == doc_id)
    if min_confidence > 0:
        stmt = stmt.where(GraphFact.confidence >= min_confidence)
    stmt = stmt.order_by(GraphFact.ingestion_time.desc()).limit(limit)

    facts = session.exec(stmt).all()

    # Enrich with entity names
    entity_cache: dict[uuid.UUID, GraphEntity] = {}
    results = []
    for f in facts:
        for eid in [f.source_entity_id, f.target_entity_id]:
            if eid not in entity_cache:
                e = session.get(GraphEntity, eid)
                if e:
                    entity_cache[eid] = e
        src = entity_cache.get(f.source_entity_id)
        tgt = entity_cache.get(f.target_entity_id)
        results.append(FactOut(
            id=f.id,
            source_entity_id=f.source_entity_id,
            target_entity_id=f.target_entity_id,
            source_entity_name=src.name if src else None,
            target_entity_name=tgt.name if tgt else None,
            source_entity_type=src.entity_type if src else None,
            target_entity_type=tgt.entity_type if tgt else None,
            relation_type=f.relation_type,
            evidence_text=f.evidence_text,
            confidence=f.confidence,
            event_time=f.event_time,
            ingestion_time=f.ingestion_time,
            document_url=f.document_url,
            document_section=f.document_section,
            chunk_id=f.chunk_id,
        ))
    return results


@router.post("/facts", response_model=FactOut, status_code=status.HTTP_201_CREATED)
def create_fact(
    request: FactCreate,
    session: Session = Depends(get_sync_session),
):
    """手动创建事实关系（用于种子数据或专家注入）。"""
    src = session.get(GraphEntity, request.source_entity_id)
    tgt = session.get(GraphEntity, request.target_entity_id)
    if not src:
        raise HTTPException(status_code=404, detail="来源实体不存在")
    if not tgt:
        raise HTTPException(status_code=404, detail="目标实体不存在")

    fact = GraphFact(
        source_entity_id=request.source_entity_id,
        target_entity_id=request.target_entity_id,
        relation_type=request.relation_type,
        evidence_text=request.evidence_text,
        confidence=request.confidence,
        event_time=request.event_time,
        ingestion_time=datetime.now(UTC),
        document_url=request.document_url,
        document_section=request.document_section,
    )
    session.add(fact)
    session.commit()
    session.refresh(fact)

    return FactOut(
        id=fact.id,
        source_entity_id=fact.source_entity_id,
        target_entity_id=fact.target_entity_id,
        source_entity_name=src.name,
        target_entity_name=tgt.name,
        source_entity_type=src.entity_type,
        target_entity_type=tgt.entity_type,
        relation_type=fact.relation_type,
        evidence_text=fact.evidence_text,
        confidence=fact.confidence,
        event_time=fact.event_time,
        ingestion_time=fact.ingestion_time,
        document_url=fact.document_url,
        document_section=fact.document_section,
        chunk_id=fact.chunk_id,
    )


# ──────────────────────────────────────────────
# 图谱查询与分析
# ──────────────────────────────────────────────


@router.get("/graph", response_model=GraphData, summary="图谱可视化数据")
def get_graph(
    entity_types: Optional[str] = Query(default=None, description="逗号分隔的实体类型列表"),
    relation_types: Optional[str] = Query(default=None, description="逗号分隔的关系类型列表"),
    ticker: Optional[str] = Query(default=None),
    min_confidence: float = Query(default=0.0, ge=0.0, le=1.0),
    since: Optional[str] = Query(default=None, description="仅含事实时间不早于此日期 YYYY-MM-DD"),
    limit: int = Query(default=200, ge=1, le=1000),
    session: Session = Depends(get_sync_session),
):
    """返回前端图谱可视化所需的节点与边数据。"""
    since_dt = None
    if since:
        try:
            since_dt = datetime.strptime(since, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=422, detail="since 日期格式应为 YYYY-MM-DD")

    params = GraphQueryParams(
        entity_types=[EntityType(t) for t in entity_types.split(",") if t] if entity_types else None,
        relation_types=[RelationType(r) for r in relation_types.split(",") if r] if relation_types else None,
        ticker=ticker,
        min_confidence=min_confidence,
        since=since_dt,
        limit=limit,
    )
    return get_graph_data(session, params)


@router.get("/analysis/bottlenecks", response_model=list[BottleneckReport], summary="产业瓶颈分析")
def bottleneck_analysis(session: Session = Depends(get_sync_session)):
    """分析 CONSTRAINED_BY 关系，识别最关键的产业瓶颈资源。"""
    return get_bottleneck_report(session)


@router.get("/analysis/demand-chain/{concept}", response_model=DemandChain, summary="需求传导链路")
def demand_chain_analysis(concept: str, session: Session = Depends(get_sync_session)):
    """分析指定需求概念（如 AI Training）的完整传导链路。"""
    chain = get_demand_chain(session, concept)
    if not chain:
        raise HTTPException(status_code=404, detail=f"未找到概念实体 '{concept}'")
    return chain


# ──────────────────────────────────────────────
# 批量摄取（按 ticker 一键拉取）
# ──────────────────────────────────────────────


@router.post(
    "/ingest/text",
    response_model=IngestDocumentResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="直接摄取文本内容",
)
async def ingest_text_endpoint(
    request: IngestTextRequest,
    background_tasks: BackgroundTasks,
):
    """接收用户粘贴的原始文本，异步执行事实抽取。

    适用于 FMP 无权限时从 Seeking Alpha 等公开来源复制的电话会议记录。
    """
    import uuid as _uuid

    llm = _get_llm()
    doc_id = _uuid.uuid4()

    async def _task():
        try:
            count, doc_id_str = await ingest_raw_text(
                raw_text=request.text,
                document_type=request.document_type,
                llm_client=llm,
                ticker=request.ticker,
                company_name=request.company_name,
                period_of_report=request.period_of_report,
                section=request.section,
                title=request.title,
            )
            logger.info("text_ingest_done", ticker=request.ticker, facts=count, doc_id=doc_id_str)
        except Exception as e:
            logger.exception("text_ingest_task_failed", ticker=request.ticker, error=str(e))

    background_tasks.add_task(_task)
    return IngestDocumentResponse(
        doc_id=doc_id,
        status="queued",
        message=f"文本已加入处理队列，共 {len(request.text)} 字符",
    )


@router.post(
    "/ingest/sec",
    status_code=status.HTTP_202_ACCEPTED,
    summary="一键摄取 SEC 文件",
)
async def ingest_sec_endpoint(
    ticker: str = Query(description="股票代码，如 NVDA"),
    form_type: str = Query(default="10-K", description="文件类型：10-K / 10-Q / 8-K"),
    section: Optional[str] = Query(default=None, description="章节提示，如 Risk Factors"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """自动查找并摄取 ticker 最新一份 SEC 文件（无需手动提交 URL）。"""
    llm = _get_llm()

    async def _task():
        try:
            count, doc_id = await ingest_sec_filing(ticker, form_type, llm, section)
            logger.info("sec_ingest_done", ticker=ticker, form=form_type, facts=count, doc_id=doc_id)
        except Exception as e:
            logger.exception("sec_ingest_task_failed", ticker=ticker, error=str(e))

    background_tasks.add_task(_task)
    return {
        "status": "queued",
        "message": f"已启动 {ticker} {form_type} 摄取任务，后台处理中",
    }


@router.post(
    "/ingest/earnings-call",
    status_code=status.HTTP_202_ACCEPTED,
    summary="摄取电话会议记录",
)
async def ingest_earnings_call_endpoint(
    ticker: str = Query(description="股票代码，如 NVDA"),
    year: int = Query(description="年份，如 2024"),
    quarter: int = Query(ge=1, le=4, description="季度 1-4"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """通过 FMP API 摄取指定季度电话会议文字记录。"""
    llm = _get_llm()

    async def _task():
        try:
            count, doc_id = await ingest_earnings_call(ticker, year, quarter, llm)
            logger.info("earnings_call_ingest_done", ticker=ticker, year=year, quarter=quarter, facts=count)
        except Exception as e:
            logger.exception("earnings_call_ingest_failed", ticker=ticker, error=str(e))

    background_tasks.add_task(_task)
    return {
        "status": "queued",
        "message": f"已启动 {ticker} {year}Q{quarter} 电话会议记录摄取任务",
    }


@router.get("/ingest/sec/search", summary="EDGAR 全文搜索")
async def search_sec_filings(
    ticker: str = Query(description="股票代码，如 NVDA"),
    form_types: str = Query(default="10-K,10-Q,8-K", description="逗号分隔的文件类型"),
    start_date: Optional[str] = Query(default=None, description="起始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(default=None, description="截止日期 YYYY-MM-DD"),
    max_results: int = Query(default=10, ge=1, le=50),
):
    """搜索 EDGAR 返回文件列表（不触发摄取），可用于预览可用文件。"""
    from app.services.graph.sec_fetcher import sec_fetcher

    forms = [f.strip() for f in form_types.split(",") if f.strip()]
    results = await sec_fetcher.search_filings(ticker, forms, start_date, end_date, max_results)
    return {"ticker": ticker, "results": results, "count": len(results)}


@router.get("/ingest/earnings-call/list", summary="列出可用电话会议记录")
async def list_earnings_calls(
    ticker: str = Query(description="股票代码，如 NVDA"),
):
    """列出 FMP 上该 ticker 所有可用的电话会议记录（年份+季度）。"""
    from app.services.graph.fmp_fetcher import fmp_transcript_fetcher

    items = await fmp_transcript_fetcher.list_available_transcripts(ticker)
    return {"ticker": ticker, "available": items, "count": len(items)}


@router.get("/stats", summary="图谱统计摘要")
def graph_stats(session: Session = Depends(get_sync_session)):
    """返回图谱的实体、事实、来源文档统计摘要。"""
    entity_by_type = {}
    for et in EntityType:
        count = session.exec(
            select(GraphEntity).where(GraphEntity.entity_type == et)
        ).all()
        entity_by_type[et.value] = len(count)

    fact_by_relation = {}
    for rt in RelationType:
        count = session.exec(
            select(GraphFact).where(GraphFact.relation_type == rt)
        ).all()
        fact_by_relation[rt.value] = len(count)

    total_docs = len(session.exec(select(SourceDocument)).all())
    done_docs = len(session.exec(
        select(SourceDocument).where(SourceDocument.status == DocumentStatus.DONE)
    ).all())

    return {
        "entities": entity_by_type,
        "facts": fact_by_relation,
        "total_entities": sum(entity_by_type.values()),
        "total_facts": sum(fact_by_relation.values()),
        "documents": {"total": total_docs, "done": done_docs},
    }
