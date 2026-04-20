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


def inject_off_by_one(tree: ast.AST, lines: list[str]) -> Tuple[bool, str, str, int]:
    """Find a for-loop range() and make it off-by-one."""
    for node in ast.walk(tree):
        if isinstance(node, ast.For):
            # Check if iter is a Call to range()
            if isinstance(node.iter, ast.Call):
                func = node.iter.func
                if isinstance(func, ast.Name) and func.id == "range":
                    # Found a for loop with range()
                    if not node.iter.args:
                        continue  # range() with no args, skip
                    
                    # Get the line range of this for statement
                    start_line = node.lineno - 1
                    end_line = getattr(node, 'end_lineno', start_line + 1) - 1
                    
                    # Original code
                    original = "\n".join(lines[start_line:end_line + 1])
                    
                    # Modify: subtract 1 from the first range argument
                    first_arg = node.iter.args[0]
                    if isinstance(first_arg, ast.Constant):
                        # Simple constant like range(10)
                        old_val = first_arg.value
                        if isinstance(old_val, int) and old_val > 1:
                            new_val = old_val - 1
                            # Replace in source
                            line = lines[start_line]
                            lines[start_line] = line.replace(f"range({old_val}", f"range({new_val}", 1)
                            bugged = "\n".join(lines[start_line:end_line + 1])
                            return True, original, bugged, start_line + 1
                    elif isinstance(first_arg, ast.Call):
                        # range(len(x)) pattern
                        if isinstance(first_arg.func, ast.Name) and first_arg.func.id == "len":
                            line = lines[start_line]
                            # Add -1 to len call
                            if "range(len(" in line:
                                lines[start_line] = line.replace("range(len(", "range(len(", 1).replace("))", ") - 1)", 1)
                                bugged = "\n".join(lines[start_line:end_line + 1])
                                return True, original, bugged, start_line + 1
    
    return False, "", "", 0


def inject_wrong_comparison(tree: ast.AST, lines: list[str]) -> Tuple[bool, str, str, int]:
    """Swap <= < or == != or >= >."""
    # Map of comparison swaps
    swaps = {
        "<=": "<",
        "<": "<=",
        ">=": ">",
        ">": ">=",
        "==": "!=",
        "!=": "==",
    }
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            # Get the line of this comparison
            start_line = node.lineno - 1
            end_line = getattr(node, 'end_lineno', start_line + 1) - 1
            
            # Original code
            original = "\n".join(lines[start_line:end_line + 1])
            
            # Check operator types
            for op in node.ops:
                op_type = type(op).__name__
                # Map AST node types to string operators
                op_map = {
                    "LtE": "<=",
                    "Lt": "<",
                    "GtE": ">=",
                    "Gt": ">",
                    "Eq": "==",
                    "NotEq": "!=",
                }
                
                if op_type in op_map:
                    old_op = op_map[op_type]
                    new_op = swaps.get(old_op)
                    if new_op:
                        # Try to replace in source (first occurrence on this line)
                        line = lines[start_line]
                        if old_op in line:
                            # Only replace first occurrence to be safe
                            lines[start_line] = line.replace(old_op, new_op, 1)
                            bugged = "\n".join(lines[start_line:end_line + 1])
                            return True, original, bugged, start_line + 1
    
    return False, "", "", 0


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
    
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return None  # skip unparseable files
    
    # Try each bug template until one succeeds
    for bug_fn in random.sample(BUG_TEMPLATES, len(BUG_TEMPLATES)):
        success, original, bugged, bug_line = bug_fn(tree, lines)
        if success:
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
        "bug_line": bug_line,
        "original_segment": original,
        "bugged_segment": bugged,
        "line_count": len(lines),
    }


if __name__ == "__main__":
    targets = load_targets()
    BUGGED_DIR.mkdir(parents=True, exist_ok=True)
    METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    with METADATA_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["target_id", "bugged_id", "bug_type", "bug_line", "original_segment", "bugged_segment", "line_count"])
        writer.writeheader()
        
        injected = 0
        for idx, row in targets.iterrows():
            snippet_path = SNIPPETS_DIR / row["file_name"]
            metadata = inject_bug_into_snippet(snippet_path, row["snippet_id"])
            if metadata:
                writer.writerow(metadata)
                injected += 1
    
    print(f"Injected {injected} bugs. Metadata saved to {METADATA_PATH}")