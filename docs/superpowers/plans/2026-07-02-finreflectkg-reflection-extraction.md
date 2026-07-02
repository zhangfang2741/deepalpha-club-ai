# FinReflectKG 严格复刻 — LangGraph 图谱构建

- 论文：FinReflectKG — *Agentic Construction and Evaluation of Financial Knowledge Graphs*（arXiv:2508.17906v2，ICAIF '25）
- 日期：2026-07-02（依据用户提供的论文 PDF 校准）
- 分支：`claude/finreflectkg-langgraph-yky0il`

## 目标

严格按论文定义的点边（本体）与流水线实现金融知识图谱构建，**不复用**项目
现有的供应链 schema（5 实体/4 关系）。现有 `graph_entities`/`graph_facts`
与前端产业图谱完全不受影响，二者并存。

## 论文组件与对应实现

| 论文组件 | 实现位置 |
|---------|---------|
| 本体：24 类实体 / 29 类关系（Table 1/2 为子集展示） | `app/services/graph/finreflect/ontology.py` |
| 4.2 表格感知语义切片（CHUNK_SIZE=2048，表格独立原子块） | `app/services/graph/finreflect/chunker.py` |
| 4.3 三种抽取工作流的提示词（含规范化与 Box 4.1 反馈） | `app/services/graph/finreflect/prompts.py` |
| 4.3.1-4.3.3 三种模式（LangGraph 编排） | `app/services/graph/finreflect/graph.py` |
| 5.1 CheckRules 四条规则与 CR(t) 得分（式 9） | `app/services/graph/finreflect/checkrules.py` |
| 5 元组 + 证据 + 合规标注的存储 | `app/models/finkg_triple.py`（`finkg_triples` 表） |

### 三元组格式（论文 5 元组）

```
(head, head_type, relation, tail, tail_type) + evidence（chunk 内原句）
```

存储时附带 CheckRules 审计结果（`compliant` / `violations`）、抽取模式与
文档溯源（`source_doc_id` / `chunk_id` / `ticker`）。

### 三种抽取模式（论文 4.3 节）

```
START → extract ──┬─(single_pass)─────────────────────→ END      式 (1)
                  ├─(multi_pass)──→ normalize ─────────→ END      式 (2)-(3)
                  └─(reflection)──→ critique ─(F=∅/满)─→ END      式 (4)-(7)
                                      ▲   │(有反馈)
                                      │   ▼
                                      └─ refine
```

- **single_pass**：单一综合提示词一步抽取；强制预定义类型、公司名规范化为
  ticker、严格 JSON 输出。
- **multi_pass**：第二遍将模型自身输出与原文一并重新输入，专用规范化提示词
  执行论文的四项职责——规范命名（ticker 替换）/过滤越界类型/合并重复/校验
  方向与顺序，删除或修正无效三元组。
- **reflection**：Feedback LLM 产出逐三元组结构化反馈（Box 4.1 格式：
  `{triple_number, triple, issue, suggestion}`），Correction LLM 修订或删除
  问题三元组；停止条件为 F = ∅（无反馈）或 t = n_max
  （`GRAPH_REFLECTION_MAX_ITERS`，默认 2）。

### CheckRules（论文 5.1 节，原版四规则）

规则检查不进反思循环（循环内评审由 Feedback LLM 承担），用于终局审计标注：

- R1 `subject_reference`：头/尾实体不得是抽象指代（"the company"/"we"/"our"/"it"），
  应规范化为具体实体（如 ticker）
- R2 `entity_length`：实体名 ≤ 5 个词
- R3 `entity_schema`：实体类型 ∈ 预配置 schema
- R4 `relationship_schema`：关系类型 ∈ 预配置 schema

单条得分 CR(t) = 通过规则数/4（式 9）；`compliance_score` 为通过全部四条的
三元组占比（论文 Table 4 口径，反思模式 64.8%）。论文 Table 7 显示反思模式在
LLM-as-a-Judge 的 Precision/Comprehensiveness/Relevance 三维领先。

## 本体核实状态

论文 Table 1/2 本身即为子集展示（标题注明 "Subset of Pre-Configured"），
完整 24/29 清单未在论文中枚举。当前注册表收录 **22/24 实体、22/29 关系**，来源：

1. 论文原文 Table 1/2 与正文示例（arXiv:2508.17906v2 PDF）
2. FinReflectKG-MultiHop（arXiv:2510.02906）Cypher 模式示例
3. HF 数据集 domyn/FinReflectKG README 公开索引

已收录实体：ORG, COMP, ORG_GOV, ORG_REG, PERSON, GPE, SECTOR, PRODUCT, SEGMENT,
EVENT, RISK_FACTOR, FIN_METRIC, ESG_TOPIC, MACRO_CONDITION, ECON_IND, FIN_INST,
CONCEPT, REGULATORY_REQUIREMENT, LITIGATION, ACCOUNTING_POLICY, RAW_MATERIAL,
FIN_MARKET

已收录关系：Has_Stake_In, Announces, Introduces, Produces, Supplies, Partners_With,
Invests_In, Operates_In, Regulates, Involved_In, Impacts, Impacted_By,
Positively_Impacts, Negatively_Impacts, Discloses, Depends_On, Related_To, Faces,
Complies_With, Subject_To, Causes_Shortage_Of, Market_Reacts_To

剩余 2 类实体、7 类关系见于 HF 数据集 README 完整表（本环境网络策略无法访问），
确认后在 `ontology.py` 两个字典中追加即可（数据驱动；存储列为字符串，无需迁移）。

## 接入方式

`GRAPH_EXTRACTION_MODE` 环境变量切换（`.env.example` 已同步）：

- `single_pass`（默认）：旧版供应链抽取，事实入 `graph_facts`（行为不变）
- `finreflect_single` / `finreflect_multi` / `finreflect_reflection`：论文本体，
  表格感知切片，5 元组入 `finkg_triples`

数据库迁移：`alembic/versions/c3d4e5f6a7b8_add_finkg_triples_table.py`。

## 与论文的已知差异

- 文档解析层：论文用 docling 解析 10-K（表格转 markdown、按 Item 分节标注）；
  本项目沿用既有 SEC/FMP 抓取器供文，切片层保持论文语义。
- 抽取模型：论文用 Qwen2.5-72B-Instruct；本项目经 `llm_registry` 走配置模型。
- evidence 字段：论文数据集通过 chunk 链接保留原文上下文，本实现额外为每条
  三元组存证据原句，便于审计（超集，不冲突）。

## 测试

`tests/test_supply_chain_graph.py` 第 8 节（25 项）：本体注册表、表格感知切片
（表格独立原子块、段落/句子边界、CHUNK_SIZE=2048）、CheckRules 四规则与 CR(t)、
Box 4.1 反馈解析、三模式图路由（单遍一调用 / 抽取→规范化两遍 / 反思按反馈修正 /
n_max 止损）、流水线端到端（finkg_triples 入库）。全套 77 项通过。
