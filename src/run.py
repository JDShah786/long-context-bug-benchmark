"""Ask a model about every context, grade each answer, save one line per answer.

Run:
  python src/run.py qwen --pilot              # 10 needles x 9 cells
  python src/run.py gemini --pilot --limit 1  # one call, a smoke test
Results go to results/<model>.jsonl (or <model>_pilot.jsonl). Re-running resumes.
"""
import argparse
import ast
import json
import pathlib
import random
import time

from models import DailyLimitReached, ModelUnavailable, gemini_generate, ollama_generate
from prompt import make_prompt, parse_response
from score import score
from haystack import SEPARATOR

ROOT = pathlib.Path(__file__).resolve().parent.parent
PILOT_MIX = {"comparison_flip": 6, "off_by_one": 3, "eq_flip": 1}
NUM_CTX = 40960  # room for a 32k-token context plus the prompt and answer, in any tokenizer
NEAR_LIMIT = 1024  # tokens of headroom; closer than this to num_ctx, Ollama may have cut the prompt
GEMINI_GAP = 8  # seconds between Gemini calls, to stay under the free per-minute limits

MODELS = {
    "qwen": ("qwen2.5-coder:7b", "ollama"),
    "deepseek": ("deepseek-coder-v2:16b", "ollama"),
    "gemini": ("gemini-3.8-flash", "gemini"),
    "gemini35": ("gemini-3.5-flash", "gemini"),  # fallback while 3.8 is overloaded
}

KEEP = ("id", "needle_id", "kind", "size", "depth", "actual_depth")


def run_all(rows, call, model_name, out_path, seed, num_ctx=NUM_CTX, log=print):
    out_path = pathlib.Path(out_path)
    done = set()
    if out_path.exists():
        done = {json.loads(line)["id"] for line in out_path.read_text(encoding="utf-8").splitlines() if line}
    todo = [r for r in rows if r["id"] not in done]
    random.Random(seed).shuffle(todo)  # so time effects don't line up with size or depth

    with open(out_path, "a", encoding="utf-8") as f:
        for n, row in enumerate(todo, 1):
            start = time.time()
            try:
                reply = call(make_prompt(row["text"]))
            except DailyLimitReached as e:
                log(f"Daily limit reached ({e}) after {n - 1} calls. Re-run tomorrow to resume.")
                return
            except ModelUnavailable as e:
                log(f"Model still unavailable (HTTP {e.status}) after all retries, {n - 1} calls done. "
                    f"Re-run later to resume.")
                return
            answer = parse_response(reply["text"])
            result = {
                **{k: row[k] for k in KEEP},
                "model": model_name,
                "raw": reply["text"],
                "error": reply.get("error"),
                "prompt_tokens": reply["prompt_tokens"],
                "near_limit": (reply["prompt_tokens"] or 0) >= num_ctx - NEAR_LIMIT,
                "seconds": round(time.time() - start, 2),
                "buggy_line": answer.buggy_line if answer else None,
                "fixed_line": answer.fixed_line if answer else None,
                **score(row, answer),
            }
            f.write(json.dumps(result) + "\n")
            f.flush()  # saved now, even if the run stops later
            log(f"[{n}/{len(todo)}] {row['id']} found={result['found']} fixed={result['fixed']} "
                f"({result['seconds']}s)")


def pick_pilot(rows, seed, mix=PILOT_MIX):
    rng = random.Random(seed)
    kind_of = {r["needle_id"]: r["kind"] for r in rows}
    chosen = set()
    for kind, n in mix.items():
        chosen |= set(rng.sample(sorted(k for k, v in kind_of.items() if v == kind), n))
    return [r for r in rows if r["needle_id"] in chosen]


def alone_rows(rows):
    """One row per needle whose text is just the bugged function, cut back out of a built context."""
    alone = {}
    for row in rows:
        if row["needle_id"] not in alone:
            alone[row["needle_id"]] = {**row, "id": f"{row['needle_id']}_alone", "size": "alone",
                                       "depth": None, "actual_depth": None, "text": _needle_of(row)}
    return list(alone.values())


def _needle_of(row):
    start = 1  # line number where the current block starts
    for block in row["text"].split(SEPARATOR):
        n_lines = block.count("\n") + 1
        if start <= row["bug_line"] < start + n_lines:
            lines = block.split("\n")
            if lines[row["bug_line"] - start] != row["bugged_line"]:
                break
            try:
                ast.parse(block)
            except SyntaxError:
                break  # cut in the wrong place
            return block
        start += n_lines + SEPARATOR.count("\n") - 1  # the separator adds blank lines between blocks
    raise ValueError(f"could not cut the needle out of {row['id']}")


def _make_call(name):
    model, backend = MODELS[name]
    if backend == "ollama":
        return model, lambda prompt: ollama_generate(model, prompt, num_ctx=NUM_CTX)
    key = next(line.split("=", 1)[1].strip() for line in open(ROOT / ".env")
               if line.startswith("GEMINI_API_KEY="))

    def call(prompt):
        reply = gemini_generate(model, prompt, key=key)
        time.sleep(GEMINI_GAP)
        return reply
    return model, call


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("model", choices=MODELS)
    parser.add_argument("--pilot", action="store_true")
    parser.add_argument("--alone", action="store_true", help="each bugged function with no padding (50 calls)")
    parser.add_argument("--limit", type=int, help="ask at most this many contexts")
    args = parser.parse_args()

    rows = [json.loads(line) for line in open(ROOT / "data" / "contexts.jsonl", encoding="utf-8")]
    if args.pilot:
        rows = pick_pilot(rows, seed=0)
    if args.alone:
        rows = alone_rows(rows)
    if args.limit:
        rows = rows[: args.limit]
    model, call = _make_call(args.model)
    suffix = ("_pilot" if args.pilot else "") + ("_alone" if args.alone else "")
    out = ROOT / "results" / f"{args.model}{suffix}.jsonl"
    out.parent.mkdir(exist_ok=True)
    run_all(rows, call, model, out, seed=1)
