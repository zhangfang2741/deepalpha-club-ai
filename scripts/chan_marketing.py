"""缠论运营生产工具：真实接口筛选、中文旁白、模拟器录屏及上传校验。"""

from __future__ import annotations

import argparse
import asyncio
import fcntl
import hashlib
import json
import os
import shutil
import signal
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import structlog
from dotenv import dotenv_values
from pydantic import BaseModel, Field
from rich.console import Console
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "marketing/chan/runs"
BUNDLE = "club.deepalpha.chan"
console = Console()
structlog.configure(processors=[structlog.processors.format_exc_info, structlog.processors.JSONRenderer(ensure_ascii=False)])
logger = structlog.get_logger()


class Step(BaseModel):
    """与模拟器共用的脚本步骤。"""

    step_id: str
    time_sec: float = 0
    layers: list[str]
    app_action: str
    on_screen_text: str
    narration_text: str
    expected_visual: str
    duration_sec: float = 0


class Production(BaseModel):
    """只记录真实完成的生产结果。"""

    run_id: str
    status: str = "started"
    stage: str = "preflight"
    symbol: str = ""
    video: str = ""
    sha256: str = ""
    duration_sec: float = 0
    steps: list[Step] = Field(default_factory=list)
    checks: dict[str, Any] = Field(default_factory=dict)


def save(path: Path, value: Any) -> None:
    """用原子替换避免下游读到半份产物。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    temporary.replace(path)


async def command(*args: str) -> str:
    """执行有明确参数边界的外部工具。"""
    process = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, stderr = await process.communicate()
    if process.returncode:
        raise RuntimeError(f"{args[0]} 执行失败：{stderr.decode()[-1500:]}")
    return stdout.decode()


async def wait_file(path: Path, error: Path, timeout: float = 100) -> None:
    """只轮询执行状态，不把文件缺失当成成功。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if error.exists():
            raise RuntimeError(error.read_text())
        if path.exists():
            return
        await asyncio.sleep(0.2)
    raise TimeoutError(f"等待 {path.name} 超时；检查模拟器登录、网络和 Debug 包")


