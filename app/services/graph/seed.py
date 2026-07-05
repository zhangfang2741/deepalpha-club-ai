"""产业因果图谱种子数据与注入逻辑。

图谱功能依赖文档摄取（LLM 抽取）才会有数据，首次部署或演示时图谱为空。
本模块提供一份精选的 NVIDIA AI 产业链事实，覆盖：

- 五类实体：Company / Product / Technology / Concept / Resource
- 四类关系：HAS_PRODUCT / SUPPLIED_BY / ENABLED_BY / CONSTRAINED_BY
- 多条 CONSTRAINED_BY 关系，供「瓶颈分析」直接出结果

`seed_supply_chain_graph()` 幂等：默认仅在图谱为空时注入；重复调用按名称 /
三元组去重，不产生重复数据。应用启动（lifespan）会自动调用一次。
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlmodel import Session, select

from app.core.logging import logger
from app.models.graph_entity import EntityType, GraphEntity
from app.models.graph_fact import GraphFact, RelationType

# 每项字段依次为：名称、实体类型、股票代码、描述
ENTITIES: list[tuple[str, str, str | None, str]] = [
    # ── Company ──
    ("NVIDIA", "Company", "NVDA", "AI 加速计算龙头，定义数据中心 GPU 与系统路线图"),
    ("TSMC", "Company", "TSM", "全球先进制程与 CoWoS 封装代工厂"),
    ("SK Hynix", "Company", None, "HBM 高带宽内存主力供应商"),
    ("Micron Technology", "Company", "MU", "HBM3E 内存供应商"),
    ("Samsung", "Company", None, "存储与代工厂商，HBM 供应方之一"),
    ("Microsoft", "Company", "MSFT", "超大规模云厂商，Azure AI 算力需求方"),
    ("Meta", "Company", "META", "超大规模厂商，自研与采购 AI 训练算力"),
    ("Amazon Web Services", "Company", "AMZN", "超大规模云厂商，AI 基础设施需求方"),
    ("Vertiv", "Company", "VRT", "数据中心电力与散热基础设施供应商"),
    ("Broadcom", "Company", "AVGO", "网络与定制 ASIC 供应商"),
    # ── Product ──
    ("H100", "Product", None, "Hopper 架构数据中心 GPU"),
    ("H200", "Product", None, "Hopper 架构升级版，搭载更大 HBM3E"),
    ("B200", "Product", None, "Blackwell 架构数据中心 GPU"),
    ("GB200", "Product", None, "Grace + Blackwell 超级芯片机架系统"),
    ("DGX", "Product", None, "NVIDIA 一体化 AI 服务器系统"),
    # ── Technology ──
    ("CoWoS", "Technology", None, "台积电 2.5D 先进封装技术"),
    ("HBM3E", "Technology", None, "第五代高带宽内存"),
    ("NVLink", "Technology", None, "GPU 间高速互连技术"),
    ("CUDA", "Technology", None, "NVIDIA 并行计算软件栈"),
    # ── Concept ──
    ("AI Training", "Concept", None, "大模型训练算力需求"),
    ("AI Inference", "Concept", None, "大模型推理算力需求"),
    ("Generative AI", "Concept", None, "生成式 AI 应用浪潮"),
    ("Data Center", "Concept", None, "数据中心建设与扩容"),
    # ── Resource ──
    ("Advanced Packaging Capacity", "Resource", None, "CoWoS 先进封装产能"),
    ("HBM Supply", "Resource", None, "HBM 高带宽内存供给"),
    ("Power Capacity", "Resource", None, "数据中心电力供给"),
    ("Cooling Infrastructure", "Resource", None, "数据中心散热基础设施"),
    ("Wafer Capacity", "Resource", None, "先进制程晶圆产能"),
]

# 每项字段依次为：来源实体、关系类型、目标实体、原文证据、置信度、事实时间
FACTS: list[tuple[str, str, str, str, float, str | None]] = [
    # ── HAS_PRODUCT：Company → Product ──
    ("NVIDIA", "HAS_PRODUCT", "H100", "NVIDIA's H100 Tensor Core GPU is the cornerstone of the company's data center business.", 0.97, "2023-01-01"),
    ("NVIDIA", "HAS_PRODUCT", "H200", "NVIDIA introduced the H200 GPU with larger and faster HBM3E memory.", 0.95, "2023-11-13"),
    ("NVIDIA", "HAS_PRODUCT", "B200", "The Blackwell B200 GPU is NVIDIA's next-generation data center accelerator.", 0.96, "2024-03-18"),
    ("NVIDIA", "HAS_PRODUCT", "GB200", "GB200 combines two Blackwell GPUs with a Grace CPU into a single superchip.", 0.95, "2024-03-18"),
    ("NVIDIA", "HAS_PRODUCT", "DGX", "NVIDIA DGX systems are turnkey AI servers built around NVIDIA GPUs.", 0.9, None),
    # ── SUPPLIED_BY：Product/Technology/Resource → Company ──
    ("H100", "SUPPLIED_BY", "TSMC", "The H100 is manufactured by TSMC on its advanced process node.", 0.93, None),
    ("GB200", "SUPPLIED_BY", "TSMC", "Blackwell-class chips are fabricated by TSMC.", 0.9, None),
    ("CoWoS", "SUPPLIED_BY", "TSMC", "CoWoS advanced packaging is provided primarily by TSMC.", 0.95, None),
    ("HBM3E", "SUPPLIED_BY", "SK Hynix", "SK Hynix is the leading supplier of HBM3E memory to NVIDIA.", 0.94, "2024-03-19"),
    ("HBM3E", "SUPPLIED_BY", "Micron Technology", "Micron began volume shipments of HBM3E for NVIDIA's H200.", 0.9, "2024-02-26"),
    ("HBM3E", "SUPPLIED_BY", "Samsung", "Samsung is qualifying its HBM3E for use in AI accelerators.", 0.82, "2024-05-01"),
    ("Advanced Packaging Capacity", "SUPPLIED_BY", "TSMC", "TSMC supplies the bulk of advanced CoWoS packaging capacity for AI chips.", 0.9, None),
    # ── ENABLED_BY：Concept/Product → Technology/Resource ──
    ("H100", "ENABLED_BY", "HBM3E", "High-bandwidth HBM3E memory is essential to feed the H100's compute throughput.", 0.9, None),
    ("H100", "ENABLED_BY", "CoWoS", "The H100 relies on CoWoS packaging to integrate GPU die and HBM stacks.", 0.92, None),
    ("H200", "ENABLED_BY", "HBM3E", "The H200 GPU is built with larger, faster HBM3E memory to increase accelerator bandwidth.", 0.93, "2023-11-13"),
    ("GB200", "ENABLED_BY", "CoWoS", "GB200 requires advanced CoWoS packaging to assemble its multi-die design.", 0.9, None),
    ("GB200", "ENABLED_BY", "NVLink", "GB200 superchips are interconnected through high-speed NVLink.", 0.9, None),
    ("AI Training", "ENABLED_BY", "CUDA", "Large-scale AI training depends on the CUDA software ecosystem.", 0.88, None),
    ("AI Training", "ENABLED_BY", "HBM3E", "Training large models is enabled by the memory bandwidth of HBM3E.", 0.85, None),
    ("AI Inference", "ENABLED_BY", "CUDA", "Production inference workloads run on the CUDA stack.", 0.83, None),
    # ── CONSTRAINED_BY：Product/Concept → Resource/Technology（瓶颈）──
    ("H100", "CONSTRAINED_BY", "Advanced Packaging Capacity", "Supply of the H100 is constrained by limited CoWoS advanced packaging capacity.", 0.92, "2023-08-23"),
    ("GB200", "CONSTRAINED_BY", "Advanced Packaging Capacity", "Blackwell ramp is gated by available advanced packaging capacity.", 0.9, "2024-08-28"),
    ("H200", "CONSTRAINED_BY", "HBM Supply", "H200 availability is limited by tight HBM memory supply.", 0.9, "2024-02-21"),
    ("GB200", "CONSTRAINED_BY", "HBM Supply", "Blackwell systems face HBM supply constraints through the ramp.", 0.85, "2024-08-28"),
    ("AI Training", "CONSTRAINED_BY", "Power Capacity", "Scaling AI training clusters is increasingly constrained by data center power capacity.", 0.88, None),
    ("AI Inference", "CONSTRAINED_BY", "Power Capacity", "Inference deployment at scale is bottlenecked by available power.", 0.82, None),
    ("Data Center", "CONSTRAINED_BY", "Power Capacity", "Data center expansion is constrained by grid power availability.", 0.9, None),
    ("Data Center", "CONSTRAINED_BY", "Cooling Infrastructure", "Higher rack densities are constrained by cooling infrastructure.", 0.85, None),
    ("CoWoS", "CONSTRAINED_BY", "Wafer Capacity", "CoWoS output is ultimately limited by upstream wafer capacity.", 0.8, None),
]


def seed_supply_chain_graph(session: Session, *, force: bool = False) -> tuple[int, int]:
    """幂等注入 NVIDIA 产业链种子数据。

    Args:
        session: 同步数据库会话。
        force: 默认 False 时，图谱已有任意实体则跳过（避免污染真实摄取数据）；
            置 True 可强制补齐缺失的种子实体与事实。

    Returns:
        (新增实体数, 新增事实数)。
    """
    if not force:
        existing = session.exec(select(GraphEntity).limit(1)).first()
        if existing:
            logger.info("supply_chain_seed_skipped", reason="graph_not_empty")
            return 0, 0

    # 1. 幂等创建实体，建立 name -> id 映射
    name_to_id: dict[str, uuid.UUID] = {}
    created_entities = 0
    for name, etype, ticker, desc in ENTITIES:
        found = session.exec(
            select(GraphEntity).where(GraphEntity.name == name)
        ).first()
        if found:
            name_to_id[name] = found.id
            continue
        entity = GraphEntity(
            entity_type=EntityType(etype),
            name=name,
            description=desc,
            ticker=ticker,
        )
        session.add(entity)
        session.flush()
        name_to_id[name] = entity.id
        created_entities += 1
    session.commit()

    # 2. 幂等创建事实（按 source/target/relation 三元组去重）
    created_facts = 0
    for src, rel, tgt, evidence, conf, event_str in FACTS:
        src_id = name_to_id.get(src)
        tgt_id = name_to_id.get(tgt)
        if not src_id or not tgt_id:
            continue
        relation = RelationType(rel)
        dup = session.exec(
            select(GraphFact).where(
                GraphFact.source_entity_id == src_id,
                GraphFact.target_entity_id == tgt_id,
                GraphFact.relation_type == relation,
            )
        ).first()
        if dup:
            continue
        event_time = datetime.strptime(event_str, "%Y-%m-%d") if event_str else None
        fact = GraphFact(
            source_entity_id=src_id,
            target_entity_id=tgt_id,
            relation_type=relation,
            evidence_text=evidence,
            confidence=conf,
            event_time=event_time,
            ingestion_time=datetime.now(UTC),
            document_section="seed",
        )
        session.add(fact)
        created_facts += 1
    session.commit()

    logger.info(
        "supply_chain_seed_done",
        created_entities=created_entities,
        created_facts=created_facts,
    )
    return created_entities, created_facts
