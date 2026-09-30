"""Tests for the prompt and the answer reader (src/prompt.py).

Requirements these encode:
- make_prompt: says there is exactly one bug, names both JSON keys, contains the code
  exactly once and unchanged, and repeats the answer format after the code.
- parse_response: finds a JSON answer inside chatter or ``` fences, takes the last valid
  one, handles braces inside strings, and returns None (never crashes) on bad answers.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from prompt import Answer, make_prompt, parse_response  # noqa: E402

CODE = "def f(xs):\n    for i in range(len(xs) - 1):\n        print(xs[i])"


# ---------- make_prompt ----------

def test_prompt_says_exactly_one_bug():
    assert "exactly one bug" in make_prompt(CODE)


def test_prompt_names_both_keys():
    p = make_prompt(CODE)
    assert "buggy_line" in p and "fixed_line" in p


def test_prompt_contains_code_once_unchanged():
    assert make_prompt(CODE).count(CODE) == 1


def test_code_starts_on_its_own_line_unindented():
    assert "\n" + CODE + "\n" in make_prompt(CODE)


def test_example_answer_in_prompt_is_valid_json():
    # Small models copy the example; it must be something our reader accepts.
    assert parse_response(make_prompt("x = 1")) is not None


def test_answer_format_repeated_after_the_code():
    p = make_prompt(CODE)
    after = p[p.index(CODE) + len(CODE):]
    assert "buggy_line" in after and "fixed_line" in after


# ---------- parse_response ----------

GOOD = Answer("for i in range(len(xs) - 1):", "for i in range(len(xs)):")
GOOD_JSON = '{"buggy_line": "for i in range(len(xs) - 1):", "fixed_line": "for i in range(len(xs)):"}'


def test_plain_json():
    assert parse_response(GOOD_JSON) == GOOD


def test_json_in_code_fence():
    assert parse_response(f"```json\n{GOOD_JSON}\n```") == GOOD


def test_json_with_chatter_around_it():
    assert parse_response(f"Sure! Here is the bug:\n{GOOD_JSON}\nHope this helps.") == GOOD


def test_last_valid_answer_wins():
    draft = '{"buggy_line": "a", "fixed_line": "b"}'
    assert parse_response(f"First guess: {draft}\nActually, final: {GOOD_JSON}") == GOOD


def test_braces_inside_strings():
    text = '{"buggy_line": "d = {}", "fixed_line": "d = {1: 2}"}'
    assert parse_response(text) == Answer("d = {}", "d = {1: 2}")


def test_extra_keys_ignored():
    text = '{"buggy_line": "a", "fixed_line": "b", "reason": "x"}'
    assert parse_response(text) == Answer("a", "b")


@pytest.mark.parametrize(
    "text",
    [
        "",
        "I could not find a bug.",
        '{"buggy_line": "a"}',                     # missing key
        '{"buggy_line": 3, "fixed_line": "b"}',    # not a string
        '{"buggy_line": "a", "fixed_line": "b"',   # cut off
        "[1, 2, 3]",
    ],
)
def test_bad_answers_give_none(text):
    assert parse_response(text) is None
