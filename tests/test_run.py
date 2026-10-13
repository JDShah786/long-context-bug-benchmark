"""Tests for the run loop (src/run.py). Uses fake model calls; no network, no GPU.

Requirements these encode:
- run_all: one saved line per row (prompt -> call -> parse -> score), written as it goes.
- Resume: rows already in the output file are skipped, not re-asked.
- Order: shuffled with a seed (repeatable), so time effects don't line up with size or depth.
- Bad replies are saved as answered=False, not dropped.
- DailyLimitReached stops cleanly and keeps everything saved so far.
- pick_pilot: 10 needles in a 6/3/1 kind mix, all 9 cells each, repeatable.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from models import DailyLimitReached  # noqa: E402
from run import pick_pilot, run_all  # noqa: E402


def make_rows(n_needles=4, kinds=("comparison_flip",)):
    rows = []
    for i in range(n_needles):
        for size in (4000, 16000, 32000):
            for depth in (0.1, 0.5, 0.9):
                rows.append({
                    "id": f"n{i:02d}_{size}_{depth}", "needle_id": f"n{i:02d}",
                    "kind": kinds[i % len(kinds)], "size": size, "depth": depth, "actual_depth": depth,
                    "bug_line": 2, "original_line": f"    if a{i} < b:", "bugged_line": f"    if a{i} <= b:",
                    "tokens": size, "text": f"def f{i}(a{i}, b):\n    if a{i} <= b:\n        pass",
                })
    return rows


def perfect(prompt):
    i = prompt.split("def f")[1].split("(")[0]
    return {"text": json.dumps({"buggy_line": f"if a{i} <= b:", "fixed_line": f"if a{i} < b:"}),
            "prompt_tokens": 123}


def read(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_one_line_per_row_with_scores(tmp_path):
    rows, out = make_rows(), tmp_path / "out.jsonl"
    run_all(rows, perfect, "fake", out, seed=0)
    saved = read(out)
    assert sorted(r["id"] for r in saved) == sorted(r["id"] for r in rows)
    assert all(r["answered"] and r["found"] and r["fixed"] for r in saved)
    first = saved[0]
    for key in ("id", "model", "needle_id", "kind", "size", "depth", "actual_depth",
                "raw", "prompt_tokens", "seconds", "answered", "found", "fixed"):
        assert key in first
    assert first["model"] == "fake"
    assert "text" not in first  # don't copy the 32k-token context into every result


def test_resume_skips_rows_already_saved(tmp_path):
    rows, out = make_rows(), tmp_path / "out.jsonl"
    run_all(rows[:5], perfect, "fake", out, seed=0)
    asked = []
    run_all(rows, lambda p: asked.append(p) or perfect(p), "fake", out, seed=0)
    assert len(asked) == len(rows) - 5
    assert len(read(out)) == len(rows)


def test_order_is_shuffled_and_repeatable(tmp_path):
    rows = make_rows()
    orders = []
    for name in ("a", "b"):
        out = tmp_path / f"{name}.jsonl"
        run_all(rows, perfect, "fake", out, seed=7)
        orders.append([r["id"] for r in read(out)])
    assert orders[0] == orders[1]
    assert orders[0] != [r["id"] for r in rows]


def test_bad_reply_saved_as_not_answered(tmp_path):
    out = tmp_path / "out.jsonl"
    run_all(make_rows(1), lambda p: {"text": "no idea", "prompt_tokens": None}, "fake", out, seed=0)
    saved = read(out)
    assert len(saved) == 9
    assert not any(r["answered"] for r in saved)
    assert saved[0]["raw"] == "no idea"


def test_daily_limit_stops_and_keeps_progress(tmp_path):
    out, count = tmp_path / "out.jsonl", {"n": 0}

    def flaky(prompt):
        count["n"] += 1
        if count["n"] > 3:
            raise DailyLimitReached("per day")
        return perfect(prompt)

    run_all(make_rows(), flaky, "fake", out, seed=0)  # must not raise
    assert len(read(out)) == 3


# ---------- pick_pilot ----------

def test_pilot_is_10_needles_all_cells_in_kind_mix():
    rows = make_rows(50, kinds=("comparison_flip",) * 6 + ("off_by_one",) * 3 + ("eq_flip",))
    pilot = pick_pilot(rows, seed=0)
    needles = {r["needle_id"] for r in pilot}
    assert len(needles) == 10
    assert len(pilot) == 90
    kinds = {r["needle_id"]: r["kind"] for r in pilot}
    assert sorted(kinds.values()).count("comparison_flip") == 6
    assert sorted(kinds.values()).count("off_by_one") == 3
    assert sorted(kinds.values()).count("eq_flip") == 1


def test_pilot_repeatable():
    rows = make_rows(50, kinds=("comparison_flip",) * 6 + ("off_by_one",) * 3 + ("eq_flip",))
    assert pick_pilot(rows, seed=0) == pick_pilot(rows, seed=0)


def test_answer_near_context_limit_is_flagged(tmp_path):
    out = tmp_path / "out.jsonl"
    near = lambda p: {**perfect(p), "prompt_tokens": 40900}
    run_all(make_rows(1), near, "fake", out, seed=0, num_ctx=40960)
    assert all(r["near_limit"] for r in read(out))
    run_all(make_rows(1), perfect, "fake", tmp_path / "ok.jsonl", seed=0, num_ctx=40960)
    assert not any(r["near_limit"] for r in read(tmp_path / "ok.jsonl"))


def test_model_error_is_saved_as_no_answer(tmp_path):
    out = tmp_path / "out.jsonl"
    looped = lambda p: {"text": "", "prompt_tokens": None, "error": "token repeat limit reached"}
    run_all(make_rows(1), looped, "fake", out, seed=0)
    saved = read(out)
    assert len(saved) == 9
    assert not any(r["answered"] for r in saved)
    assert saved[0]["error"] == "token repeat limit reached"
