from pathlib import Path
import pandas as pd
import ast
import random
import csv
from typing import List, Tuple

BASE_DIR = Path(__file__).resolve().parent.parent
TARGETS_PATH = BASE_DIR / "data" / "target_snippets.csv"
SNIPPETS_DIR = BASE_DIR / "data" / "snippets"  # NOW after BASE_DIR
BUGGED_DIR = BASE_DIR / "data" / "bugged"
METADATA_PATH = BASE_DIR / "data" / "bug_metadata.csv"

MIN_LINES_FOR_BUG = 20  # don't inject into tiny snippets


def load_targets() -> pd.DataFrame:
    return pd.read_csv(TARGETS_PATH)


def get_bug_position_buckets(total_tokens: int) -> List[Tuple[str, int, int]]:
    """Return early/mid/late token ranges."""
    early_end = int(0.2 * total_tokens)
    mid_start, mid_end = int(0.4 * total_tokens), int(0.6 * total_tokens)
    late_start = int(0.8 * total_tokens)
    
    return [
        ("early", 0, early_end),
        ("mid", mid_start, mid_end),
        ("late", late_start, total_tokens),
    ]


def inject_off_by_one(tree: ast.AST, lines: list[str]) -> Tuple[bool, str, str]:
    """Find a for-loop range() and make it off-by-one."""
    # Placeholder: find range() in for-loop and adjust end
    # Return: (success, original_code, bugged_code)
    return False, "", ""


def inject_wrong_comparison(tree: ast.AST, lines: list[str]) -> Tuple[bool, str, str]:
    """Swap <= < or == !=."""
    # Placeholder
    return False, "", ""


BUG_TEMPLATES = [
    inject_off_by_one,
    inject_wrong_comparison,
    # Add more later
]


def inject_bug_into_snippet(snippet_path: Path, target_id: str) -> dict:
    """Inject one bug into snippet, return metadata."""
    text = snippet_path.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()
    
    if len(lines) < MIN_LINES_FOR_BUG:
        return None
    
    tree = ast.parse(text)
    
    # Try each bug template until one succeeds
    for bug_fn in random.sample(BUG_TEMPLATES, len(BUG_TEMPLATES)):
        result = bug_fn(tree, lines)
        if result[0]:  # success
            success, original, bugged = result
            break
    else:
        return None  # no applicable bugs
    
    # Save bugged version
    bugged_id = f"{target_id}_bug"
    bugged_path = BUGGED_DIR / f"{bugged_id}.py"
    BUGGED_DIR.mkdir(parents=True, exist_ok=True)
    bugged_path.write_text("\n".join(lines), encoding="utf-8")  

    return {
        "target_id": target_id,
        "bugged_id": bugged_id,
        "bug_type": bug_fn.__name__,
        "original_segment": original,
        "bugged_segment": bugged,
        "line_count": len(lines),
    }


if __name__ == "__main__":
    targets = load_targets()
    BUGGED_DIR.mkdir(parents=True, exist_ok=True)
    METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    with METADATA_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["target_id", "bugged_id", "bug_type", "original_segment", "bugged_segment", "line_count"])
        writer.writeheader()
        
        injected = 0
        for idx, row in targets.iterrows():
            snippet_path = SNIPPETS_DIR / row["file_name"]
            metadata = inject_bug_into_snippet(snippet_path, row["snippet_id"])
            if metadata:
                writer.writerow(metadata)
                injected += 1
        
        print(f"Injected {injected} bugs. Metadata saved to {METADATA_PATH}")
