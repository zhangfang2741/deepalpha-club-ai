"""Skill factor explorer API: SSE code generation, K-line pre-load, and Skill execution."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from redis.asyncio import Redis

from app.api.v1.auth import get_current_user
from app.cache.client import get_redis
from app.core.limiter import limiter
from app.core.logging import logger
from app.models.user import User
from app.schemas.skills import (
    FactorSkillBrief,
    FactorSkillDetail,
    FactorSkillGalleryResponse,
    FactorSkillMineResponse,
    KlineResponse,
    RerunRequest,
    SaveSkillRequest,
    SkillGenerateRequest,
    SkillGenerateResponse,
    SkillRunRequest,
    SkillRunResponse,
)
from app.services.skills import (
    compute_factor_snapshot,
    fetch_kline,
    generate_skill_stream,
)
from app.services.skills import SkillError, SkillSyntaxError
from app.services.skills.kline import bars_to_price_records

_executor = ThreadPoolExecutor(max_workers=4)

router = APIRouter()


@router.post("/generate")
@limiter.limit("20 per minute")
async def generate_skill(
    request: Request,
    body: SkillGenerateRequest,
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Stream Skill factor code generation via SSE.

    Each event has the format: data: {"content": "...", "done": false}
    """
    logger.info(
        "skill_generate_request",
        user_id=user.id,
        turns=len(body.messages),
    )

    async def event_generator():
        try:
            async for chunk in generate_skill_stream(body.messages):
                payload = SkillGenerateResponse(content=chunk, done=False)
                yield f"data: {payload.model_dump_json()}\n\n"
            yield f"data: {SkillGenerateResponse(content='', done=True).model_dump_json()}\n\n"
        except Exception as e:
            logger.exception("skill_generate_failed", user_id=user.id, error=str(e))
            yield f"data: {SkillGenerateResponse(content=str(e), done=True).model_dump_json()}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/kline", response_model=KlineResponse)
