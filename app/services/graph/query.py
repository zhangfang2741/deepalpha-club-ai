"""图谱查询服务 — 实体检索、因果链分析、瓶颈报告。"""

import uuid
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy import select as sa_select
from sqlmodel import Session, col, select

from app.core.logging import logger
from app.models.graph_entity import EntityType, GraphEntity
from app.models.graph_fact import GraphFact, RelationType
from app.schemas.supply_chain import (
    BottleneckReport,
    DemandChain,
    EntityOut,
    FactOut,
    GraphData,
    GraphEdge,
    GraphNode,
    GraphQueryParams,
    IndustryGraphOverview,
    IndustryOverviewItem,
)
from app.services.graph.normalizer import normalize_entity_name


def get_graph_data(session: Session, params: GraphQueryParams) -> GraphData:
    """获取图谱可视化数据（节点 + 边），支持多维过滤。"""
    # 实体连接度子查询：被多少条事实引用（作为来源或目标）。
    # 按连接度降序取 Top-N，避免数据量大时展示任意子集导致图谱碎片化。
    degree_subq = (
        sa_select(func.count())
        .select_from(GraphFact)
        .where(
            or_(
                col(GraphFact.source_entity_id) == col(GraphEntity.id),
                col(GraphFact.target_entity_id) == col(GraphEntity.id),
            )
        )
        .correlate(GraphEntity)
        .scalar_subquery()
    )

    if params.ticker:
        # 聚焦某公司：从该 ticker 的公司实体出发，沿事实展开 2 跳邻居，
        # 得到「这家公司的产业链子图」，而不是只筛出带 ticker 的公司节点。
        focus = session.exec(
            select(GraphEntity).where(GraphEntity.ticker == params.ticker.upper())
        ).all()
        neighbor_ids: set[uuid.UUID] = {e.id for e in focus}
        frontier = set(neighbor_ids)
        for _ in range(2):  # 2 跳邻居
            if not frontier:
                break
            rel_facts = session.exec(
                select(GraphFact).where(
                    or_(
                        col(GraphFact.source_entity_id).in_(frontier),
                        col(GraphFact.target_entity_id).in_(frontier),
                    )
                )
            ).all()
            reached: set[uuid.UUID] = set()
            for f in rel_facts:
                reached.add(f.source_entity_id)
                reached.add(f.target_entity_id)
            frontier = reached - neighbor_ids
            neighbor_ids |= reached

        if not neighbor_ids:
            total_entities = session.exec(select(func.count()).select_from(GraphEntity)).one()
            total_facts = session.exec(select(func.count()).select_from(GraphFact)).one()
            return GraphData(nodes=[], edges=[], total_entities=total_entities, total_facts=total_facts)
        entity_stmt = select(GraphEntity).where(col(GraphEntity.id).in_(neighbor_ids))
    else:
        entity_stmt = select(GraphEntity)

    if params.entity_types:
        entity_stmt = entity_stmt.where(col(GraphEntity.entity_type).in_(params.entity_types))
    entity_stmt = entity_stmt.order_by(degree_subq.desc(), GraphEntity.name).limit(params.limit)

    entities = session.exec(entity_stmt).all()
    entity_ids = {e.id for e in entities}
    if not entity_ids:
        total_entities = session.exec(select(func.count()).select_from(GraphEntity)).one()
        total_facts = session.exec(select(func.count()).select_from(GraphFact)).one()
        return GraphData(nodes=[], edges=[], total_entities=total_entities, total_facts=total_facts)

    # 构建事实查询（只返回两端实体都在结果集中的边）
    fact_stmt = select(GraphFact).where(
        col(GraphFact.source_entity_id).in_(entity_ids),
        col(GraphFact.target_entity_id).in_(entity_ids),
        col(GraphFact.confidence) >= params.min_confidence,
    )
    if params.relation_types:
        fact_stmt = fact_stmt.where(col(GraphFact.relation_type).in_(params.relation_types))
    # 时间筛选：保留结构性事实（无 event_time）与不早于 since 的有时事实
    if params.since:
        fact_stmt = fact_stmt.where(
            or_(col(GraphFact.event_time).is_(None), col(GraphFact.event_time) >= params.since)
        )
    fact_stmt = fact_stmt.limit(params.limit * 5)

    facts = session.exec(fact_stmt).all()

    # 统计每个实体的 fact 数量
    entity_fact_counts: dict[uuid.UUID, int] = {}
    for f in facts:
        entity_fact_counts[f.source_entity_id] = entity_fact_counts.get(f.source_entity_id, 0) + 1
        entity_fact_counts[f.target_entity_id] = entity_fact_counts.get(f.target_entity_id, 0) + 1

    nodes = [
        GraphNode(
            id=str(e.id),
            name=e.name,
            entity_type=e.entity_type,
            ticker=e.ticker,
            description=e.description,
            fact_count=entity_fact_counts.get(e.id, 0),
        )
        for e in entities
    ]

    edges = [
        GraphEdge(
            id=str(f.id),
            source=str(f.source_entity_id),
            target=str(f.target_entity_id),
            relation_type=f.relation_type,
            evidence_text=f.evidence_text,
            confidence=f.confidence,
            event_time=f.event_time,
            document_url=f.document_url,
        )
        for f in facts
    ]

    # 总计数（不受 limit 约束）
    total_entities = session.exec(select(func.count()).select_from(GraphEntity)).one()
    total_facts = session.exec(select(func.count()).select_from(GraphFact)).one()

    logger.info(
        "graph_data_queried",
        nodes=len(nodes),
        edges=len(edges),
        total_entities=total_entities,
        total_facts=total_facts,
    )
    return GraphData(
        nodes=nodes,
        edges=edges,
        total_entities=total_entities,
        total_facts=total_facts,
    )


