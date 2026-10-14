"""Tests for the hand-check sampler (src/verify.py).

Requirements these encode:
- pick_papers: n distinct papers, repeatable with a seed.
- pick_answers: n answers, half the code graded "found" and half "not found" (as far as possible), repeatable.
- where_in_file: the line number to jump to and how far down the file it is, by lines.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from verify import pick_answers, pick_papers, where_in_file  # noqa: E402

PAPERS = [{"id": f"p{i}"} for i in range(30)]
ANSWERS = [{"id": f"a{i}", "found": i < 6} for i in range(40)]  # only 6 graded found


def test_pick_papers_distinct_and_repeatable():
    a = pick_papers(PAPERS, 5, seed=1)
    assert len({p["id"] for p in a}) == 5
    assert a == pick_papers(PAPERS, 5, seed=1)


def test_pick_answers_balanced():
    picked = pick_answers(ANSWERS, 10, seed=1)
    assert len(picked) == 10
    assert sum(a["found"] for a in picked) == 5
    assert picked == pick_answers(ANSWERS, 10, seed=1)


def test_pick_answers_tops_up_when_one_side_is_short():
    few_found = [{"id": f"a{i}", "found": i < 2} for i in range(40)]
    picked = pick_answers(few_found, 10, seed=1)
    assert len(picked) == 10
    assert sum(a["found"] for a in picked) == 2


def test_where_in_file():
    row = {"text": "\n".join(f"line {i}" for i in range(1, 101)), "bug_line": 50}
    assert where_in_file(row) == (50, 0.49)  # 49 of 100 lines come before it
