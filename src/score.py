"""Grade one model answer: did it answer, find the bugged line, and fix it?"""
import io
import tokenize

from prompt import Answer


def score(row: dict, answer: Answer | None) -> dict:
    if answer is None:
        return {"answered": False, "found": False, "fixed": False}
    found = _same(answer.buggy_line, row["bugged_line"])
    fixed = found and _same(answer.fixed_line, row["original_line"])
    return {"answered": True, "found": found, "fixed": fixed}


def _same(a: str, b: str) -> bool:
    return _normalize(a) == _normalize(b)


def _normalize(line: str) -> str:
    return "".join(_drop_comment(line).split())  # remove every space, tab, newline


def _drop_comment(line: str) -> str:
    # tokenize knows a '#' inside quotes is not a comment; a plain find("#") would not.
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(line.strip() + "\n").readline))
    except (tokenize.TokenError, SyntaxError):
        return line  # can't read it as code (e.g. an unclosed bracket): compare as-is
    for tok in tokens:
        if tok.type == tokenize.COMMENT:
            return line.strip()[: tok.start[1]]
    return line