def get_entity_facts(
    session: Session,
    entity_id: uuid.UUID,
    direction: str = "both",  # "outbound" | "inbound" | "both"
) -> list[FactOut]:
    """获取指定实体的所有关联事实，带实体名称 join。"""
    if direction == "outbound":
        facts = session.exec(
            select(GraphFact).where(GraphFact.source_entity_id == entity_id)
        ).all()
    elif direction == "inbound":
        facts = session.exec(
            select(GraphFact).where(GraphFact.target_entity_id == entity_id)
        ).all()
    else:
        facts = session.exec(
            select(GraphFact).where(
                (GraphFact.source_entity_id == entity_id) | (GraphFact.target_entity_id == entity_id)
            )
        ).all()

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


# 实体类型的中文称谓（用于瓶颈中文描述）
_ENTITY_TYPE_CN: dict[EntityType, str] = {
    EntityType.COMPANY: "公司",
    EntityType.PRODUCT: "产品",
    EntityType.TECHNOLOGY: "技术",
    EntityType.CONCEPT: "概念",
    EntityType.RESOURCE: "资源",
}


def _build_bottleneck_description(
    resource_name: str,
    resource_type: EntityType,
    count: int,
    entity_names: list[str],
) -> str:
    """生成瓶颈的中文解读：严重程度 + 主要受制方。"""
    if count >= 3:
        severity = "高度集中的核心瓶颈"
    elif count == 2:
        severity = "较重要的瓶颈"
    else:
        severity = "潜在瓶颈"

    type_cn = _ENTITY_TYPE_CN.get(resource_type, "资源")
    shown = "、".join(entity_names[:5])
    suffix = " 等" if len(entity_names) > 5 else ""
    return (
        f"「{resource_name}」（{type_cn}）被 {count} 个产品 / 概念约束，"
        f"属于{severity}。主要受制方：{shown}{suffix}。"
    )


def get_bottleneck_report(session: Session) -> list[BottleneckReport]:
    """识别产业瓶颈：统计被 CONSTRAINED_BY 指向的 Resource/Technology 实体及约束计数。"""
    constrained_facts = session.exec(
        select(GraphFact).where(GraphFact.relation_type == RelationType.CONSTRAINED_BY)
    ).all()

    # 统计每个 target（瓶颈资源）被约束次数
    bottleneck_map: dict[uuid.UUID, list[GraphFact]] = {}
    for f in constrained_facts:
        bottleneck_map.setdefault(f.target_entity_id, []).append(f)

    reports: list[BottleneckReport] = []
    for resource_id, facts in sorted(bottleneck_map.items(), key=lambda x: -len(x[1])):
        resource = session.get(GraphEntity, resource_id)
        if not resource:
            continue

        # 收集受约束实体
        constrained_ids = {f.source_entity_id for f in facts}
        constrained_entities: list[EntityOut] = []
        for eid in constrained_ids:
            entity = session.get(GraphEntity, eid)
            if entity:
                constrained_entities.append(EntityOut.model_validate(entity))

        entity_names = [e.name for e in constrained_entities]
        reports.append(BottleneckReport(
            resource_name=resource.name,
            resource_type=resource.entity_type,
            constrained_count=len(constrained_ids),
            constrained_entities=constrained_entities,
            evidence_samples=[f.evidence_text[:200] for f in facts[:3]],
            description=_build_bottleneck_description(
                resource.name, resource.entity_type, len(constrained_ids), entity_names
            ),
        ))

    return reports


