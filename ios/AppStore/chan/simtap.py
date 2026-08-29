#!/usr/bin/env python3
"""在 iOS 模拟器上按归一化坐标点击 / 滑动，用来自动化跑截图。

用法：
    uv run --with pyobjc-framework-Quartz --no-project python ios/AppStore/chan/simtap.py tap 0.5 0.33
    uv run --with pyobjc-framework-Quartz --no-project python ios/AppStore/chan/simtap.py swipe 0.5 0.75 0.5 0.35

坐标是**设备屏幕**的归一化值（0–1），左上角为原点，和截图上量出来的比例直接对应，
不用关心模拟器窗口被拖到了哪、缩放成了多大。

为什么不用 AppleScript：`System Events` 的 `click at` 对模拟器返回 -25204，
合成事件根本没送进去。Quartz 的 CGEvent 是系统级事件，模拟器照单全收。
"""
from __future__ import annotations

import subprocess
import sys
import time

import Quartz

# 设备宽高比（iPhone 17 Pro Max / 1320×2868）。模拟器窗口宽度撑满时，
# 屏幕高度由此算出，窗口剩下的部分是标题栏。
ASPECT = 1320 / 2868


def window_frame() -> tuple[float, float, float, float]:
    """模拟器窗口的 (x, y, w, h)，屏幕坐标系。"""
    out = subprocess.check_output([
        "osascript", "-e",
        'tell application "System Events" to tell process "Simulator" '
        'to get {position, size} of window 1',
    ], text=True).strip()
    x, y, w, h = (float(v) for v in out.split(", "))
    return x, y, w, h


def screen_rect() -> tuple[float, float, float, float]:
    """设备屏幕在屏幕坐标系里的 (x, y, w, h)，已剔除窗口标题栏。"""
    wx, wy, ww, wh = window_frame()
    sw = ww
    sh = sw / ASPECT
    # 屏幕贴着窗口底部，上方余量是标题栏
    return wx, wy + (wh - sh), sw, sh


def to_screen(nx: float, ny: float) -> tuple[float, float]:
    sx, sy, sw, sh = screen_rect()
    return sx + sw * nx, sy + sh * ny


def _post(event) -> None:
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)


def tap(nx: float, ny: float) -> None:
    x, y = to_screen(nx, ny)
    for kind in (Quartz.kCGEventLeftMouseDown, Quartz.kCGEventLeftMouseUp):
        _post(Quartz.CGEventCreateMouseEvent(
            None, kind, (x, y), Quartz.kCGMouseButtonLeft))
        time.sleep(0.05)
    print(f"tap ({nx:.3f}, {ny:.3f}) → 屏幕 ({x:.0f}, {y:.0f})")


def swipe(nx1: float, ny1: float, nx2: float, ny2: float, steps: int = 24) -> None:
    """按住拖动。用于滚动页面——一次性跳到终点模拟器会当成点击，必须分步。"""
    x1, y1 = to_screen(nx1, ny1)
    x2, y2 = to_screen(nx2, ny2)
    _post(Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventLeftMouseDown, (x1, y1), Quartz.kCGMouseButtonLeft))
    time.sleep(0.05)
    for i in range(1, steps + 1):
        t = i / steps
        _post(Quartz.CGEventCreateMouseEvent(
            None, Quartz.kCGEventLeftMouseDragged,
            (x1 + (x2 - x1) * t, y1 + (y2 - y1) * t), Quartz.kCGMouseButtonLeft))
        time.sleep(0.012)
    _post(Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventLeftMouseUp, (x2, y2), Quartz.kCGMouseButtonLeft))
    print(f"swipe ({nx1:.2f},{ny1:.2f}) → ({nx2:.2f},{ny2:.2f})")


# macOS 虚拟键码。只列截图流程用得到的：数字、字母、删除键。
KEYCODES = {
    "0": 29, "1": 18, "2": 19, "3": 20, "4": 21,
    "5": 23, "6": 22, "7": 26, "8": 28, "9": 25,
    "a": 0, "b": 11, "c": 8, "d": 2, "e": 14, "f": 3, "g": 5, "h": 4, "i": 34,
    "j": 38, "k": 40, "l": 37, "m": 46, "n": 45, "o": 31, "p": 35, "q": 12,
    "r": 15, "s": 1, "t": 17, "u": 32, "v": 9, "w": 13, "x": 7, "y": 16, "z": 6,
    "\b": 51,  # delete
    "\n": 36,  # return
}


def type_text(text: str) -> None:
    """向模拟器发送键盘事件。

    需要模拟器开着「Connect Hardware Keyboard」（I/O 菜单，默认开）。
    走 Quartz 而不是 osascript keystroke，原因同 tap。
    """
    for ch in text.lower():
        code = KEYCODES.get(ch)
        if code is None:
            raise SystemExit(f"未映射的字符：{ch!r}")
        for down in (True, False):
            _post(Quartz.CGEventCreateKeyboardEvent(None, code, down))
            time.sleep(0.02)
        time.sleep(0.04)
    print(f"type {text!r}")


def main() -> None:
    args = sys.argv[1:]
    if not args:
        raise SystemExit(__doc__)
    cmd, *rest = args
    if cmd == "tap":
        tap(float(rest[0]), float(rest[1]))
    elif cmd == "swipe":
        swipe(*(float(v) for v in rest[:4]))
    elif cmd == "type":
        type_text(rest[0])
    elif cmd == "rect":
        print("屏幕区域 (x, y, w, h) =", tuple(round(v) for v in screen_rect()))
    else:
        raise SystemExit(f"未知命令 {cmd}")


if __name__ == "__main__":
    main()
