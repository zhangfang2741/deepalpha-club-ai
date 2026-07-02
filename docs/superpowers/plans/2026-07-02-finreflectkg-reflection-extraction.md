# FinReflectKG 严格复刻 — LangGraph 图谱构建

- 论文：FinReflectKG — *Agentic Construction and Evaluation of Financial Knowledge Graphs*（arXiv:2508.17906）
- 日期：2026-07-02
- 分支：`claude/finreflectkg-langgraph-yky0il`

## 目标

严格按论文定义的点边（本体）与流水线实现金融知识图谱构建，**不复用**项目
现有的供应链 schema（5 实体/4 关系）。现有 `graph_entities`/`graph_facts`
与前端产业图谱完全不受影响，二者并存。

## 论文要点与对应实现

| 论文组件 | 实现位置 |
|---------|---------|
| 本体：24 类实体 / 29 类关系（Table 1/2） | `app/services/graph/finreflect/ontology.py` |
| 表格感知切片（table-aware chunking） | `app/services/graph/finreflect/chunker.py` |
| Schema-guided 抽取提示词 | `app/services/graph/finreflect/prompts.py` |
| 三种抽取模式（single/multi/reflection） | `app/services/graph/finreflect/graph.py`（LangGraph） |
| 反思闭环：抽取 LLM → 评审 LLM → 修正 LLM | 同上（critique/refine 节点） |
| CheckRules 规则化合规策略 + 合规率 | `app/services/graph/finreflect/checkrules.py` |
| 5 元组 + 原文证据的数据形态 | `app/models/finkg_triple.py`（`finkg_triples` 表） |

### 三元组格式（论文 5 元组）

```
(head, head_type, relation, tail, tail_type) + evidence（chunk 内原句）
```

存储时附带 CheckRules 审计结果（`compliant` / `violations`）、抽取模式与
文档溯源（`source_doc_id` / `chunk_id` / `ticker`）。

### LangGraph 图结构

```
START → extract ──┬─(single_pass)──────────────────────→ END
                  ├─(multi_pass)──→ extract_more ─┐
                  │                    ▲          │(轮次未满)
                  │                    └──────────┘ →(满)──→ END
                  └─(reflection)──→ critique ─(通过/满)──→ END
                                      ▲   │(有问题)
                                      │   ▼
                                      └─ refine
```

- **extract**：schema-guided 首轮抽取（本体动态注入提示词，filer-centric：
  申报公司=ORG，其他公司=COMP）。
- **extract_more**（multi_pass）：仅补抽遗漏三元组，按 (head, relation, tail) 去重合并。
- **critique**（reflection）：Critic LLM 审计忠实度/接地/schema 合规/实体质量/完整性，
  输出 `{approve, issues, missing}`。
- **refine**（reflection）：Corrector LLM 依反馈修订，回到 critique；
  直至通过或达 `GRAPH_REFLECTION_MAX_ITERS`。

### CheckRules（规则化合规策略）

规则检查不进反思循环（循环内评审由 Critic LLM 承担），用于终局审计与标注，
对应论文的 rule-based compliance 评估（论文反思模式合规率 64.8%）：

- P1 `entity_type_policy`：头/尾实体类型 ∈ 本体
- P2 `relation_policy`：关系类型 ∈ 本体
- P3 `well_formed_policy`：非空、非自环、名称长度合理
- P4 `grounding_policy`：证据句非空且能在原文 chunk 接地（词重合 ≥ 50%）

## 本体核实状态

arxiv/HF 原文被本环境网络策略拦截，本体从论文衍生工作（FinReflectKG-MultiHop、
EvalBench）与开源数据集文档的公开索引核实，当前收录 **19/24 实体、20/29 关系**
（类型名与论文一致，描述为自撰简述）。注册表为数据驱动——论文 Table 1/2 剩余
条目确认后直接在 `ontology.py` 两个字典中追加即可，存储列为字符串，无需迁移。

已收录实体：ORG, COMP, ORG_GOV, ORG_REG, PERSON, GPE, SECTOR, PRODUCT, EVENT,
RISK_FACTOR, FIN_METRIC, ESG_TOPIC, MACRO_CONDITION, ECON_IND, FIN_INST, CONCEPT,
REGULATORY_REQUIREMENT, LITIGATION, ACCOUNTING_POLICY

已收录关系：Has_Stake_In, Announces, Introduces, Produces, Supplies, Partners_With,
Invests_In, Operates_In, Regulates, Involved_In, Impacts, Impacted_By,
Positively_Impacts, Negatively_Impacts, Discloses, Depends_On, Related_To, Faces,
Complies_With, Subject_To

## 接入方式

`GRAPH_EXTRACTION_MODE` 环境变量切换（`.env.example` 已同步）：

- `single_pass`（默认）：旧版供应链抽取，事实入 `graph_facts`（行为不变）
- `finreflect_single` / `finreflect_multi` / `finreflect_reflection`：论文本体，
  表格感知切片，5 元组入 `finkg_triples`

辅助参数：`GRAPH_REFLECTION_MAX_ITERS`（反思修正轮上限，默认 2）、
`GRAPH_FINREFLECT_PASSES`（multi_pass 总轮数，默认 2）。

数据库迁移：`alembic/versions/c3d4e5f6a7b8_add_finkg_triples_table.py`。

## 测试

`tests/test_supply_chain_graph.py` 第 8 节（22 项新增）：本体注册表、表格感知
切片（Markdown/HTML 表格原子性、句子边界）、CheckRules 四策略、JSON 解析与
去重合并、三模式图路由（单次一调用 / 多轮去重合并 / 反思纠错 / 最大轮次止损）、
流水线端到端（finkg_triples 入库）。全套 74 项通过。
