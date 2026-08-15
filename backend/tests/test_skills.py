from __future__ import annotations

import pytest

from jarvis.skills import HELP_TEXT, NO_MODEL_TEXT, answer_locally, evaluate_arithmetic


@pytest.mark.parametrize(
    ("expression", "expected"),
    [("2+2", 4), ("10 / 4", 2.5), ("2 ** 8", 256), ("-3 * (2 + 1)", -9)],
)
def test_evaluate_arithmetic(expression: str, expected: float) -> None:
    assert evaluate_arithmetic(expression) == expected


def test_evaluate_arithmetic_rejects_code() -> None:
    with pytest.raises(ValueError):
        evaluate_arithmetic("__import__('os').getcwd()")


@pytest.mark.parametrize(
    ("prompt", "expected"),
    [
        ("what is 21 times 2", "42"),
        ("calculate 100 divided by 8", "12.5"),
        ("whats 7 plus 5?", "12"),
    ],
)
def test_math_prompts(prompt: str, expected: str) -> None:
    assert answer_locally(prompt) == expected


def test_time_and_date_prompts() -> None:
    assert answer_locally("what's the time").startswith("It is ")
    assert answer_locally("what is the date today").startswith("Today is ")


def test_help_and_fallback() -> None:
    assert answer_locally("what can you do") == HELP_TEXT
    assert answer_locally("explain quantum tunnelling") == NO_MODEL_TEXT
    assert answer_locally("   ") == "I did not catch that."
