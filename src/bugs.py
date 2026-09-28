"""Find places in Python code where a one-line bug can be injected, and inject it.

find_sites(source) -> list[Site]   every possible bug, in source order
apply_site(source, site) -> Bug    the code with that one bug applied

A Site says: on line `line`, replace bytes [start:end] with `new`.
Offsets are UTF-8 bytes because that is what ast's col_offset uses.
"""
import ast
from dataclasses import dataclass

# ast operator type -> (text in the code, text to replace it with, bug kind)
FLIPS = {
    ast.Lt: ("<", "<=", "comparison_flip"),
    ast.LtE: ("<=", "<", "comparison_flip"),
    ast.Gt: (">", ">=", "comparison_flip"),
    ast.GtE: (">=", ">", "comparison_flip"),
    ast.Eq: ("==", "!=", "eq_flip"),
    ast.NotEq: ("!=", "==", "eq_flip"),
}


@dataclass(frozen=True)
class Site:
    kind: str
    line: int   # 1-based
    start: int  # byte offset in the line
    end: int    # byte offset in the line (start == end means insert)
    new: str


@dataclass(frozen=True)
class Bug:
    kind: str
    line: int
    original_line: str
    bugged_line: str
    source: str


def find_sites(source: str) -> list[Site]:
    tree = ast.parse(source)  # raises SyntaxError on broken code, on purpose
    lines = source.split("\n")
    sites = _comparison_sites(tree, lines) + _off_by_one_sites(tree)
    return sorted(sites, key=lambda s: (s.line, s.start))


def apply_site(source: str, site: Site) -> Bug:
    lines = source.split("\n")
    old = lines[site.line - 1]
    raw = old.encode("utf-8")
    new = (raw[: site.start] + site.new.encode("utf-8") + raw[site.end :]).decode("utf-8")
    lines[site.line - 1] = new
    return Bug(site.kind, site.line, old, new, "\n".join(lines))


def _comparison_sites(tree: ast.AST, lines: list[str]) -> list[Site]:
    sites = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        operands = [node.left] + node.comparators
        # `a < b <= c` has ops [<, <=]; op i sits between operands i and i+1.
        for i, op in enumerate(node.ops):
            if type(op) not in FLIPS:
                continue  # `is`, `in`, `not in`, `is not`
            left, right = operands[i], operands[i + 1]
            if left.end_lineno != right.lineno:
                continue  # operator may be on another line; skip to stay safe
            old_text, new_text, kind = FLIPS[type(op)]
            raw = lines[right.lineno - 1].encode("utf-8")
            gap = raw[left.end_col_offset : right.col_offset]  # e.g. b") < "
            start = left.end_col_offset + gap.index(old_text.encode())
            sites.append(Site(kind, right.lineno, start, start + len(old_text), new_text))
    return sites


def _off_by_one_sites(tree: ast.AST) -> list[Site]:
    sites = []
    for node in ast.walk(tree):
        if isinstance(node, ast.For):
            iter_node = node.iter
            if isinstance(iter_node, ast.Call) and isinstance(iter_node.func, ast.Name) and iter_node.func.id == "range" and len(iter_node.args) == 1 and not iter_node.keywords:
                arg = iter_node.args[0]
                if arg.lineno == arg.end_lineno:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, int) and not isinstance(arg.value, bool) and arg.value > 1:
                        sites.append(Site("off_by_one", arg.lineno, arg.col_offset, arg.end_col_offset, str(arg.value - 1)))
                    elif isinstance(arg, (ast.Name, ast.Call, ast.Attribute, ast.Subscript)):
                        sites.append(Site("off_by_one", arg.lineno, arg.end_col_offset, arg.end_col_offset, " - 1"))
    return sites