def _find_chain_entry_entities(session: Session, query: str) -> list[GraphEntity]:
    """Find graph entities that can act as a chain-tracing entry point."""
    raw = query.strip()
    if not raw:
        return []

    canonical = normalize_entity_name(raw)
    terms = list(dict.fromkeys([raw, canonical]))
    clauses = []
    for term in terms:
        clauses.append(col(GraphEntity.name).ilike(f"%{term}%"))
        clauses.append(col(GraphEntity.ticker).ilike(term.upper()))

    entities = session.exec(select(GraphEntity).where(or_(*clauses))).all()
    priority = {
        EntityType.CONCEPT: 0,
        EntityType.TECHNOLOGY: 1,
        EntityType.RESOURCE: 2,
        EntityType.PRODUCT: 3,
        EntityType.COMPANY: 4,
    }
    lowered_terms = {term.lower() for term in terms}
    return sorted(
        entities,
        key=lambda entity: (
            0 if entity.name.lower() in lowered_terms else 1,
            priority.get(entity.entity_type, 9),
            entity.name,
        ),
    )


def _entities_by_ids(session: Session, entity_ids: set[uuid.UUID]) -> list[GraphEntity]:
    """Resolve entity ids into a stable, de-duplicated entity list."""
    entities: list[GraphEntity] = []
    seen: set[uuid.UUID] = set()
    for entity_id in entity_ids:
        if entity_id in seen:
            continue
        entity = session.get(GraphEntity, entity_id)
        if entity:
            entities.append(entity)
            seen.add(entity_id)
    entities.sort(key=lambda entity: (_ENTITY_TYPE_CN.get(entity.entity_type, ""), entity.name))
    return entities


def get_demand_chain(session: Session, concept_name: str) -> Optional[DemandChain]:
    """分析需求/技术/资源传导链路。

    用户常用 HBM、CoWoS、Power 这类产业关键词追链，而不是只输入
    AI Training 这样的 Concept。这里允许任意实体作为入口，并自动补齐：
    - 入口依赖的产品/技术
    - 依赖入口的上游/下游节点
    - 供应商
    - 直接或间接受约束的瓶颈资源
    """
    entry_entities = _find_chain_entry_entities(session, concept_name)
    if not entry_entities:
        return None
    concept = entry_entities[0]
    entry_ids = {entity.id for entity in entry_entities}

    # 向下：入口 → Technology/Resource（ENABLED_BY）
    enabled_facts = session.exec(
        select(GraphFact).where(
            col(GraphFact.source_entity_id).in_(entry_ids),
            GraphFact.relation_type == RelationType.ENABLED_BY,
        )
    ).all()

    enabled_entity_ids = {f.target_entity_id for f in enabled_facts}

    # 反向：Product/Concept → 入口（ENABLED_BY），例如 H100 / AI Training → HBM3E。
    dependent_facts = session.exec(
        select(GraphFact).where(
            col(GraphFact.target_entity_id).in_(entry_ids),
            GraphFact.relation_type == RelationType.ENABLED_BY,
        )
    ).all()
    enabled_entity_ids.update(f.source_entity_id for f in dependent_facts)
    enabled_entity_ids.update(entry_ids)
    enabled_products = _entities_by_ids(session, enabled_entity_ids - {concept.id})

    # 供应商：Product SUPPLIED_BY Company
    supplier_ids: set[uuid.UUID] = set()
    supplier_source_ids = entry_ids | {prod.id for prod in enabled_products}
    for source_id in supplier_source_ids:
        supply_facts = session.exec(
            select(GraphFact).where(
                GraphFact.source_entity_id == source_id,
                GraphFact.relation_type == RelationType.SUPPLIED_BY,
            )
        ).all()
        supplier_ids.update(f.target_entity_id for f in supply_facts)

    suppliers = _entities_by_ids(session, supplier_ids)

    # 瓶颈：CONSTRAINED_BY —— 同时考虑概念自身与其依赖产品/技术的约束
    constrained_ids: set[uuid.UUID] = set()
    constraint_source_ids = entry_ids | {p.id for p in enabled_products}
    for source_id in constraint_source_ids:
        constraint_facts = session.exec(
            select(GraphFact).where(
                GraphFact.source_entity_id == source_id,
                GraphFact.relation_type == RelationType.CONSTRAINED_BY,
            )
        ).all()
        constrained_ids.update(f.target_entity_id for f in constraint_facts)

    # 反向：Product/Concept CONSTRAINED_BY 入口资源，例如 H200 → HBM Supply。
    constrained_by_entry = session.exec(
        select(GraphFact).where(
            col(GraphFact.target_entity_id).in_(entry_ids),
            GraphFact.relation_type == RelationType.CONSTRAINED_BY,
        )
    ).all()
    constrained_ids.update(f.target_entity_id for f in constrained_by_entry)

    constrained_resources = _entities_by_ids(session, constrained_ids)

    return DemandChain(
        concept=EntityOut.model_validate(concept),
        enabled_products=[EntityOut.model_validate(e) for e in enabled_products],
        supplier_companies=[EntityOut.model_validate(e) for e in suppliers],
        constrained_resources=[EntityOut.model_validate(e) for e in constrained_resources],
    )


