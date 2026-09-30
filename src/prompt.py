"""The prompt we send every model, and the reader that pulls its answer back out."""
import json
from dataclasses import dataclass


@dataclass(frozen=True)
class Answer:
    buggy_line: str
    fixed_line: str


def make_prompt(code: str) -> str:
    return f"""The Python code below contains exactly one bug. The bug is on a single line.
Find that line and fix it.

Reply with only a JSON object, like this:
{{"buggy_line": "<the buggy line, copied exactly>", "fixed_line": "<the fixed line, copied exactly>"}}

CODE START
{code}
CODE END

reply with only the JSON object with keys "buggy_line" and "fixed_line"."""
    


def parse_response(text: str) -> Answer | None:
    decoder = json.JSONDecoder()
    found = None
    i = text.find("{")
    while i != -1:
        try:
            obj, end = decoder.raw_decode(text, i)  # reads one JSON value starting at i
        except ValueError:
            i = text.find("{", i + 1)  # not valid JSON here: try the next "{"
            continue
        if _is_answer(obj):
            found = Answer(obj["buggy_line"], obj["fixed_line"])  # keep going: last one wins
        i = text.find("{", end)
    return found


def _is_answer(obj) -> bool:
    return (
        isinstance(obj, dict)
        and isinstance(obj.get("buggy_line"), str)
        and isinstance(obj.get("fixed_line"), str)
    )
