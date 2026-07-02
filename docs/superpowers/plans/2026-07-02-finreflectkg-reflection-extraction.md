# FinReflectKG 反思式图谱抽取（LangGraph）

- 论文：FinReflectKG — *Agentic Construction and Evaluation of Financial Knowledge Graphs*（arXiv:2508.17906）
- 日期：2026-07-02
- 分支：`claude/finreflectkg-langgraph-yky0il`

## 背景

现有图谱摄取流水线（`app/services/graph/pipeline.py`）采用**单次抽取**（single-pass）：
每个文本 chunk 调用一次 LLM 产出三元组即入库。FinReflectKG 指出，单次抽取在忠实度
（faithfulness）、schema 合规性与完整性上均有缺陷，提出**反思智能体**（reflection-agent）
范式——引入「抽取 → 评审 → 修正」闭环，在其评测中取得最佳的精确率/完整性/相关性平衡
（CheckRules 合规率 64.8%）。

本次实现用 LangGraph 复刻该反思闭环，作为流水线可选的抽取模式，**不改动**既有五类实体
（Company/Product/Technology/Concept/Resource）与四类关系（HAS_PRODUCT/SUPPLIED_BY/
ENABLED_BY/CONSTRAINED_BY）schema，保证下游产业图谱查询与前端不受影响。

## 实现

### 反思图（`app/services/graph/reflection_graph.py`）

LangGraph `StateGraph`，三个节点构成闭环：

```
START → extract → critique ──(通过/达最大轮次)──→ END
                     ▲                 │
                     └──── refine ◄──(有问题)
```

- **extract**：抽取 LLM，复用既有 `_SYSTEM_PROMPT` 产出初始三元组。
- **critique**：确定性规则检查（CheckRules）+ 评审 LLM，合并出问题清单与 `passed`。
- **refine**：修正 LLM，依反馈删改/补全三元组，轮次 +1。
- **路由**：`passed` 或 `iteration >= max_iterations` 时结束，否则回到 refine。

### CheckRules（确定性 rule-based policies）

`check_fact_rules()` 对每条三元组执行四类硬规则，对应论文 compliance policies：

1. **Schema 合规**：关系/实体类型合法，且头尾类型组合符合关系签名（如 HAS_PRODUCT 必须
   Company→Product）。
2. **证据忠实与接地**：`evidence` 非空且与原文有足够词重合（阈值 50%，防臆造）。
3. **实体良构**：头尾名非空、非自环、长度合理。
4. **置信度有效**：`confidence ∈ [0, 1]`。

`compliance_score()` 计算合规率；`filter_compliant_facts()` 作终局兜底，丢弃仍违规者。

### 接入流水线

- 配置开关 `GRAPH_EXTRACTION_MODE`（`single_pass` | `reflection`）与
  `GRAPH_REFLECTION_MAX_ITERS`（默认 2）。
- `pipeline._extract_chunk_facts()` 按模式分派；`reflection` 走
  `extract_facts_with_reflection()`，签名与 `extract_facts_from_chunk()` 对齐，可平替。
- 反思模式失败时优雅降级（返回空列表），不影响其余 chunk。

## 测试

`tests/test_supply_chain_graph.py` 新增：
- `TestCheckRules`：七项规则（合法通过 / 非法关系 / 类型签名不符 / 自环 / 证据未接地 /
  置信度越界 / 合规率与过滤）。
- `TestReflectionGraph`：评审首过不修正、修正纠正非法三元组、最大轮次止损、流水线
  reflection 模式端到端。

全部 63 项测试通过。
