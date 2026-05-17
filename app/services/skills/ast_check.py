"""Python AST 安全检查：禁止危险 builtins，禁止 os/subprocess/socket 等模块。"""
from __future__ import annotations

import ast

from app.services.skills.errors import SkillSyntaxError

_DANGEROUS_BUILTINS = frozenset({
    "open", "compile", "eval", "exec", "getattr", "setattr",
    "delattr", "__import__", "reload", "breakpoint",
})

_DANGEROUS_MODULES = frozenset({
    "os", "sys", "subprocess", "socket", "requests", "urllib",
    "http", "ftplib", "telnetlib", "pty", "tty", "termios",
    "fcntl", "select", "asyncio", "threading",
    "multiprocessing", "concurrent", "aiohttp", "httpx",
})

_DANGEROUS_PATTERNS = ("__class__", "__base__", "__subclasses__", "__globals__")


def check_code_safety(code: str) -> None:
    """解析 code，若含危险 builtins 或 imports 则抛出 SkillSyntaxError。"""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise SkillSyntaxError(f"代码语法错误：{e}") from e

    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            if node.id in _DANGEROUS_BUILTINS:
                raise SkillSyntaxError(f"禁止使用 builtin：{node.id}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name.split(".")[0]
                if name in _DANGEROUS_MODULES:
                    raise SkillSyntaxError(f"禁止导入模块：{name}")
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] in _DANGEROUS_MODULES:
                raise SkillSyntaxError(f"禁止从 {node.module.split('.')[0]} 导入")

    # 防御子类枚举逃逸
    compact = code.replace(" ", "").replace("\n", "")
    for pat in _DANGEROUS_PATTERNS:
        if pat in compact:
            raise SkillSyntaxError(f"代码包含禁止模式：{pat}")
