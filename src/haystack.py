"""Hide a bugged function (the needle) among unrelated functions (the haystack).

The fillers are chosen once per (needle, target size). Only the needle's slot
changes with depth, so every depth sees the same haystack.
"""
from dataclasses import dataclass
from typing import Callable

SEPARATOR = "\n\n\n"  # two blank lines between top-level functions, as in PEP 8
SAFETY = 0.99  # aim 1% under target: token counts of joined text can differ slightly from the sum of parts
MIN_FILL = 0.9
TOLERANCE = 0.05


@dataclass(frozen=True)
class Context:
    text: str
    bug_line: int  # 1-based line of the bug in `text`
    depth: float   # tokens before the bug line / total tokens
    tokens: int


def build_context(
    needle: str,
    bug_line: int,
    fillers: list[str],
    target_tokens: int,
    depth: float,
    count_tokens: Callable[[str], int],
) -> Context:
    if not 0 < depth < 1:
        raise ValueError(f"depth must be between 0 and 1, got {depth}")
    if not 1 <= bug_line <= len(needle.split("\n")):
        raise ValueError(f"bug_line {bug_line} is outside the needle")

    chosen = _pick_fillers(needle, fillers, target_tokens, count_tokens)
    slot = _choose_slot(needle, bug_line, chosen, depth, count_tokens)
    ctx = _assemble(needle, bug_line, chosen, slot, count_tokens)

    if ctx.tokens > target_tokens:
        raise ValueError(f"context is {ctx.tokens} tokens, over target {target_tokens}")
    if abs(ctx.depth - depth) > TOLERANCE:
        raise ValueError(f"closest depth is {ctx.depth:.3f}, requested {depth}")
    return ctx


def _pick_fillers(needle, fillers, target_tokens, count_tokens) -> list[str]:
    budget = SAFETY * target_tokens
    total = count_tokens(needle)
    chosen = []
    for filler in fillers:
        cost = count_tokens(SEPARATOR + filler)
        if total + cost > budget:
            continue  # too big to fit: skip it whole, a smaller one may still fit
        chosen.append(filler)
        total += cost
    if total < MIN_FILL * target_tokens:
        raise ValueError(f"only {total} tokens of material for target {target_tokens}")
    return chosen


def _assemble(needle, bug_line, chosen, slot, count_tokens) -> Context:
    text = SEPARATOR.join(chosen[:slot] + [needle] + chosen[slot:])
    head = SEPARATOR.join(chosen[:slot]) + SEPARATOR if slot else ""
    line = head.count("\n") + bug_line
    before = "\n".join(text.split("\n")[: line - 1])
    tokens = count_tokens(text)
    return Context(text, line, count_tokens(before) / tokens, tokens)


def _choose_slot(needle, bug_line, chosen, depth, count_tokens) -> int:
    best_slot = 0
    best_gap = float("inf")
    for slot in range(len(chosen) + 1):
        slotcheck = _assemble(needle, bug_line, chosen, slot, count_tokens)
        gap = abs(slotcheck.depth - depth)
        if gap < best_gap:
            best_slot = slot
            best_gap = gap
    return best_slot