@limiter.limit("30 per minute")
async def get_kline(
    request: Request,
    symbol: str = Query(..., min_length=1, max_length=20),
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    freq: Literal["daily", "weekly"] = Query("daily"),
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> KlineResponse:
    """Pre-load K-line data and write to Redis cache for reuse during Skill execution."""
    from app.schemas.skills import KlineBar

    logger.info("skill_kline_request", user_id=user.id, symbol=symbol)
    try:
        bars = await fetch_kline(user.id, symbol, start_date, end_date, freq, redis=redis)
        klines = [
            KlineBar(time=b["time"], open=b["open"], high=b["high"],
                     low=b["low"], close=b["close"], volume=b["volume"])
            for b in bars
        ]
        return KlineResponse(symbol=symbol, freq=freq, klines=klines)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("skill_kline_failed", symbol=symbol, error=str(e))
        raise HTTPException(status_code=500, detail=f"K 线数据获取失败：{e}")


@router.post("/run", response_model=SkillRunResponse)
@limiter.limit("10 per minute")
async def run_skill(
    request: Request,
    body: SkillRunRequest,
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> SkillRunResponse:
    """Execute Skill code and return factor data, reusing cached price data from Redis."""
    from app.schemas.skills import FactorPoint

    logger.info("skill_run_request", user_id=user.id, symbol=body.symbol)
    try:
        bars = await fetch_kline(user.id, body.symbol, body.start_date, body.end_date, body.freq, redis=redis)
        price_records = bars_to_price_records(bars)

        result = await compute_factor_snapshot(
            body.code, price_records, body.symbol, body.start_date, body.end_date,
        )
        factor = result["factor"]
        factor_points = [FactorPoint(time=f["time"], value=f["value"]) for f in factor]
        return SkillRunResponse(
            symbol=body.symbol,
            output_type="factor",
            factor=factor_points,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("skill_run_failed", user_id=user.id, symbol=body.symbol, error=str(e))
        raise HTTPException(status_code=500, detail=f"Skill 执行失败：{e}")


@router.get("/gallery", response_model=FactorSkillGalleryResponse)
async def get_gallery(user: User = Depends(get_current_user)) -> FactorSkillGalleryResponse:
    """案例馆：Hero（pin_priority=1）+ 副网格（其余 NULL + owner_id 案例）"""
    from sqlalchemy import select, or_
    from app.db.session import get_sync_session
    from app.models.factor_skill import FactorSkill

    session = get_sync_session().__enter__()
    hero = session.exec(
        select(FactorSkill).where(
            FactorSkill.owner_id.is_(None),
            FactorSkill.pin_priority == 1,
        ).order_by(FactorSkill.created_at.desc()).limit(1)
    ).first()

    cases = session.exec(
        select(FactorSkill).where(
            FactorSkill.owner_id.is_(None),
            or_(FactorSkill.pin_priority.is_(None), FactorSkill.pin_priority > 1),
        ).order_by(FactorSkill.pin_priority.asc().nullslast(),
                   FactorSkill.created_at.desc())
    ).all()

    return FactorSkillGalleryResponse(
        hero=FactorSkillDetail.model_validate(hero) if hero else None,
        cases=[FactorSkillBrief.model_validate(c) for c in cases],
    )


@router.get("/mine", response_model=FactorSkillMineResponse)
async def get_mine(user: User = Depends(get_current_user)) -> FactorSkillMineResponse:
    """我的因子：当前用户保存的所有 skill"""
    from sqlalchemy import select
    from app.db.session import get_sync_session
    from app.models.factor_skill import FactorSkill

    session = get_sync_session().__enter__()
    skills = session.exec(
        select(FactorSkill).where(FactorSkill.owner_id == user.id)
        .order_by(FactorSkill.created_at.desc())
    ).all()
    return FactorSkillMineResponse(skills=[FactorSkillBrief.model_validate(s) for s in skills])


@router.get("/{skill_id}", response_model=FactorSkillDetail)
async def get_skill_detail(skill_id: UUID, user: User = Depends(get_current_user)) -> FactorSkillDetail:
    """详情页：返回完整 skill（含快照 + narrative）"""
    from app.db.session import get_sync_session
    from app.models.factor_skill import FactorSkill

    session = get_sync_session().__enter__()
    skill = session.get(FactorSkill, skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    if skill.owner_id is not None and skill.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    return FactorSkillDetail.model_validate(skill)


@router.post("/save", response_model=FactorSkillBrief)
async def save_skill(
    body: SaveSkillRequest,
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> FactorSkillBrief:
    """保存新 skill（生成 AI 旁白）"""
    from app.db.session import get_sync_session
    from app.models.factor_skill import FactorSkill

    session = get_sync_session().__enter__()

    # 拉 K 线（user_id 用于缓存隔离）
    kline = await fetch_kline(user.id, body.symbol, body.start_date, body.end_date, body.freq, redis=redis)
    if not kline:
        raise HTTPException(status_code=400, detail="无法获取股票数据")

    # 转换为 price_records 格式
    price_records = bars_to_price_records(kline)

    # 计算因子快照（使用 runner）
    try:
        snapshot = await compute_factor_snapshot(
            body.code, price_records, body.symbol, body.start_date, body.end_date
        )
    except (SkillError, SkillSyntaxError) as e:
        raise HTTPException(status_code=422, detail=str(e))

    # 生成 AI 旁白
    from app.services.skills import generate_narrative
    narrative = await generate_narrative(snapshot, body.symbol, body.category)

    # 写入 DB
    skill = FactorSkill(
        owner_id=user.id,
        title=body.title,
        description=body.description,
        category=body.category,
        code=body.code,
        default_symbol=body.symbol,
        default_start_date=body.start_date,
        default_end_date=body.end_date,
        default_freq=body.freq,
        snapshot_factor_jsonb=snapshot,
        narrative_jsonb=narrative,
        is_public=False,
    )
    session.add(skill)
    session.commit()
    session.refresh(skill)
    logger.info("skill_saved", user_id=user.id, skill_id=skill.id, title=skill.title)
    return FactorSkillBrief.model_validate(skill)


@router.post("/{skill_id}/rerun", response_model=dict)
async def rerun_skill(
    skill_id: UUID,
    body: RerunRequest,
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> dict:
    """换股重跑：计算结果写入 factor_runs 表"""
    from sqlalchemy import select, and_
    from app.db.session import get_sync_session
    from app.models.factor_skill import FactorSkill
    from app.models.factor_run import FactorRun
    from app.services.skills import generate_narrative

    session = get_sync_session().__enter__()
    skill = session.get(FactorSkill, skill_id)
    if not skill or (skill.owner_id is not None and skill.owner_id != user.id):
        raise HTTPException(status_code=403, detail="Not authorized")

    # 检查缓存
    existing = session.exec(
        select(FactorRun).where(
            and_(
                FactorRun.skill_id == skill_id,
                FactorRun.user_id == user.id,
                FactorRun.symbol == body.symbol,
                FactorRun.start_date == body.start_date,
                FactorRun.end_date == body.end_date,
                FactorRun.freq == body.freq,
            )
        )
    ).first()
    if existing:
        return {"cached": True, "snapshot": existing.factor_jsonb, "narrative": existing.narrative_jsonb}

    # 计算
    kline = await fetch_kline(user.id, body.symbol, body.start_date, body.end_date, body.freq, redis=redis)
    price_records = bars_to_price_records(kline)
    snapshot = await compute_factor_snapshot(skill.code, price_records, body.symbol, body.start_date, body.end_date)
    narrative = await generate_narrative(snapshot, body.symbol, skill.category)

    # 写入
    run = FactorRun(
        skill_id=skill_id,
        user_id=user.id,
        symbol=body.symbol,
        start_date=body.start_date,
        end_date=body.end_date,
        freq=body.freq,
        factor_jsonb=snapshot,
        narrative_jsonb=narrative,
    )
    session.add(run)
    session.commit()
    logger.info("skill_rerun", user_id=user.id, skill_id=skill_id, symbol=body.symbol)
    return {"cached": False, "snapshot": snapshot, "narrative": narrative}


@router.delete("/{skill_id}")
async def delete_skill(skill_id: UUID, user: User = Depends(get_current_user)) -> dict:
    """删除我的因子（仅 owner 可操作）"""
    from app.db.session import get_sync_session
    from app.models.factor_skill import FactorSkill

    session = get_sync_session().__enter__()
    skill = session.get(FactorSkill, skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Not found")
    if skill.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    session.delete(skill)
    session.commit()
    logger.info("skill_deleted", user_id=user.id, skill_id=skill_id)
    return {"ok": True}
