"""Tests for the "function alone" baseline (alone_rows in src/run.py).

Requirements these encode:
- One row per needle (not per size/depth), id "<needle_id>_alone", size "alone".
- Its text is exactly the bugged function, cut back out of a built context.
- It keeps what scoring needs (bugged_line, original_line, kind) and works with run_all.
- If the function can't be cut out cleanly, fail loudly.
"""
import json
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from dataset import build_rows, pick_needles  # noqa: E402
from run import alone_rows, run_all  # noqa: E402


def words(text):
    return len(text.split())


def cmp_fn(i):
    return f"def c{i}(a, b):\n    x = a + {i}\n\n    return x < b"  # a blank line inside, on purpose


POOL = [f"def p{i}():\n    return " + " ".join(["x"] * 8) for i in range(200)]


def built():
    needles = pick_needles([cmp_fn(i) for i in range(4)], {"comparison_flip": 3}, random.Random(0))
    rows = build_rows(needles, POOL, [300, 600], [0.1, 0.5, 0.9], words, random.Random(0))
    return needles, rows


def test_one_row_per_needle():
    needles, rows = built()
    alone = alone_rows(rows)
    assert sorted(r["id"] for r in alone) == sorted(f"n{i:02d}_alone" for i in range(len(needles)))
    assert all(r["size"] == "alone" for r in alone)


def test_text_is_exactly_the_bugged_function():
    needles, rows = built()
    by_id = {r["needle_id"]: r for r in alone_rows(rows)}
    for i, needle in enumerate(needles):
        assert by_id[f"n{i:02d}"]["text"] == needle.source


def test_keeps_scoring_fields():
    _, rows = built()
    a = alone_rows(rows)[0]
    src = next(r for r in rows if r["needle_id"] == a["needle_id"])
    for key in ("needle_id", "kind", "bugged_line", "original_line"):
        assert a[key] == src[key]


def test_works_with_run_all(tmp_path):
    _, rows = built()
    alone = alone_rows(rows)

    def perfect(prompt):
        row = next(r for r in alone if r["text"] in prompt)
        return {"text": json.dumps({"buggy_line": row["bugged_line"], "fixed_line": row["original_line"]}),
                "prompt_tokens": 50}

    out = tmp_path / "alone.jsonl"
    run_all(alone, perfect, "fake", out, seed=0)
    saved = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert len(saved) == len(alone)
    assert all(r["fixed"] for r in saved)


def test_bug_line_outside_any_block_fails_loudly():
    _, rows = built()
    broken = dict(rows[0], bug_line=10_000)
    with pytest.raises(ValueError):
        alone_rows([broken])
