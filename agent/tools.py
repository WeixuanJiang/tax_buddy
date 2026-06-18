"""Agent tools. Currently: a safe arithmetic calculator.

LLMs are unreliable at arithmetic, so any numeric work in a tax calculation
(percentages, the CGT 50% discount, depreciation, apportioning by work-use %)
is delegated to this tool, which evaluates expressions via a restricted AST
walker — never Python's eval().
"""
from __future__ import annotations

import ast
import math
import operator

from langchain_core.tools import tool

_BIN = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
}
_UNARY = {ast.USub: operator.neg, ast.UAdd: operator.pos}
_FUNCS = {
    "round": round, "abs": abs, "min": min, "max": max, "sum": sum,
    "sqrt": math.sqrt, "floor": math.floor, "ceil": math.ceil,
}


def _eval(node):
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ValueError("only numbers are allowed")
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
        return _BIN[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_eval(node.operand))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
            and node.func.id in _FUNCS and not node.keywords:
        return _FUNCS[node.func.id](*[_eval(a) for a in node.args])
    if isinstance(node, (ast.List, ast.Tuple)):
        return [_eval(e) for e in node.elts]
    raise ValueError("unsupported expression")


def evaluate(expression: str):
    """Evaluate a numeric expression; returns a number. Raises on anything unsafe."""
    return _eval(ast.parse(expression, mode="eval").body)


@tool
def calculator(expression: str) -> str:
    """Evaluate an arithmetic expression and return the exact numeric result.

    Pass a plain arithmetic expression (Python syntax). Supports + - * / ** % //,
    parentheses, and round/abs/min/max/sum/sqrt/floor/ceil. Convert word problems
    first, e.g. "2% of 85000" -> "0.02 * 85000", a 50% CGT discount -> "gain * 0.5".

    Examples: "0.02 * 85000", "round(2800 * 0.8, 2)", "(50000 - 10000) * 0.5".
    """
    try:
        result = evaluate(expression)
        if isinstance(result, float) and result.is_integer():
            result = int(result)
        return str(result)
    except Exception as e:  # noqa: BLE001
        return f"error: could not evaluate '{expression}' ({e})"
