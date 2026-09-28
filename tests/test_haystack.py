"""Tests for the haystack builder (src/haystack.py).

Requirements these encode:
- build_context(needle, bug_line, fillers, target_tokens, depth, count_tokens) -> Context
- Total size lands in [0.9 * target, target].
- The bugged line lands within 0.05 of the requested depth (depth = tokens before the bug line / total).
- The filler set and order are identical for every depth: only the needle's slot moves.
- Context.bug_line points at the bugged line in the full text.
- Fail loudly (ValueError) when the request can't be met.

Tests use a word counter as the tokenizer, so sizes are exact and easy to reason about.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from haystack import SEPARATOR, build_context  # noqa: E402


def words(text: str) -> int:
    return len(text.split())


NEEDLE = "def needle(a, b):\n    if a < b:\n        return 1\n    return 0"  # 11 words
BUG_LINE = 2  # "    if a < b:" (1-based, inside the needle)
FILLERS = [f"def f{i}():\n    return " + " ".join(["x"] * 8) for i in range(300)]  # 11 words each


def build(depth, target=1000, fillers=FILLERS, needle=NEEDLE, bug_line=BUG_LINE):
    return build_context(needle, bug_line, fillers, target, depth, words)


def blocks(ctx):
    return ctx.text.split(SEPARATOR)


# ---------- size and position ----------

@pytest.mark.parametrize("depth", [0.1, 0.5, 0.9])
def test_total_tokens_within_target_range(depth):
    ctx = build(depth)
    assert 900 <= ctx.tokens <= 1000
    assert ctx.tokens == words(ctx.text)


@pytest.mark.parametrize("depth", [0.1, 0.5, 0.9])
def test_bug_lands_near_requested_depth(depth):
    ctx = build(depth)
    before = "\n".join(ctx.text.split("\n")[: ctx.bug_line - 1])
    assert ctx.depth == pytest.approx(words(before) / ctx.tokens)
    assert abs(ctx.depth - depth) <= 0.05


@pytest.mark.parametrize("depth", [0.1, 0.5, 0.9])
def test_closest_slot_is_chosen_not_first_close_enough(depth):
    # Each filler is ~1% of the total, so the closest slot is within ~0.006.
    # "First slot within 0.05" would land ~0.04 early and fail this.
    assert abs(build(depth).depth - depth) <= 0.01


def test_bug_line_points_at_the_bugged_line():
    ctx = build(0.5)
    assert ctx.text.split("\n")[ctx.bug_line - 1] == "    if a < b:"


def test_deeper_request_puts_bug_later():
    lines = [build(d).bug_line for d in (0.1, 0.5, 0.9)]
    assert lines[0] < lines[1] < lines[2]


# ---------- the control: same haystack at every depth ----------

def test_same_fillers_in_same_order_at_every_depth():
    hays = [[b for b in blocks(build(d)) if b != NEEDLE] for d in (0.1, 0.5, 0.9)]
    assert hays[0] == hays[1] == hays[2]


def test_fillers_used_in_given_order_without_repeats():
    hay = [b for b in blocks(build(0.5)) if b != NEEDLE]
    assert hay == FILLERS[: len(hay)]


def test_needle_appears_exactly_once_and_intact():
    assert blocks(build(0.5)).count(NEEDLE) == 1


def test_deterministic():
    assert build(0.5) == build(0.5)


def test_filler_too_big_to_fit_is_skipped_not_truncated():
    big = "def big():\n    return " + " ".join(["y"] * 2000)
    ctx = build(0.5, fillers=[big] + FILLERS)
    assert big not in blocks(ctx)
    assert 900 <= ctx.tokens <= 1000


# ---------- failing loudly ----------

def test_not_enough_fillers_raises():
    with pytest.raises(ValueError):
        build(0.5, fillers=FILLERS[:10])  # ~110 + 11 words, far below 900


def test_needle_too_big_for_early_depth_raises():
    # 200 words before the bug line is 20% of 1000: depth 0.1 is impossible.
    padded = "def needle(a, b):\n    z = " + " ".join(["q"] * 197) + "\n    if a < b:\n        return 1"
    with pytest.raises(ValueError):
        build(0.1, needle=padded, bug_line=3)


@pytest.mark.parametrize("depth", [0.0, 1.0, -0.1, 1.5])
def test_depth_outside_open_interval_raises(depth):
    with pytest.raises(ValueError):
        build(depth)


@pytest.mark.parametrize("bug_line", [0, 5])
def test_bug_line_outside_needle_raises(bug_line):
    with pytest.raises(ValueError):
        build(0.5, bug_line=bug_line)
