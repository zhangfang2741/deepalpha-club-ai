"""公司基础画像服务。

用大模型总结公司的行业、供应链位置、产品、差异化竞争力与主要竞争对手，
帮助投资者一眼建立对公司的基础认知。结果按 CIK 缓存，避免重复调用大模型。
"""

import json
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage
from redis.asyncio import Redis

from app.core.logging import logger
from app.schemas.sec_filings import CompanyProfile
from app.services.llm.service import llm_service
from app.services.sec_filings.service import sec_filings_service

_CACHE_PREFIX = "sec:profile:v2"
_CACHE_TTL = 604800  # 7天：公司基本面画像变动很慢

_SYSTEM_PROMPT = """你是一位资深的股票投资研究分析师，擅长用最精炼的语言帮投资者快速建立对一家上市公司的基础认知。

要求：
1. 全部用简体中文输出。
2. 内容客观、精准、不堆砌形容词，聚焦对投资判断有用的信息。
3. 只依据你对该公司的既有认知作答；对不确定的信息保持克制，不要编造具体数字。
4. 护城河判断参考晨星（Morningstar）式经济护城河框架，但不要声称这是晨星官方评级；需要给出自己的保守判断。
5. 市占率只能给广泛公开、你有把握的近似范围；不确定时写“未知/未披露”，不要编造精确数字。
6. 严格按要求的 JSON 结构输出，不要添加额外字段。"""


class CompanyProfileService:
    """基于公司名称/代码，用大模型生成结构化的公司基础画像。"""

    def _build_prompt(self, name: str, ticker: str, cik: str, sic: str) -> str:
        ident_parts = []
        if name:
            ident_parts.append(f"公司名称：{name}")
        if ticker:
            ident_parts.append(f"股票代码：{ticker}")
        if sic:
            ident_parts.append(f"SEC 行业分类（SIC）：{sic}")
        if cik:
            ident_parts.append(f"CIK：{cik}")
        ident = "\n".join(ident_parts)

        return f"""请为下面这家美股上市公司生成一份「投资者速览」画像。

{ident}

请输出以下字段（全部中文）：
- one_liner：一句话概括这家公司到底是做什么的（不超过 40 字，直白通俗）。
- industry：所属行业及细分赛道，一句话点明它在哪个大行业、哪个具体环节。
- supply_chain_position：在产业链/供应链中的位置，说明它处在上游/中游/下游，主要的上游供应方和下游客户是谁。
- main_products：主要产品或业务线，3-6 项。每项包含：
  - name：产品名称（简短，几个字到十几个字）。
  - explanation：用大白话解释这个产品到底是干什么用的、它如何与普通人的日常生活挂钩，最好举一个生活化的例子（1-2 句，避免堆砌专业术语）。比如「基带芯片」可以解释为「手机能打电话、上网靠它，没有它手机就连不上移动网络」。
  - market_share：该产品/业务线的市占率或市场份额估计。可以写“约 20%”“超过 70%”“全球前三”“未知/未披露”等；没有可靠把握时必须写“未知/未披露”。
- main_customers：主要客户或客户群体，3-6 项，说明产品主要卖给谁（可以是具体大客户，也可以是客户类型，如"中小企业/设计团队/云厂商"）。
- moat_rating：经济护城河判断，只能从“宽”“中”“窄”“无”四个值中选一个。参考因素包括转换成本、网络效应、规模优势、品牌、专利/监管壁垒、成本优势、数据/生态锁定等。判断要保守。
- moat_reason：用 1-2 句解释为什么给这个护城河等级。
- differentiation：在行业中的核心差异化竞争力或护城河，2-3 句，说明它凭什么区别于对手、壁垒在哪。
- competitors：主要竞争对手，列出 3-6 家公司名（可用中英文常见叫法）。"""

    async def get_profile(
        self, query: str, redis: Optional[Redis] = None
    ) -> Optional[dict]:
        """解析 ticker/CIK 并用大模型生成公司画像。

        Args:
            query: 股票代码（AAPL）或 CIK（320193）。
            redis: 可选缓存客户端。

        Returns:
            {cik, name, ticker, sic_description, profile:{...}} 或 None（无法解析公司）。
        """
        resolved = await sec_filings_service.resolve_cik(query, redis)
        if not resolved:
            return None

        cik = resolved["cik"]
        name = resolved.get("name", "")
        ticker = resolved.get("ticker", "")

        cache_key = f"{_CACHE_PREFIX}:{cik}"
        if redis is not None:
            try:
                raw = await redis.get(cache_key)
                if raw:
                    cached = json.loads(raw)
                    # 校验缓存结构与当前 schema 一致（防止旧版本缓存导致响应校验 500）
                    CompanyProfile.model_validate(cached.get("profile", {}))
                    logger.info("sec_company_profile_cache_hit", cik=cik)
                    return cached
            except Exception as e:
                # 结构不兼容或反序列化失败：忽略缓存，重新生成
                logger.warning("sec_company_profile_cache_read_error", error=str(e))

        # 尽量补全公司名与 SIC（画像质量更高）；失败不阻塞
        sic = ""
        try:
            company, _ = await sec_filings_service._fetch_all_filings(cik)
            name = company.get("name") or name
            sic = company.get("sic_description", "")
            tickers = company.get("tickers") or []
            if not ticker and tickers:
                ticker = tickers[0]
        except Exception as e:
            logger.warning("sec_company_profile_meta_fetch_error", cik=cik, error=str(e))

        if not name and not ticker:
            logger.warning("sec_company_profile_insufficient_identity", cik=cik)
            return None

        messages = [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=self._build_prompt(name, ticker, cik, sic)),
        ]

        try:
            profile: CompanyProfile = await llm_service.call(
                messages, response_format=CompanyProfile
            )
        except Exception as e:
            logger.exception("sec_company_profile_llm_failed", cik=cik, error=str(e))
            return None

        result = {
            "cik": cik,
            "name": name,
            "ticker": ticker,
            "sic_description": sic,
            "profile": profile.model_dump(),
        }

        if redis is not None:
            try:
                await redis.set(cache_key, json.dumps(result, ensure_ascii=False), ex=_CACHE_TTL)
            except Exception as e:
                logger.warning("sec_company_profile_cache_write_error", error=str(e))

        logger.info("sec_company_profile_generated", cik=cik, name=name)
        return result


# 单例
company_profile_service = CompanyProfileService()
