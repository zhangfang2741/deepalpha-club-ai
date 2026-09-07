"""验证运营流程在前置失败或成片被替换时停止."""

import asyncio
import hashlib
import json
from pathlib import Path

import pytest

from scripts.chan_marketing import Production, save, upload, wait_file


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


def test_atomic_save_has_no_partial_output(tmp_path: Path) -> None:
    """写入结果完整且临时文件不作为交接文件留下."""
    output = tmp_path / "nested/production.json"
    save(output, {"status": "success", "symbol": "NVDA"})
    assert json.loads(output.read_text())["status"] == "success"
    assert not output.with_suffix(".json.tmp").exists()