def _entity_outs(session: Session, entity_ids: set[uuid.UUID], limit: int = 5) -> list[EntityOut]:
    """按名称稳定返回实体输出。"""
    entities: list[GraphEntity] = []
    for entity_id in entity_ids:
        entity = session.get(GraphEntity, entity_id)
        if entity:
            entities.append(entity)
    entities.sort(key=lambda e: e.name)
    return [EntityOut.model_validate(e) for e in entities[:limit]]


def _sample_evidence(facts: list[GraphFact], limit: int = 3) -> list[str]:
    """返回简短证据样本。"""
    return [f.evidence_text[:220] for f in facts[:limit] if f.evidence_text]


def _get_focus_label(session: Session, ticker: Optional[str]) -> str:
    """根据 ticker 生成总览标题中的聚焦对象。"""
    if not ticker:
        return "全部已入库产业链"
    entity = session.exec(
        select(GraphEntity).where(GraphEntity.ticker == ticker.upper())
    ).first()
    return f"{entity.name}（{ticker.upper()}）" if entity else ticker.upper()


def get_industry_overview(
    session: Session,
    params: GraphQueryParams,
) -> IndustryGraphOverview:
    """生成面向普通投资者的产业图谱总览。

    该函数不调用 LLM，完全基于已入库事实生成稳定、可解释的摘要。
    """
    graph = get_graph_data(session, params)
    focus = _get_focus_label(session, params.ticker)

    if not graph.nodes:
        return IndustryGraphOverview(
            title=f"{focus}产业图谱总览",
            summary="当前筛选条件下没有可用图谱事实。先放宽筛选，或摄取目标公司年报、电话会议记录与关键供应商材料。",
            focus=focus,
            total_entities=graph.total_entities,
            total_facts=graph.total_facts,
            data_mode="empty",
            confidence=0.0,
            key_companies=[],
            bottlenecks=[],
            demand_chains=[],
            investor_questions=[
                "这个行业的真实需求来自哪里？",
                "哪些资源限制了供给扩张？",
                "哪些公司同时卡在产品、供应和瓶颈三个位置？",
            ],
            next_actions=[
                "导入龙头公司最新 10-K 或 10-Q。",
                "补充最近 2-4 个季度电话会议记录。",
                "补充关键供应商或客户公司的披露材料。",
            ],
        )

    node_ids = {uuid.UUID(n.id) for n in graph.nodes}
    fact_stmt = select(GraphFact).where(
        col(GraphFact.source_entity_id).in_(node_ids),
        col(GraphFact.target_entity_id).in_(node_ids),
        col(GraphFact.confidence) >= params.min_confidence,
    )
    if params.relation_types:
        fact_stmt = fact_stmt.where(col(GraphFact.relation_type).in_(params.relation_types))
    facts = session.exec(fact_stmt).all()

    fact_count_by_entity: dict[uuid.UUID, int] = {}
    relation_count: dict[RelationType, int] = {r: 0 for r in RelationType}
    evidence_facts: list[GraphFact] = []
    for fact in facts:
        fact_count_by_entity[fact.source_entity_id] = fact_count_by_entity.get(fact.source_entity_id, 0) + 1
        fact_count_by_entity[fact.target_entity_id] = fact_count_by_entity.get(fact.target_entity_id, 0) + 1
        relation_count[fact.relation_type] = relation_count.get(fact.relation_type, 0) + 1
        if fact.evidence_text:
            evidence_facts.append(fact)

    companies = [
        session.get(GraphEntity, entity_id)
        for entity_id, _count in sorted(fact_count_by_entity.items(), key=lambda x: x[1], reverse=True)
    ]
    key_company_items: list[IndustryOverviewItem] = []
    for company in [c for c in companies if c and c.entity_type == EntityType.COMPANY][:5]:
        related = [f for f in facts if f.source_entity_id == company.id or f.target_entity_id == company.id]
        score = min(1.0, len(related) / max(1, len(facts)))
        key_company_items.append(
            IndustryOverviewItem(
                title=company.name,
                description=f"{company.name} 连接了 {len(related)} 条产业链事实，是当前图谱中需要优先跟踪的公司节点。",
                score=score,
                entities=[EntityOut.model_validate(company)],
                evidence_samples=_sample_evidence(related),
            )
        )

    bottleneck_items = [
        IndustryOverviewItem(
            title=report.resource_name,
            description=report.description,
            score=min(1.0, report.constrained_count / 5),
            entities=report.constrained_entities[:5],
            evidence_samples=report.evidence_samples,
        )
        for report in get_bottleneck_report(session)[:5]
    ]

    concept_ids: set[uuid.UUID] = {
        uuid.UUID(n.id)
        for n in graph.nodes
        if n.entity_type == EntityType.CONCEPT
    }
    linked_concept_facts = session.exec(
        select(GraphFact).where(
            col(GraphFact.target_entity_id).in_(node_ids),
            col(GraphFact.relation_type).in_([RelationType.ENABLED_BY, RelationType.CONSTRAINED_BY]),
        )
    ).all()
    for fact in linked_concept_facts:
        source = session.get(GraphEntity, fact.source_entity_id)
        if source and source.entity_type == EntityType.CONCEPT:
            concept_ids.add(source.id)

    demand_items: list[IndustryOverviewItem] = []
    for concept in _entity_outs(session, concept_ids, limit=5):
        chain = get_demand_chain(session, concept.name)
        if not chain:
            continue
        linked_entities = [
            *chain.enabled_products[:3],
            *chain.supplier_companies[:3],
            *chain.constrained_resources[:3],
        ]
        total_links = len(chain.enabled_products) + len(chain.supplier_companies) + len(chain.constrained_resources)
        demand_items.append(
            IndustryOverviewItem(
                title=concept.name,
                description=(
                    f"{concept.name} 已追踪到 {len(chain.enabled_products)} 个支撑产品/技术、"
                    f"{len(chain.supplier_companies)} 个供应商和 {len(chain.constrained_resources)} 个瓶颈资源。"
                ),
                score=min(1.0, total_links / 8),
                entities=linked_entities,
                evidence_samples=[],
            )
        )

    avg_confidence = sum(f.confidence for f in facts) / len(facts) if facts else 0.0
    data_mode = "documented" if any(f.source_doc_id for f in facts) else "demo"
    bottleneck_count = relation_count.get(RelationType.CONSTRAINED_BY, 0)
    supplier_count = relation_count.get(RelationType.SUPPLIED_BY, 0)
    summary = (
        f"当前图谱覆盖 {len(graph.nodes)} 个可视节点、{len(graph.edges)} 条关系；"
        f"其中 {bottleneck_count} 条指向供给瓶颈，{supplier_count} 条指向供应商。"
        f"优先关注高连接公司、被多条链路共同指向的资源，以及需求概念能否传导到真实产品和供应商。"
    )

    return IndustryGraphOverview(
        title=f"{focus}产业图谱总览",
        summary=summary,
        focus=focus,
        total_entities=graph.total_entities,
        total_facts=graph.total_facts,
        data_mode=data_mode,
        confidence=avg_confidence,
        key_companies=key_company_items,
        bottlenecks=bottleneck_items,
        demand_chains=demand_items,
        investor_questions=[
            "需求增长最终会让哪类公司受益，而不是只停留在概念层？",
            "供给瓶颈是短期产能约束，还是长期稀缺资源？",
            "关键公司是否同时具备产品、客户和供应链控制力？",
            "当前证据来自真实文档还是演示数据，是否需要补充最新季度材料？",
        ],
        next_actions=[
            "先看瓶颈资源，再回到图谱点击相关节点核对原文证据。",
            "用股票代码聚焦单家公司，观察 2 跳上下游是否完整。",
            "导入最近电话会议记录，验证管理层是否确认需求或产能变化。",
        ],
    )
