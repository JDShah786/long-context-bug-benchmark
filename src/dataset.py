"""Build the test contexts: pick bugged functions (needles), pad them with other functions, save.

Run: python src/dataset.py
"""
import ast
import csv
import json
import pathlib
import random
import sys
import textwrap
from dataclasses import dataclass

from bugs import Bug, apply_site, find_sites
from haystack import build_context

SEED = 42
QUOTAS = {"comparison_flip": 30, "off_by_one": 15, "eq_flip": 5}
SIZES = [4000, 16000, 32000]
DEPTHS = [0.1, 0.5, 0.9]
NEEDLE_TOKENS = (80, 300)
MAX_FILLER_TOKENS = 300
SKIP_DIRS = {"site-packages", "test", "tests", "idlelib", "turtledemo", "__phello__"}  # site-packages = third-party code

DATA_DIR = pathlib.Path(__file__).resolve().parent.parent / "data"


@dataclass(frozen=True)
class Needle:
    original: str
    source: str
    bug: Bug


FUNCTION_NODES = (ast.FunctionDef, ast.AsyncFunctionDef)


def extract_functions(source: str) -> list[str]:
    """Top-level functions and methods of top-level classes, in file order, un-indented."""
    tree = ast.parse(source)
    lines = source.split("\n")
    nodes = []
    for node in tree.body:
        if isinstance(node, FUNCTION_NODES):
            nodes.append(node)
        elif isinstance(node, ast.ClassDef):
            nodes += [n for n in node.body if isinstance(n, FUNCTION_NODES)]

    functions = []
    for node in nodes:
        start = min([node.lineno] + [d.lineno for d in node.decorator_list])
        text = textwrap.dedent("\n".join(lines[start - 1 : node.end_lineno]))
        try:
            ast.parse(text)  # a method may not stand alone cleanly (e.g. a string at column 0)
        except SyntaxError:
            continue
        functions.append(text)
    return functions


def pick_needles(candidates: list[str], quotas: dict[str, int], rng: random.Random) -> list[Needle]:
    usable = {}  # function -> its usable sites
    for fn in candidates:
        try:
            usable[fn] = [s for s in find_sites(fn) if _bugged_line_is_unique(fn, s)]
        except SyntaxError:
            continue

    def available(kind, used):
        return [fn for fn, sites in usable.items() if fn not in used and any(s.kind == kind for s in sites)]

    used, needles = set(), []
    for kind in sorted(quotas, key=lambda k: len(available(k, used))):  # rarest kind first
        pool = available(kind, used)
        if len(pool) < quotas[kind]:
            raise ValueError(f"need {quotas[kind]} {kind} needles, only {len(pool)} candidates")
        for fn in rng.sample(pool, quotas[kind]):
            bug = apply_site(fn, rng.choice([s for s in usable[fn] if s.kind == kind]))
            needles.append(Needle(fn, bug.source, bug))
            used.add(fn)
    return needles


def _bugged_line_is_unique(fn: str, site) -> bool:
    bug = apply_site(fn, site)
    stripped = [line.strip() for line in bug.source.split("\n")]
    return stripped.count(bug.bugged_line.strip()) == 1


def fillers_for(needle: Needle, pool: list[str]) -> list[str]:
    target = needle.bug.bugged_line.strip()
    kept = []
    for fn in pool:
        if fn == needle.original:
            continue
        if any(line.strip() == target for line in fn.split("\n")):
            continue
        kept.append(fn)
    return kept


def build_rows(needles, pool, sizes, depths, count_tokens, rng) -> list[dict]:
    rows = []
    for i, needle in enumerate(needles):
        fillers = list(fillers_for(needle, pool))
        rng.shuffle(fillers)  # once per needle: every size and depth sees this same order
        for size in sizes:
            for depth in depths:
                ctx = build_context(needle.source, needle.bug.line, fillers, size, depth, count_tokens)
                rows.append({
                    "id": f"n{i:02d}_{size}_{depth}",
                    "needle_id": f"n{i:02d}",
                    "kind": needle.bug.kind,
                    "size": size,
                    "depth": depth,
                    "actual_depth": round(ctx.depth, 4),
                    "bug_line": ctx.bug_line,
                    "original_line": needle.bug.original_line,
                    "bugged_line": needle.bug.bugged_line,
                    "tokens": ctx.tokens,
                    "text": ctx.text,
                })
    return rows


def split_pool(functions, count_tokens, needle_range=NEEDLE_TOKENS, max_filler=MAX_FILLER_TOKENS):
    """Return (needle candidates, filler pool): each function once, first-seen order, filtered by size."""
    unique = list(dict.fromkeys(functions))  # e.g. ~100 identical getregentry() copies in encodings/
    sizes = {fn: count_tokens(fn) for fn in unique}
    candidates = [fn for fn in unique if needle_range[0] <= sizes[fn] <= needle_range[1]]
    pool = [fn for fn in unique if sizes[fn] <= max_filler]
    return candidates, pool


def stdlib_files(lib: pathlib.Path) -> list[pathlib.Path]:
    # Only look at folders INSIDE lib, so where Python is installed doesn't matter.
    return [p for p in sorted(lib.rglob("*.py"))
            if not SKIP_DIRS & set(p.relative_to(lib).parts[:-1])]


def _stdlib_functions() -> list[str]:
    functions = []
    for path in stdlib_files(pathlib.Path(ast.__file__).parent):
        try:
            functions += extract_functions(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
    return functions


if __name__ == "__main__":
    import tiktoken

    enc = tiktoken.get_encoding("cl100k_base")

    def count_tokens(text: str) -> int:
        return len(enc.encode(text, disallowed_special=()))

    candidates, pool = split_pool(_stdlib_functions(), count_tokens)

    rng = random.Random(SEED)
    needles = pick_needles(candidates, QUOTAS, rng)
    rows = build_rows(needles, pool, SIZES, DEPTHS, count_tokens, rng)

    DATA_DIR.mkdir(exist_ok=True)
    with open(DATA_DIR / "contexts.jsonl", "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    with open(DATA_DIR / "manifest.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[k for k in rows[0] if k != "text"])
        writer.writeheader()
        writer.writerows({k: v for k, v in row.items() if k != "text"} for row in rows)
    print(f"Python {sys.version.split()[0]}: {len(rows)} contexts from {len(needles)} needles, "
          f"{len(candidates)} candidates, {len(pool)} fillers")
