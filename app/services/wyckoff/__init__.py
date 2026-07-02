"""威科夫方法论（The Wyckoff Methodology）技术分析模块。

基于价格与成交量，识别交易区间（trading range）、威科夫事件（SC/AR/ST/
Spring/SOS/UT/UTAD 等）、市场周期阶段（吸筹 / 拉升 / 派发 / 下跌），
并结合威科夫三大定律（供求 / 因果 / 量价）给出操作建议。
"""
from app.services.wyckoff.analyzer import WyckoffAnalyzer, WyckoffAnalysisResult

__all__ = ["WyckoffAnalyzer", "WyckoffAnalysisResult"]