async def launch(*args: str) -> None:
    """终止并重新启动自己的模拟器 App。"""
    process = await asyncio.create_subprocess_exec("xcrun", "simctl", "terminate", "booted", BUNDLE,
                                                   stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
    await process.wait()
    config = {**dotenv_values(Path.home() / ".config/deepalpha/marketing.env"), **os.environ}
    environment = dict(os.environ)
    for source, target in [("CHAN_DEMO_ACCOUNT", "deepalphaDemoAccount"), ("CHAN_DEMO_PASSWORD", "deepalphaDemoPassword")]:
        if config.get(source):
            environment[f"SIMCTL_CHILD_{target}"] = str(config[source])
    process = await asyncio.create_subprocess_exec("xcrun", "simctl", "launch", "booted", BUNDLE,
        "-deepalphaDemo", *args, env=environment, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    _, stderr = await process.communicate()
    if process.returncode:
        raise RuntimeError(f"模拟器启动失败：{stderr.decode()[-500:]}")


async def bridge(directory: Path, request: dict[str, str]) -> dict[str, Any]:
    """借助 App 原有会话访问自己的 API，不导出登录凭证。"""
    for name in ["response.json", "error.txt"]:
        (directory / name).unlink(missing_ok=True)
    save(directory / "request.json", request)
    await launch("-marketingRequest")
    await wait_file(directory / "response.json", directory / "error.txt")
    return json.loads((directory / "response.json").read_text())


async def probe(path: Path) -> dict[str, Any]:
    """读取实际媒体信息。"""
    return json.loads(await command("ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)))


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10),
       retry=retry_if_exception_type(httpx.TransportError), reraise=True)
async def speech(text: str, path: Path) -> None:
    """在主机服务侧生成中文音频；只保存成功的响应。"""
    config = {**dotenv_values(ROOT / ".env"), **os.environ}
    key = config.get("MINIMAX_TTS_API_KEY")
    if not key:
        raise RuntimeError("未配置 MINIMAX_TTS_API_KEY")
    payload = {
        "model": config.get("MINIMAX_TTS_MODEL", "speech-2.8-hd"), "text": text,
        "stream": False, "language_boost": "Chinese", "output_format": "hex",
        "voice_setting": {"voice_id": config.get("CHAN_TTS_VOICE", "male-qn-qingse"), "speed": 1.0, "vol": 1.0, "pitch": 0},
        "audio_setting": {"sample_rate": 44100, "bitrate": 128000, "format": "mp3", "channel": 1},
    }
    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(str(config.get("MINIMAX_TTS_BASE_URL", "https://api.minimaxi.com/v1")).rstrip("/") + "/t2a_v2",
                                     headers={"Authorization": f"Bearer {key}"}, json=payload)
        response.raise_for_status()
        result = response.json()
    if result.get("base_resp", {}).get("status_code") != 0:
        raise RuntimeError(f"MiniMax 合成失败：{result.get('base_resp')}")
    audio = bytes.fromhex(result.get("data", {}).get("audio", ""))
    if not audio:
        raise RuntimeError("MiniMax 返回空音频")
    path.write_bytes(audio)


def teaching_steps(symbol: str) -> list[Step]:
    """可核验的分型与笔常青教程，不宣称最新买卖建议。"""
    return [
        Step(step_id="01", layers=[], app_action="关闭所有结构图层", on_screen_text=symbol,
             narration_text=f"看{symbol}的日线，先关掉图层，只看原始K线。", expected_visual="真实结果页，图上只有K线和MACD"),
        Step(step_id="02", layers=["fractals"], app_action="打开分型", on_screen_text="分型",
             narration_text="打开分型。红点标记顶分型，绿点标记底分型。", expected_visual="红绿分型点出现"),
        Step(step_id="03", layers=["fractals", "strokes"], app_action="打开笔", on_screen_text="笔",
             narration_text="再打开笔。蓝线连接结构，虚线表示还没有确认。", expected_visual="分型点保留，蓝色笔和未确认虚线出现"),
        Step(step_id="04", layers=["fractals", "strokes"], app_action="停留展示", on_screen_text=f"{symbol} · 日线",
             narration_text="这些是历史结构，不是收益预测。先看懂，再判断。", expected_visual="保持真实图表供观众对照"),
    ]


async def produce(args: argparse.Namespace, run: Path, state: Production) -> None:
    """按依赖顺序执行生产，上传前保留人工视觉核验入口。"""
    container = Path((await command("xcrun", "simctl", "get_app_container", "booted", BUNDLE, "data")).strip())
    directory = container / "Documents/marketing"
    directory.mkdir(parents=True, exist_ok=True)
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    candidates = []
    state.stage = "selection"
    for symbol in args.symbols:
        console.print(f"正在分析 {symbol}")
        result = await bridge(directory, {"operation": "analysis", "symbol": symbol,
            "start_date": (today - timedelta(days=365)).isoformat(), "end_date": today.isoformat(), "freq": "daily", "lang": "zh"})
        save(run / f"analysis-{symbol}.json", result)
        recent_fractals = [f for f in result.get("fractals", []) if f.get("confirmed")][-8:]
        eligible = len(recent_fractals) >= 3 and len(result.get("strokes", [])) >= 3
        candidates.append({"symbol": symbol, "eligible": eligible, "confirmed_fractals": len(recent_fractals),
                           "bars_count": result.get("bars_count"), "last_bar": result.get("merged_candles", [{}])[-1].get("time"),
                           "source": "https://api.deepalpha.club/api/v1/chan/analysis"})
    chosen = next((c for c in candidates if c["eligible"]), None)
    if chosen is None:
        raise RuntimeError("候选均无足够已确认分型和笔，停止生产")
    state.symbol = chosen["symbol"]
    selection = {"run_id": state.run_id, "date": str(today), "status": "success", "mode": "常青教学功能测试" if args.test else "常青结构教学",
                 "selected": chosen, "candidates": candidates, "note": "候选顺序由调用方给定；不把常见代码等同于当日热点，教程只讲已确认分型与笔"}
    save(run / "selection.json", selection)
    (run / "selection.md").write_text(f"# 选题回执\n\n{json.dumps(selection, ensure_ascii=False, indent=2)}\n")
    state.stage = "speech"
    state.steps = teaching_steps(state.symbol)
    elapsed = 0.0
    for step in state.steps:
        audio = run / f"voice-{step.step_id}.mp3"
        await speech(step.narration_text, audio)
        duration = float((await probe(audio))["format"]["duration"])
        step.time_sec = elapsed
        step.duration_sec = duration
        elapsed += duration + 0.6
    state.duration_sec = elapsed
    if not 20 <= elapsed <= 45:
        raise RuntimeError(f"旁白时长 {elapsed:.2f} 秒不满足 20–45 秒，需调整文案")
    save(run / "script.json", [s.model_dump() for s in state.steps])
    save(directory / "playback.json", [s.model_dump() for s in state.steps])
    state.stage = "recording"
    for name in ["ready", "start", "events.json", "error.txt"]:
        (directory / name).unlink(missing_ok=True)
    await launch("-deepalphaDemo", f"-deepalphaDemoSymbol={state.symbol}", "-marketingPlayback")
    await wait_file(directory / "ready", directory / "error.txt")
    raw = run / "screen.mp4"
    recorder = await asyncio.create_subprocess_exec("xcrun", "simctl", "io", "booted", "recordVideo", "--codec=h264", "--force", str(raw),
                                                     stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
    try:
        assert recorder.stderr is not None
        async with asyncio.timeout(15):
            while True:
                line = await recorder.stderr.readline()
                if not line:
                    raise RuntimeError("模拟器录屏启动失败")
                if b"Recording started" in line:
                    break
        await asyncio.sleep(0.3)
        (directory / "start").touch()
        await asyncio.sleep(elapsed + 0.4)
    finally:
        if recorder.returncode is None:
            recorder.send_signal(signal.SIGINT)
            await recorder.communicate()
    await wait_file(directory / "events.json", directory / "error.txt", timeout=3)
    events = json.loads((directory / "events.json").read_text())
    save(run / "events.json", events)
    # SwiftUI 在切换图层并重绘图表时会产生少量主线程调度抖动；半秒以内仍与当前旁白段严格对应。
    if len(events) != len(state.steps) or any(abs(e["actual_time_sec"] - s.time_sec) > 0.5 for e, s in zip(events, state.steps, strict=True)):
        raise RuntimeError("实际图层切换时间与旁白时间轴不一致")
    await encode(run, state, raw)


async def encode(run: Path, state: Production, raw: Path) -> None:
    """保留模拟器可变帧时间戳并输出固定帧率成片。"""
    elapsed = state.duration_sec
    state.stage = "encoding"
    output = run / "teaching.mp4"
    inputs = ["ffmpeg", "-y", "-v", "error", "-ss", "0.3", "-i", str(raw)]
    filters = []
    for index, step in enumerate(state.steps, start=1):
        inputs += ["-i", str(run / f"voice-{step.step_id}.mp3")]
        filters.append(f"[{index}:a]adelay={int(step.time_sec * 1000)}:all=1[a{index}]")
    mix = "".join(f"[a{i}]" for i in range(1, len(state.steps) + 1))
    filters.append(mix + f"amix=inputs={len(state.steps)}:normalize=0,loudnorm=I=-16:TP=-1.5:LRA=11[a]")
    await command(*inputs, "-filter_complex", ";".join(filters), "-map", "0:v", "-map", "[a]",
                  "-vf", "fps=30,scale=720:-2", "-fps_mode", "cfr", "-c:v", "libx264", "-preset", "fast", "-crf", "21", "-pix_fmt", "yuv420p",
                  "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", "-t", str(elapsed), str(output))
    metadata = await probe(output)
    codecs = {s["codec_type"]: s["codec_name"] for s in metadata["streams"]}
    if codecs.get("video") != "h264" or codecs.get("audio") != "aac":
        raise RuntimeError("成片编码不符合要求")
    await command("ffmpeg", "-v", "error", "-i", str(output), "-f", "null", "-")
    for step in state.steps:
        await command("ffmpeg", "-y", "-v", "error", "-ss", str(step.time_sec + 1), "-i", str(output),
                      "-frames:v", "1", "-pix_fmt", "yuvj420p", str(run / f"frame-{step.step_id}.jpg"))
    state.video = str(output)
    state.sha256 = hashlib.sha256(output.read_bytes()).hexdigest()
    state.checks = {"codecs": codecs, "decode": "passed", "timeline": "passed", "visual_review": "pending", "audio_review": "pending"}
    state.status = "awaiting_review"
    state.stage = "review"
    save(run / "production.json", state.model_dump())
    console.print(f"生产完成，等待逐步视觉核验：{output}")


async def upload(run: Path) -> None:
    """人工音画核验通过后，实测上传与匿名读取。"""
    state = Production.model_validate_json((run / "production.json").read_text())
    review = json.loads((run / "review.json").read_text())
    video = Path(state.video)
    digest = hashlib.sha256(video.read_bytes()).hexdigest()
    if digest != state.sha256 or review.get("sha256") != digest or review.get("visual") != "passed" or review.get("audio") != "passed":
        raise RuntimeError("缺少与成片哈希匹配的音画校验，禁止上传")
    container = Path((await command("xcrun", "simctl", "get_app_container", "booted", BUNDLE, "data")).strip())
    directory = container / "Documents/marketing"
    shutil.copyfile(video, directory / "upload.mp4")
    result = await bridge(directory, {"operation": "upload"})
    save(run / "upload.json", result)
    async with httpx.AsyncClient(timeout=45, follow_redirects=True) as client:
        head = await client.head(result["url"])
        head.raise_for_status()
        get = await client.get(result["url"])
        get.raise_for_status()
    if "video/mp4" not in head.headers.get("content-type", "") or hashlib.sha256(get.content).hexdigest() != digest:
        raise RuntimeError("公网媒体类型或内容哈希不符")
    state.checks.update(visual_review="passed", audio_review="passed", anonymous_head="passed", anonymous_get_sha256="passed")
    state.status = "ready_for_buffer"
    state.stage = "uploaded"
    save(run / "production.json", state.model_dump())
    (run / "production.md").write_text(f"# 生产与上传回执\n\n{state.model_dump_json(indent=2)}\n")
    console.print("上传和匿名 HEAD/GET 内容校验通过", result["url"])


async def main() -> None:
    """生产工具入口；Buffer 最终提交由已授权连接器执行。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["produce", "encode", "upload"])
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--symbols", nargs="+", default=["NVDA", "AAPL", "TSLA"])
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()
    if Path(args.run_id).name != args.run_id or args.run_id in {".", ".."}:
        raise ValueError("运行标识无效")
    RUNS.mkdir(parents=True, exist_ok=True)
    with (RUNS / ".production.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        run = RUNS / args.run_id
        run.mkdir(parents=True, exist_ok=True)
        state = Production(run_id=args.run_id)
        try:
            if args.action == "upload":
                await upload(run)
            elif args.action == "encode":
                state = Production.model_validate_json((run / "production.json").read_text())
                await encode(run, state, run / "screen.mp4")
            else:
                if (run / "production.json").exists():
                    raise RuntimeError("该运行已有产物，请检查并继续上传，或使用新运行标识")
                await produce(args, run, state)
        except Exception as exc:
            save(run / "failure.json", {"run_id": args.run_id, "stage": state.stage, "error": str(exc)})
            logger.exception("chan_marketing_failed", stage=state.stage)
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
