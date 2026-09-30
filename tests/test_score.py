"""Tests for the scorer (src/score.py).

Requirements these encode:
- score(row, answer) -> {"answered", "found", "fixed"}, all bools.
- found: quoted line == bugged line; fixed: found and fix == original line.
- Comparison ignores all whitespace and trailing comments, nothing else.
- No answer scores all False.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from prompt import Answer  # noqa: E402
from score import score  # noqa: E402

ROW = {
    "original_line": "        for i in range(len(xs)):  # walk every item",
    "bugged_line": "        for i in range(len(xs) - 1):  # walk every item",
}
BUGGED = "for i in range(len(xs) - 1):"
ORIGINAL = "for i in range(len(xs)):"


def test_found_and_fixed():
    assert score(ROW, Answer(BUGGED, ORIGINAL)) == {"answered": True, "found": True, "fixed": True}


def test_found_but_wrong_fix():
    assert score(ROW, Answer(BUGGED, "for i in range(len(xs) + 1):")) == {
        "answered": True, "found": True, "fixed": False}


def test_wrong_line():
    assert score(ROW, Answer("print(xs[i])", ORIGINAL)) == {"answered": True, "found": False, "fixed": False}


def test_no_answer():
    assert score(ROW, None) == {"answered": False, "found": False, "fixed": False}


@pytest.mark.parametrize(
    "quoted",
    [
        "for i in range(len(xs)-1):",                        # spacing differs
        "        for i in range(len(xs) - 1):",              # indentation kept
        "for i in range(len(xs) - 1):  # walk every item",   # comment kept
        "for i in range(len(xs) - 1):  # a different comment",
    ],
)
def test_whitespace_and_comments_ignored(quoted):
    assert score(ROW, Answer(quoted, ORIGINAL))["found"]


def test_hash_inside_string_is_not_a_comment():
    row = {"original_line": "if s == '#':", "bugged_line": "if s != '#':"}
    assert not score(row, Answer("if s != '':", "if s == '':"))["found"]
    assert score(row, Answer("if s != '#':", "if s == '#':"))["fixed"]


def test_fix_equal_to_original_but_wrong_line_is_not_fixed():
    assert not score(ROW, Answer("print(xs[i])", ORIGINAL))["fixed"]


def test_different_code_is_not_equal():
    assert not score(ROW, Answer("for i in range(len(ys) - 1):", ORIGINAL))["found"]
