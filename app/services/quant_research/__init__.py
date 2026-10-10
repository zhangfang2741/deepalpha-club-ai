"""量化研究。

参照业界常见的多因子评级框架，美股六维度（估值 / 成长 / 盈利能力 / 动量 / EPS 修正 / 财务稳健）
在 GICS 板块内横向比较，每个数都能追到原始数据。

分层：grading / inputs / metrics / revisions / stage / scoring / copy 是无 IO 纯函数；
fmp / repository / batch / service / scheduler 负责拉取、落库与编排。
设计见 docs/superpowers/specs/2026-09-30-quant-research-design.md。
"""
