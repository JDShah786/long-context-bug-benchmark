"""Tests for the analysis (src/analyze.py).

Requirements these encode:
- wilson(k, n): 95% Wilson interval for k successes out of n (values checked by hand).
- mcnemar(b, c): exact two-sided McNemar p-value from the two discordant counts.
- cell_rates: found/fixed counts and intervals per (size, depth).
- paired_test: pairs the SAME needle and size at the middle vs one end, counts the disagreements, tests them.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from analyze import baseline, cell_rates, matching_alone, mcnemar, paired_test, plot_models, series, wilson  # noqa: E402


# ---------- wilson ----------

@pytest.mark.parametrize("k, n, lo, hi", [(0, 10, 0.0, 0.2775), (5, 10, 0.2366, 0.7634), (10, 10, 0.7225, 1.0)])
def test_wilson_known_values(k, n, lo, hi):
    got = wilson(k, n)
    assert got == (pytest.approx(lo, abs=1e-4), pytest.approx(hi, abs=1e-4))


def test_wilson_needs_trials():
    with pytest.raises(ValueError):
        wilson(0, 0)


# ---------- mcnemar ----------

@pytest.mark.parametrize("b, c, p", [(0, 0, 1.0), (0, 6, 0.03125), (6, 0, 0.03125), (1, 5, 0.21875), (3, 3, 1.0)])
def test_mcnemar_exact(b, c, p):
    assert mcnemar(b, c) == pytest.approx(p)


# ---------- cell_rates / paired_test ----------

def result(needle, size, depth, found, fixed=False):
    return {"needle_id": needle, "size": size, "depth": depth, "found": found, "fixed": fixed}


def test_cell_rates_counts_and_intervals():
    rows = [result("n1", 4000, 0.5, True, True), result("n2", 4000, 0.5, False), result("n1", 4000, 0.1, False)]
    cells = {(c["size"], c["depth"]): c for c in cell_rates(rows)}
    mid = cells[(4000, 0.5)]
    assert (mid["n"], mid["found"], mid["fixed"]) == (2, 1, 1)
    assert (mid["found_lo"], mid["found_hi"]) == wilson(1, 2)
    assert cells[(4000, 0.1)]["found"] == 0


def test_paired_test_counts_disagreements_on_same_needle_and_size():
    rows = [
        # n1: found at middle, missed at 10%   -> counts for "middle better"
        result("n1", 4000, 0.5, True), result("n1", 4000, 0.1, False),
        # n2: missed at middle, found at 10%   -> counts for "end better"
        result("n2", 4000, 0.5, False), result("n2", 4000, 0.1, True),
        # n3: found at both                     -> agreement, ignored
        result("n3", 4000, 0.5, True), result("n3", 4000, 0.1, True),
        # n4 at 16k: missed at middle, found at 10%
        result("n4", 16000, 0.5, False), result("n4", 16000, 0.1, True),
        # n5: middle only, no 10% partner       -> skipped
        result("n5", 4000, 0.5, True),
    ]
    out = paired_test(rows, end=0.1)
    assert (out["middle_only"], out["end_only"], out["pairs"]) == (1, 2, 4)
    assert out["p"] == pytest.approx(mcnemar(1, 2))


def test_paired_test_can_filter_by_size():
    rows = [result("n1", 4000, 0.5, True), result("n1", 4000, 0.9, False),
            result("n1", 16000, 0.5, False), result("n1", 16000, 0.9, True)]
    assert paired_test(rows, end=0.9, size=4000)["middle_only"] == 1
    assert paired_test(rows, end=0.9, size=4000)["end_only"] == 0


# ---------- chart data + picture ----------

def grid(found_at):
    """2 needles x 2 sizes x 3 depths; found only where found_at(needle, size, depth) says."""
    return [result(n, s, d, found_at(n, s, d)) for n in ("n1", "n2") for s in (4000, 16000) for d in (0.1, 0.5, 0.9)]


def test_series_one_line_per_size_in_depth_order():
    rows = grid(lambda n, s, d: d != 0.5)  # everything found except the middle
    lines = series(rows)
    assert sorted(lines) == [4000, 16000]
    depths = [p[0] for p in lines[4000]]
    rates = [p[1] for p in lines[4000]]
    assert depths == [0.1, 0.5, 0.9]
    assert rates == [1.0, 0.0, 1.0]
    lo, hi = lines[4000][1][2:]
    assert (lo, hi) == wilson(0, 2)


def test_series_ignores_alone_rows():
    rows = grid(lambda n, s, d: True) + [result("n1", "alone", None, True)]
    assert "alone" not in series(rows)


def test_baseline_rate_and_interval():
    alone = [result("n1", "alone", None, True), result("n2", "alone", None, False)]
    assert baseline(alone) == (0.5, *wilson(1, 2))


def test_plot_writes_a_png(tmp_path):
    out = tmp_path / "fig.png"
    plot_models({"Model A": (grid(lambda n, s, d: d == 0.1), None),
                 "Model B": (grid(lambda n, s, d: True), [result("n1", "alone", None, True)])}, out)
    assert out.exists() and out.read_bytes()[:4] == b"\x89PNG"


def test_matching_alone_keeps_only_the_same_bugs():
    results = grid(lambda n, s, d: False)  # needles n1, n2
    alone = [result("n1", "alone", None, True), result("n2", "alone", None, False), result("n9", "alone", None, True)]
    assert [a["needle_id"] for a in matching_alone(results, alone)] == ["n1", "n2"]
