"""Pull random samples for a human to check by hand.

  python src/verify.py papers   # saves 5 papers to verify/papers/ and says which line to look at
  python src/verify.py grade    # shows 10 model answers, you grade them, then compares with the code
"""
import ast
import csv
import json
import pathlib
import random
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
RESULT_FILES = ["qwen_pilot", "deepseek_pilot", "qwen_alone", "deepseek_alone"]


def pick_papers(rows, n, seed):
    return random.Random(seed).sample(rows, n)


def pick_answers(answers, n, seed):
    """Half graded found by the code, half not; if one side is short, the other side fills the gap."""
    rng = random.Random(seed)
    found = [a for a in answers if a["found"]]
    missed = [a for a in answers if not a["found"]]
    take_found = min(len(found), n // 2)
    picked = rng.sample(found, take_found) + rng.sample(missed, n - take_found)
    rng.shuffle(picked)  # so the order doesn't give the grade away
    return picked


def where_in_file(row):
    lines = row["text"].split("\n")
    return row["bug_line"], round((row["bug_line"] - 1) / len(lines), 2)


def _load(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def check_papers(seed=7, n=5):
    rows = _load(ROOT / "data" / "contexts.jsonl")
    out_dir = ROOT / "verify" / "papers"
    out_dir.mkdir(parents=True, exist_ok=True)
    lib = pathlib.Path(ast.__file__).parent
    print(f"Real Python source to compare against: {lib}\n")
    for row in pick_papers(rows, n, seed):
        path = out_dir / f"{row['id']}.py"
        path.write_text(row["text"], encoding="utf-8")
        line, frac = where_in_file(row)
        print(f"{path.relative_to(ROOT)}")
        print(f"  Ctrl+G to line {line}. Expect:    {row['bugged_line'].strip()}")
        print(f"  The original Python line was:   {row['original_line'].strip()}")
        print(f"  Target position {int(100 * row['depth'])}%; by line count it is {int(100 * frac)}% down the file.\n")


def check_grades(seed=7, n=10):
    contexts = {}
    for line in (ROOT / "data" / "contexts.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        contexts.setdefault(r["needle_id"], r)  # bug and original lines are the same for every paper of a needle
    answers = []
    for name in RESULT_FILES:
        path = ROOT / "results" / f"{name}.jsonl"
        if path.exists():
            answers += [dict(a, source=name) for a in _load(path) if a["answered"]]

    rows, agree = [], 0
    for i, a in enumerate(pick_answers(answers, n, seed), 1):
        c = contexts[a["needle_id"]]
        print(f"\n--- {i}/{n} ---")
        print(f"Real bugged line:   {c['bugged_line'].strip()}")
        print(f"Correct line:       {c['original_line'].strip()}")
        print(f"Model quoted:       {(a['buggy_line'] or '').strip()}")
        print(f"Model's fix:        {(a['fixed_line'] or '').strip()}")
        you_found = input("Did it find the bug? (y/n) ").strip().lower() == "y"
        you_fixed = you_found and input("Is the fix correct? (y/n) ").strip().lower() == "y"
        same = (you_found, you_fixed) == (a["found"], a["fixed"])
        agree += same
        print(f"Code said: found={a['found']} fixed={a['fixed']}  ->  {'AGREE' if same else 'DISAGREE'}")
        rows.append({"source": a["source"], "id": a["id"], "you_found": you_found, "you_fixed": you_fixed,
                     "code_found": a["found"], "code_fixed": a["fixed"], "agree": same})

    out = ROOT / "verify" / "hand_grades.csv"
    out.parent.mkdir(exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nYou agreed with the code on {agree}/{n}. Saved to {out.relative_to(ROOT)}")


if __name__ == "__main__":
    {"papers": check_papers, "grade": check_grades}[sys.argv[1]]()
