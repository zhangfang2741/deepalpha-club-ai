"""图谱查询服务 — 实体检索、因果链分析、瓶颈报告。"""

import uuid
from typing import Optional

from sqlalchemy import func
from sqlmodel import Session, select

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
)


def get_graph_data(session: Session, params: GraphQueryParams) -> GraphData:
    """获取图谱可视化数据（节点 + 边），支持多维过滤。"""
    # 构建实体查询
    entity_stmt = select(GraphEntity)
    if params.entity_types:
        entity_stmt = entity_stmt.where(GraphEntity.entity_type.in_(params.entity_types))
    if params.ticker:
        entity_stmt = entity_stmt.where(GraphEntity.ticker == params.ticker.upper())
    entity_stmt = entity_stmt.limit(params.limit)

    entities = session.exec(entity_stmt).all()
    entity_ids = {e.id for e in entities}

    # 构建事实查询（只返回两端实体都在结果集中的边）
    fact_stmt = select(GraphFact).where(
        GraphFact.source_entity_id.in_(entity_ids),
        GraphFact.target_entity_id.in_(entity_ids),
        GraphFact.confidence >= params.min_confidence,
    )
    if params.relation_types:
        fact_stmt = fact_stmt.where(GraphFact.relation_type.in_(params.relation_types))
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
        constrained_entities = [
            EntityOut.model_validate(session.get(GraphEntity, eid))
            for eid in constrained_ids
            if session.get(GraphEntity, eid)
        ]

        reports.append(BottleneckReport(
            resource_name=resource.name,
            resource_type=resource.entity_type,
            constrained_count=len(constrained_ids),
            constrained_entities=constrained_entities,
            evidence_samples=[f.evidence_text[:200] for f in facts[:3]],
        ))

    return reports


def get_demand_chain(session: Session, concept_name: str) -> Optional[DemandChain]:
    """分析需求传导链路：Concept → Product → Company → Resource（瓶颈）。"""
    concept_stmt = select(GraphEntity).where(
        GraphEntity.name.ilike(f"%{concept_name}%"),
        GraphEntity.entity_type == EntityType.CONCEPT,
    )
    concept = session.exec(concept_stmt).first()
    if not concept:
        return None

    # 向下：Concept → Technology/Resource（ENABLED_BY）
    enabled_facts = session.exec(
        select(GraphFact).where(
            GraphFact.source_entity_id == concept.id,
            GraphFact.relation_type == RelationType.ENABLED_BY,
        )
    ).all()

    enabled_entity_ids = {f.target_entity_id for f in enabled_facts}
    enabled_products: list[GraphEntity] = []
    for eid in enabled_entity_ids:
        e = session.get(GraphEntity, eid)
        if e:
            enabled_products.append(e)

    # 供应商：Product SUPPLIED_BY Company
    supplier_ids: set[uuid.UUID] = set()
    for prod in enabled_products:
        supply_facts = session.exec(
            select(GraphFact).where(
                GraphFact.source_entity_id == prod.id,
                GraphFact.relation_type == RelationType.SUPPLIED_BY,
            )
        ).all()
        supplier_ids.update(f.target_entity_id for f in supply_facts)

    suppliers = [session.get(GraphEntity, sid) for sid in supplier_ids if session.get(GraphEntity, sid)]

    # 瓶颈：CONSTRAINED_BY
    constrained_ids: set[uuid.UUID] = set()
    for prod in enabled_products:
        constraint_facts = session.exec(
            select(GraphFact).where(
                GraphFact.source_entity_id == prod.id,
                GraphFact.relation_type == RelationType.CONSTRAINED_BY,
            )
        ).all()
        constrained_ids.update(f.target_entity_id for f in constraint_facts)

    constrained_resources = [session.get(GraphEntity, cid) for cid in constrained_ids if session.get(GraphEntity, cid)]

    return DemandChain(
        concept=EntityOut.model_validate(concept),
        enabled_products=[EntityOut.model_validate(e) for e in enabled_products],
        supplier_companies=[EntityOut.model_validate(e) for e in suppliers if e],
        constrained_resources=[EntityOut.model_validate(e) for e in constrained_resources if e],
    )
