"""Deterministic built-in skills used by the offline brain.

These are intentionally small and dependency free: they keep Jarvis useful when
no model endpoint is configured, and they double as fast paths for questions
that a language model should never be asked.
"""

from __future__ import annotations

import ast
import operator
import re
from collections.abc import Callable
from datetime import datetime, timezone

_ARITHMETIC: dict[type[ast.operator], Callable[[float, float], float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

HELP_TEXT = (
    "I can tell you the time or date, do arithmetic, and hold a conversation. "
    "Set JARVIS_API_KEY to give me a full language model."
)

NO_MODEL_TEXT = (
    "I am running on local rules only, so my answers are limited. "
    "Set JARVIS_API_KEY and JARVIS_CHAT_MODEL to bring my full mind online."
)


def _now() -> datetime:
    return datetime.now(timezone.utc).astimezone()


def _eval(node: ast.expr) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.UAdd | ast.USub):
        value = _eval(node.operand)
        return value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.BinOp):
        handler = _ARITHMETIC.get(type(node.op))
        if handler is None:
            raise ValueError("unsupported operator")
        return handler(_eval(node.left), _eval(node.right))
    raise ValueError("unsupported expression")


def evaluate_arithmetic(expression: str) -> float:
    """Evaluate a pure arithmetic expression without using ``eval``."""
    tree = ast.parse(expression, mode="eval")
    return _eval(tree.body)


def _format_number(value: float) -> str:
    if value == int(value) and abs(value) < 1e15:
        return str(int(value))
    return f"{value:.6g}"


_WORD_OPERATORS = (
    (re.compile(r"\bplus\b"), "+"),
    (re.compile(r"\bminus\b"), "-"),
    (re.compile(r"\b(?:times|multiplied by)\b"), "*"),
    (re.compile(r"\bdivided by\b"), "/"),
    (re.compile(r"\bto the power of\b"), "**"),
)

_MATH_CHARS = re.compile(r"^[0-9+\-*/%(). ]+$")


def _maybe_math(prompt: str) -> str | None:
    expression = prompt.lower()
    for prefix in ("what is", "whats", "what's", "calculate", "compute", "how much is"):
        if expression.startswith(prefix):
            expression = expression[len(prefix) :]
            break
    for pattern, symbol in _WORD_OPERATORS:
        expression = pattern.sub(symbol, expression)
    expression = expression.strip().rstrip("?=").strip()
    if not expression or not _MATH_CHARS.match(expression):
        return None
    if not any(op in expression for op in "+-*/%"):
        return None
    try:
        return _format_number(evaluate_arithmetic(expression))
    except (SyntaxError, ValueError, ZeroDivisionError, OverflowError):
        return None


def _greeting(_: str) -> str:
    return "At your service."


_MATCHERS: tuple[tuple[re.Pattern[str], Callable[[str], str]], ...] = (
    (re.compile(r"\b(what(?:'s| is)? the )?time\b"), lambda _: f"It is {_now():%H:%M}."),
    (
        re.compile(r"\b(what(?:'s| is)? (?:the )?)?(date|today)\b"),
        lambda _: f"Today is {_now():%A, %d %B %Y}.",
    ),
    (re.compile(r"^(hi|hey|hello|good (morning|evening|afternoon))\b"), _greeting),
    (re.compile(r"\b(are you (there|online|awake))\b"), lambda _: "Online and listening."),
    (re.compile(r"\b(thanks|thank you)\b"), lambda _: "Always."),
    (re.compile(r"\b(help|what can you do)\b"), lambda _: HELP_TEXT),
)


def answer_locally(prompt: str) -> str:
    """Best-effort answer produced without any model call."""
    text = prompt.strip()
    if not text:
        return "I did not catch that."

    math_answer = _maybe_math(text)
    if math_answer is not None:
        return math_answer

    lowered = text.lower()
    for pattern, handler in _MATCHERS:
        if pattern.search(lowered):
            return handler(lowered)
    return NO_MODEL_TEXT
