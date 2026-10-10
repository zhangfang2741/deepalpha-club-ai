"""验证运营流程在前置失败或成片被替换时停止."""

import asyncio
import hashlib
import json
from pathlib import Path

import pytest

from scripts.chan_marketing import (
    OUTPUT_HEIGHT,
    OUTPUT_WIDTH,
    SAFE_HEIGHT,
    SAFE_LEFT,
    SAFE_TOP,
    SAFE_WIDTH,
    Production,
    brief_steps,
    save,
    upload,
    wait_file,
)

ROOT = Path(__file__).resolve().parents[1]


def test_marketing_fundamental_step_opens_quant_segment() -> None:
    source = (ROOT / "ios/DeepAlphaChan/Views/SignalRadar/SignalRadarView.swift").read_text()
    fundamental_branch = source.split('case "fundamental":', 1)[1].split("default:", 1)[0]

    assert "openSymbol(symbol, name: nil, segment: .quant)" in fundamental_branch


def test_error_prevents_stale_response(tmp_path: Path) -> None:
    """存在旧响应也不能掩盖本次错误."""
    response = tmp_path / "response.json"
    error = tmp_path / "error.txt"
    response.write_text('{}')
    error.write_text("登录失败")
    with pytest.raises(RuntimeError, match="登录失败"):
        asyncio.run(wait_file(response, error, timeout=1))


def test_tampered_video_cannot_upload(tmp_path: Path) -> None:
    """审核后替换视频必须在访问网络前被拒绝."""
    video = tmp_path / "video.mp4"
    video.write_bytes(b"original")
    digest = hashlib.sha256(video.read_bytes()).hexdigest()
    save(tmp_path / "production.json", Production(run_id="test", video=str(video), sha256=digest).model_dump())
    save(tmp_path / "review.json", {"sha256": digest, "visual": "passed", "audio": "passed"})
    video.write_bytes(b"changed")
    with pytest.raises(RuntimeError, match="成片哈希"):
        asyncio.run(upload(tmp_path))


def test_incomplete_review_cannot_upload(tmp_path: Path) -> None:
    """视觉通过但声音未通过时不能上传."""
    video = tmp_path / "video.mp4"
    video.write_bytes(b"original")
    digest = hashlib.sha256(video.read_bytes()).hexdigest()
    save(tmp_path / "production.json", Production(run_id="test", video=str(video), sha256=digest).model_dump())
    save(tmp_path / "review.json", {"sha256": digest, "visual": "passed", "audio": "pending"})
    with pytest.raises(RuntimeError, match="音画校验"):
        asyncio.run(upload(tmp_path))


def test_missing_platform_safe_zone_review_cannot_upload(tmp_path: Path) -> None:
    """未确认平台遮挡安全区时不能上传。"""
    video = tmp_path / "video.mp4"
    video.write_bytes(b"original")
    digest = hashlib.sha256(video.read_bytes()).hexdigest()
    save(tmp_path / "production.json", Production(run_id="test", video=str(video), sha256=digest).model_dump())
    save(tmp_path / "review.json", {"sha256": digest, "visual": "passed", "audio": "passed"})

    with pytest.raises(RuntimeError, match="音画校验"):
        asyncio.run(upload(tmp_path))


def test_atomic_save_has_no_partial_output(tmp_path: Path) -> None:
    """写入结果完整且临时文件不作为交接文件留下."""
    output = tmp_path / "nested/production.json"
    save(output, {"status": "success", "symbol": "NVDA"})
    assert json.loads(output.read_text())["status"] == "success"
    assert not output.with_suffix(".json.tmp").exists()


def test_platform_safe_zone_reserves_overlay_space() -> None:
    """关键信息区域不得进入右侧操作栏或底部文案覆盖区。"""
    right_reserved = OUTPUT_WIDTH - SAFE_LEFT - SAFE_WIDTH
    bottom_reserved = OUTPUT_HEIGHT - SAFE_TOP - SAFE_HEIGHT

    assert (OUTPUT_WIDTH, OUTPUT_HEIGHT) == (720, 1280)
    assert right_reserved >= 120
    assert bottom_reserved >= 256


