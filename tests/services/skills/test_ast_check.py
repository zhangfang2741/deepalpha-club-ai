"""AST 安全检查测试"""
import pytest
from app.services.skills.ast_check import check_code_safety
from app.services.skills.errors import SkillSyntaxError

def test_safe_code_passes():
    code = """
import pandas as pd
import numpy as np
def compute(prices, symbol):
    return [{'time': p['date'], 'value': p['close']} for p in prices]
"""
    check_code_safety(code)  # 不抛异常

def test_dangerous_import_rejected():
    for dangerous in ["import os", "import subprocess", "import socket", "import sys"]:
        with pytest.raises(SkillSyntaxError):
            check_code_safety(dangerous + "\ndef compute(p,s): return []")

def test_dangerous_pattern_rejected():
    for pattern in ["__class__", "__base__", "__subclasses__"]:
        with pytest.raises(SkillSyntaxError):
            check_code_safety(f"x = 1  # {pattern}\ndef compute(p,s): return []")

def test_dangerous_builtin_rejected():
    for builtin in ["open", "compile", "eval", "exec"]:
        with pytest.raises(SkillSyntaxError):
            check_code_safety(f"{builtin}('x')\ndef compute(p,s): return []")