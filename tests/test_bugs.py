"""Tests for the bug injector (src/bugs.py).

Requirements these encode:
- Kinds: "comparison_flip" (< <= > >=), "eq_flip" (== !=), "off_by_one" (for-loop range).
- Each bug changes exactly one line, keeps the code valid Python, and changes its meaning (AST differs).
- The edit hits the exact operator the AST points at, never a lookalike in a string or elsewhere on the line.
"""
import ast
import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from bugs import apply_site, find_sites  # noqa: E402


def src(text: str) -> str:
    return textwrap.dedent(text).lstrip("\n")


def only_site(source: str, kind: str):
    sites = [s for s in find_sites(source) if s.kind == kind]
    assert len(sites) == 1, f"expected 1 {kind} site, got {sites}"
    return sites[0]


# ---------- comparison / equality flips ----------

@pytest.mark.parametrize(
    "op, new_op, kind",
    [
        ("<", "<=", "comparison_flip"),
        ("<=", "<", "comparison_flip"),
        (">", ">=", "comparison_flip"),
        (">=", ">", "comparison_flip"),
        ("==", "!=", "eq_flip"),
        ("!=", "==", "eq_flip"),
    ],
)
def test_each_operator_flips_to_its_partner(op, new_op, kind):
    source = f"if a {op} b:\n    pass\n"
    bug = apply_site(source, only_site(source, kind))
    assert bug.bugged_line == f"if a {new_op} b:"
    assert bug.original_line == f"if a {op} b:"
    assert bug.kind == kind
    assert bug.line == 1


def test_second_operator_on_line_is_the_one_edited():
    source = "if a <= b and c < d:\n    pass\n"
    sites = find_sites(source)
    assert len(sites) == 2
    bug = apply_site(source, sites[1])
    assert bug.bugged_line == "if a <= b and c <= d:"


def test_operator_inside_string_is_not_touched():
    source = "if s == '<' and n < 2:\n    pass\n"
    lt = only_site(source, "comparison_flip")
    bug = apply_site(source, lt)
    assert bug.bugged_line == "if s == '<' and n <= 2:"


def test_non_ascii_before_operator_uses_correct_column():
    # ast col offsets are UTF-8 bytes; "é" is 2 bytes but 1 character.
    source = 'if name == "é" and n < 2:\n    pass\n'
    bug = apply_site(source, only_site(source, "comparison_flip"))
    assert bug.bugged_line == 'if name == "é" and n <= 2:'


def test_chained_comparison_gives_one_site_per_operator():
    source = "ok = a < b <= c\n"
    sites = find_sites(source)
    assert len(sites) == 2
    assert apply_site(source, sites[0]).bugged_line == "ok = a <= b <= c"
    assert apply_site(source, sites[1]).bugged_line == "ok = a < b < c"


def test_parenthesised_operand_still_found():
    source = "ok = (a + 1) >= b\n"
    bug = apply_site(source, only_site(source, "comparison_flip"))
    assert bug.bugged_line == "ok = (a + 1) > b"


def test_comparison_spanning_lines_is_skipped():
    source = "ok = (a\n      < b)\n"
    assert find_sites(source) == []


def test_is_and_in_are_not_sites():
    source = "ok = a is None or b in c or d not in e or f is not g\n"
    assert find_sites(source) == []


# ---------- off-by-one ----------

@pytest.mark.parametrize(
    "loop, expected",
    [
        ("for i in range(len(x)):", "for i in range(len(x) - 1):"),
        ("for i in range(len(f(x))):", "for i in range(len(f(x)) - 1):"),
        ("for i in range(n):", "for i in range(n - 1):"),
        ("for i in range(self.size):", "for i in range(self.size - 1):"),
        ("for i in range(10):", "for i in range(9):"),
    ],
)
def test_off_by_one_shortens_single_arg_range(loop, expected):
    source = f"{loop}\n    pass\n"
    bug = apply_site(source, only_site(source, "off_by_one"))
    assert bug.bugged_line == expected


@pytest.mark.parametrize(
    "loop",
    [
        "for i in range(1):",              # would become range(0): loop never runs, too odd
        "for i in range(2, n):",           # two-arg range: out of scope
        "for i in range(a if c else b):",  # appending ' - 1' would change precedence
        "for i in items:",                 # not a range loop
    ],
)
def test_off_by_one_not_offered(loop):
    source = f"{loop}\n    pass\n"
    assert [s for s in find_sites(source) if s.kind == "off_by_one"] == []


def test_range_outside_for_loop_is_not_a_site():
    source = "xs = list(range(n))\n"
    assert find_sites(source) == []


# ---------- general guarantees ----------

SAMPLE = src(
    """
    def f(items, limit):
        total = 0
        for i in range(len(items)):
            if items[i] >= limit and i != 0:
                total += 1
            elif items[i] < 0:
                break
        return total == len(items) or total <= 3
    """
)


def test_sites_are_in_source_order():
    lines = [s.line for s in find_sites(SAMPLE)]
    assert lines == sorted(lines)
    assert len(lines) == 6  # range, >=, !=, <, ==, <=


def test_every_bug_is_one_line_valid_and_changes_meaning():
    original_tree = ast.dump(ast.parse(SAMPLE))
    for site in find_sites(SAMPLE):
        bug = apply_site(SAMPLE, site)
        before, after = SAMPLE.splitlines(), bug.source.splitlines()
        diff = [i for i, (x, y) in enumerate(zip(before, after)) if x != y]
        assert len(before) == len(after)
        assert diff == [bug.line - 1]
        assert before[bug.line - 1] == bug.original_line
        assert after[bug.line - 1] == bug.bugged_line
        assert ast.dump(ast.parse(bug.source)) != original_tree


def test_apply_does_not_mutate_input():
    copy = str(SAMPLE)
    apply_site(SAMPLE, find_sites(SAMPLE)[0])
    assert SAMPLE == copy


def test_no_candidates_gives_empty_list():
    assert find_sites("x = 1\nprint(x)\n") == []


def test_invalid_python_raises_syntax_error():
    with pytest.raises(SyntaxError):
        find_sites("def broken(:\n")