def test_creative_brief_drives_distinct_steps(tmp_path: Path) -> None:
    """创意生产必须使用 brief 中的画面路径和钩子。"""
    brief = {
        "symbol": "GME",
        "steps": [
            {"step_id": "01", "layers": [], "app_action": "看原图", "on_screen_text": "GME", "narration_text": "一", "expected_visual": "原图", "overlay_text": "财报后先看结构"},
            {"step_id": "02", "layers": ["strokes"], "app_action": "开笔", "on_screen_text": "笔", "narration_text": "二", "expected_visual": "笔"},
            {"step_id": "03", "layers": ["strokes", "segments"], "app_action": "开线段", "on_screen_text": "线段", "narration_text": "三", "expected_visual": "线段"},
            {"step_id": "04", "layers": ["strokes", "segments", "pivots"], "app_action": "开中枢", "on_screen_text": "中枢", "narration_text": "四", "expected_visual": "中枢", "overlay_text": "App Store 搜索 DeepAlpha 缠论"},
        ],
    }
    path = tmp_path / "creative-brief.json"
    save(path, brief)

    steps = brief_steps(path, "GME")

    assert steps[2].layers == ["strokes", "segments"]
    assert steps[-1].overlay_text == "App Store 搜索 DeepAlpha 缠论"


def test_latest_app_brief_requires_complete_research_path(tmp_path: Path) -> None:
    """最新版 APP 创意必须在录屏前声明完整五步真实操作链。"""
    brief = {
        "symbol": "AAPL",
        "steps": [
            {"step_id": "01", "layers": [], "screen_action": "market_radar", "app_action": "切换市场雷达", "on_screen_text": "美股", "narration_text": "一", "expected_visual": "市场雷达", "overlay_text": "市场"},
            {"step_id": "02", "layers": [], "screen_action": "industry_radar", "app_action": "打开行业雷达", "on_screen_text": "行业", "narration_text": "二", "expected_visual": "行业雷达", "overlay_text": "行业"},
            {"step_id": "03", "layers": [], "screen_action": "stock_radar", "app_action": "打开个股名单", "on_screen_text": "个股", "narration_text": "三", "expected_visual": "个股名单", "overlay_text": "个股"},
            {"step_id": "04", "layers": [], "screen_action": "fundamental", "app_action": "进入基本面", "on_screen_text": "基本面", "narration_text": "四", "expected_visual": "评分与分位", "overlay_text": "基本面"},
            {"step_id": "05", "layers": ["fractals", "strokes"], "screen_action": "chan_structure", "app_action": "进入缠论结构", "on_screen_text": "结构", "narration_text": "五", "expected_visual": "缠论结构", "overlay_text": "App Store 搜索 DeepAlpha 缠论"},
        ],
    }
    path = tmp_path / "creative-brief.json"
    save(path, brief)

    steps = brief_steps(path, "AAPL")

    assert [step.screen_action for step in steps] == [
        "market_radar", "industry_radar", "stock_radar", "fundamental", "chan_structure"
    ]


def test_latest_app_brief_rejects_missing_research_layer(tmp_path: Path) -> None:
    """缺少行业或基本面等任一层时不得开始生产。"""
    brief = {
        "symbol": "AAPL",
        "steps": [
            {"step_id": "01", "layers": [], "screen_action": "market_radar", "app_action": "市场", "on_screen_text": "市场", "narration_text": "一", "expected_visual": "市场", "overlay_text": "市场"},
            {"step_id": "02", "layers": [], "screen_action": "stock_radar", "app_action": "个股", "on_screen_text": "个股", "narration_text": "二", "expected_visual": "个股"},
            {"step_id": "03", "layers": [], "screen_action": "fundamental", "app_action": "基本面", "on_screen_text": "基本面", "narration_text": "三", "expected_visual": "基本面"},
            {"step_id": "04", "layers": [], "screen_action": "chan_structure", "app_action": "结构", "on_screen_text": "结构", "narration_text": "四", "expected_visual": "结构", "overlay_text": "App Store 搜索 DeepAlpha 缠论"},
        ],
    }
    path = tmp_path / "creative-brief.json"
    save(path, brief)

    with pytest.raises(RuntimeError, match="五步真实操作链"):
        brief_steps(path, "AAPL")
