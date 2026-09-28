"""Tests for the dataset builder (src/dataset.py).

Requirements these encode:
- extract_functions: top-level functions only (with decorators), in file order.
- pick_needles: meets each kind's quota exactly, uses each function at most once,
  handles the rarest kind first, is repeatable with the same seed, fails loudly if short.
- fillers_for: drops the needle's own function and any filler containing the bugged line,
  so "found" scoring can never match the wrong place.
- build_rows: one row per needle x size x depth; same filler order for all of a needle's rows;
  the bugged line appears exactly once in each context; repeatable with the same seed.
"""
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from dataset import build_rows, extract_functions, fillers_for, pick_needles  # noqa: E402
from haystack import SEPARATOR  # noqa: E402


def words(text: str) -> int:
    return len(text.split())


def cmp_fn(i):
    return f"def c{i}(a, b):\n    return a < b + {i}"


def obo_fn(i):
    return f"def o{i}(xs):\n    for j in range(len(xs)):\n        print(j + {i})"


def eq_fn(i):
    return f"def e{i}(a):\n    return a == {i}"


BOTH = "def both(xs):\n    for j in range(len(xs)):\n        if j == 3:\n            print(j)"
POOL = [f"def p{i}():\n    return " + " ".join(["x"] * 8) for i in range(200)]  # no bug sites, 11 words each


# ---------- extract_functions ----------

def test_extract_functions_top_level_only_with_decorators():
    source = (
        "import os\n\n"
        "@cache\n"
        "def a(x):\n"
        "    def inner():\n"
        "        pass\n"
        "    return x\n\n"
        "class K:\n"
        "    def method(self):\n"
        "        pass\n\n"
        "def b():\n"
        "    pass\n"
    )
    assert extract_functions(source) == [
        "@cache\ndef a(x):\n    def inner():\n        pass\n    return x",
        "def b():\n    pass",
    ]


def test_extract_functions_includes_async():
    assert extract_functions("async def a():\n    pass\n") == ["async def a():\n    pass"]


# ---------- pick_needles ----------

CANDIDATES = [cmp_fn(i) for i in range(10)] + [obo_fn(i) for i in range(4)] + [eq_fn(i) for i in range(4)]
QUOTAS = {"comparison_flip": 5, "off_by_one": 3, "eq_flip": 2}


def test_quotas_met_exactly():
    needles = pick_needles(CANDIDATES, QUOTAS, random.Random(0))
    kinds = [n.bug.kind for n in needles]
    assert {k: kinds.count(k) for k in QUOTAS} == QUOTAS


def test_each_function_used_at_most_once():
    needles = pick_needles(CANDIDATES, QUOTAS, random.Random(0))
    originals = [n.original for n in needles]
    assert len(originals) == len(set(originals))


def test_needle_is_the_original_with_the_bug_applied():
    for n in pick_needles(CANDIDATES, QUOTAS, random.Random(0)):
        assert n.original in CANDIDATES
        assert n.source == n.bug.source
        assert n.source != n.original


def test_rarest_kind_is_served_first():
    # BOTH is the only off-by-one candidate. If eq_flip took it first, off_by_one would fail.
    needles = pick_needles([BOTH, eq_fn(1)], {"eq_flip": 1, "off_by_one": 1}, random.Random(0))
    by_kind = {n.bug.kind: n.original for n in needles}
    assert by_kind == {"off_by_one": BOTH, "eq_flip": eq_fn(1)}


def test_same_seed_same_needles_different_seed_can_differ():
    a = pick_needles(CANDIDATES, QUOTAS, random.Random(1))
    b = pick_needles(CANDIDATES, QUOTAS, random.Random(1))
    assert a == b
    others = [pick_needles(CANDIDATES, QUOTAS, random.Random(s)) for s in range(2, 8)]
    assert any(o != a for o in others)


def test_not_enough_candidates_raises():
    with pytest.raises(ValueError):
        pick_needles(CANDIDATES, {"off_by_one": 5}, random.Random(0))


def test_bug_that_duplicates_another_line_in_its_function_is_not_used():
    # Flipping either operator makes the two `if` lines identical.
    twin = "def d(a, b):\n    if a <= b:\n        pass\n    if a < b:\n        pass"
    with pytest.raises(ValueError):
        pick_needles([twin], {"comparison_flip": 1}, random.Random(0))


def test_unparseable_candidates_are_skipped():
    needles = pick_needles(["def broken(:"] + CANDIDATES, QUOTAS, random.Random(0))
    assert len(needles) == sum(QUOTAS.values())


# ---------- fillers_for ----------

def test_fillers_exclude_needles_own_function():
    needle = pick_needles([cmp_fn(1)], {"comparison_flip": 1}, random.Random(0))[0]
    assert cmp_fn(1) not in fillers_for(needle, [cmp_fn(1)] + POOL)


def test_fillers_exclude_any_function_containing_the_bugged_line():
    needle = pick_needles([cmp_fn(1)], {"comparison_flip": 1}, random.Random(0))[0]
    lookalike = "def other(a, b):\n    x = 1\n    " + needle.bug.bugged_line.strip()
    assert lookalike not in fillers_for(needle, [lookalike] + POOL)


def test_fillers_keep_everything_else_in_order():
    needle = pick_needles([cmp_fn(1)], {"comparison_flip": 1}, random.Random(0))[0]
    assert fillers_for(needle, POOL) == POOL


# ---------- build_rows ----------

SIZES = [300, 600]
DEPTHS = [0.1, 0.5, 0.9]


def rows_for(seed=0, pool=POOL):
    needles = pick_needles(CANDIDATES, QUOTAS, random.Random(seed))
    return needles, build_rows(needles, pool, SIZES, DEPTHS, words, random.Random(seed))


def test_one_row_per_needle_size_depth():
    needles, rows = rows_for()
    assert len(rows) == len(needles) * len(SIZES) * len(DEPTHS)
    assert len({r["id"] for r in rows}) == len(rows)


def test_row_fields():
    _, rows = rows_for()
    expected = {"id", "needle_id", "kind", "size", "depth", "actual_depth",
                "bug_line", "original_line", "bugged_line", "tokens", "text"}
    assert set(rows[0]) == expected


def test_bug_line_points_at_the_bugged_line():
    for r in rows_for()[1]:
        assert r["text"].split("\n")[r["bug_line"] - 1] == r["bugged_line"]


def test_bugged_line_appears_exactly_once():
    for r in rows_for()[1]:
        stripped = [line.strip() for line in r["text"].split("\n")]
        assert stripped.count(r["bugged_line"].strip()) == 1


def test_same_filler_order_across_sizes_and_depths_for_a_needle():
    needles, rows = rows_for()
    for i, needle in enumerate(needles):
        hays = [[b for b in r["text"].split(SEPARATOR) if b != needle.source]
                for r in rows if r["needle_id"] == f"n{i:02d}"]
        longest = max(hays, key=len)
        for hay in hays:
            it = iter(longest)
            assert all(block in it for block in hay)  # same relative order as the longest


def test_fillers_are_shuffled_not_pool_order():
    _, rows = rows_for()
    hay = [b for b in rows[0]["text"].split(SEPARATOR) if b.startswith("def p")]
    assert hay != POOL[: len(hay)]


def test_build_rows_repeatable_with_same_seed():
    assert rows_for(seed=3)[1] == rows_for(seed=3)[1]
