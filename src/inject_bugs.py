from pathlib import Path
import pandas as pd
import ast
import random
import csv
import tiktoken
from typing import List, Tuple, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
TARGETS_PATH = BASE_DIR / "data" / "target_snippets.csv"
SNIPPETS_DIR = BASE_DIR / "data" / "snippets"
BUGGED_DIR = BASE_DIR / "data" / "bugged"
METADATA_PATH = BASE_DIR / "data" / "bug_metadata.csv"

MIN_LINES_FOR_BUG = 20
ENCODING = "cl100k_base"


def load_targets() -> pd.DataFrame:
    return pd.read_csv(TARGETS_PATH)


def get_position_buckets(total_lines: int) -> List[Tuple[str, int, int]]:
    """Return early/mid/late line ranges (approximate)."""
    early_end = int(0.2 * total_lines)
    mid_start, mid_end = int(0.4 * total_lines), int(0.6 * total_lines)
    late_start = int(0.8 * total_lines)
    
    return [
        ("early", 0, max(early_end, 1)),
        ("mid", mid_start, mid_end),
        ("late", late_start, total_lines),
    ]


def node_in_position(node: ast.AST, bucket_start: int, bucket_end: int) -> bool:
    """Check if AST node falls within line range."""
    node_line = node.lineno - 1  # 0-indexed
    return bucket_start <= node_line < bucket_end


def inject_off_by_one(tree: ast.AST, lines: list[str], bucket_start: int, bucket_end: int) -> Tuple[bool, str, str, int]:
    """Find a for-loop range() in position bucket and make it off-by-one."""
    for node in ast.walk(tree):
        if isinstance(node, ast.For):
            if not node_in_position(node, bucket_start, bucket_end):
                continue
                
            if isinstance(node.iter, ast.Call):
                func = node.iter.func
                if isinstance(func, ast.Name) and func.id == "range":
                    if not node.iter.args:
                        continue
                    
                    start_line = node.lineno - 1
                    end_line = getattr(node, 'end_lineno', start_line + 1) - 1
                    original = "\n".join(lines[start_line:end_line + 1])
                    
                    first_arg = node.iter.args[0]
                    if isinstance(first_arg, ast.Constant):
                        old_val = first_arg.value
                        if isinstance(old_val, int) and old_val > 1:
                            new_val = old_val - 1
                            line = lines[start_line]
                            lines[start_line] = line.replace(f"range({old_val}", f"range({new_val}", 1)
                            bugged = "\n".join(lines[start_line:end_line + 1])
                            return True, original, bugged, start_line + 1
                    elif isinstance(first_arg, ast.Call):
                        if isinstance(first_arg.func, ast.Name) and first_arg.func.id == "len":
                            line = lines[start_line]
                            if "range(len(" in line:
                                lines[start_line] = line.replace("))", ") - 1)", 1)
                                bugged = "\n".join(lines[start_line:end_line + 1])
                                return True, original, bugged, start_line + 1
    
    return False, "", "", 0


def inject_wrong_comparison(tree: ast.AST, lines: list[str], bucket_start: int, bucket_end: int) -> Tuple[bool, str, str, int]:
    """Swap comparison operators in position bucket."""
    swaps = {
        "<=": "<", "<": "<=",
        ">=": ">", ">": ">=",
        "==": "!=", "!=": "==",
    }
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            if not node_in_position(node, bucket_start, bucket_end):
                continue
                
            start_line = node.lineno - 1
            end_line = getattr(node, 'end_lineno', start_line + 1) - 1
            original = "\n".join(lines[start_line:end_line + 1])
            
            for op in node.ops:
                op_map = {
                    "LtE": "<=", "Lt": "<",
                    "GtE": ">=", "Gt": ">",
                    "Eq": "==", "NotEq": "!=",
                }
                
                op_type = type(op).__name__
                if op_type in op_map:
                    old_op = op_map[op_type]
                    new_op = swaps.get(old_op)
                    if new_op:
                        line = lines[start_line]
                        if old_op in line:
                            lines[start_line] = line.replace(old_op, new_op, 1)
                            bugged = "\n".join(lines[start_line:end_line + 1])
                            return True, original, bugged, start_line + 1
    
    return False, "", "", 0


BUG_TEMPLATES = [
    inject_off_by_one,
    inject_wrong_comparison,
]


def inject_bug_at_position(snippet_path: Path, target_id: str, position: str, bucket_start: int, bucket_end: int) -> Optional[dict]:
    """Try to inject one bug in the specified position bucket."""
    text = snippet_path.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()
    
    if len(lines) < MIN_LINES_FOR_BUG:
        return None
    
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return None
    
    # Try each template in random order
    for bug_fn in random.sample(BUG_TEMPLATES, len(BUG_TEMPLATES)):
        # Make a fresh copy of lines for each attempt
        lines_copy = lines.copy()
        success, original, bugged, bug_line = bug_fn(tree, lines_copy, bucket_start, bucket_end)
        if success:
            # Save bugged version
            bugged_id = f"{target_id}_{position}_bug"
            bugged_path = BUGGED_DIR / f"{bugged_id}.py"
            BUGGED_DIR.mkdir(parents=True, exist_ok=True)
            bugged_path.write_text("\n".join(lines_copy), encoding="utf-8")
            
            return {
                "target_id": target_id,
                "bugged_id": bugged_id,
                "position_bucket": position,
                "bug_type": bug_fn.__name__,
                "bug_line": bug_line,
                "original_segment": original,
                "bugged_segment": bugged,
                "line_count": len(lines),
            }
    
    return None


if __name__ == "__main__":
    targets = load_targets()
    BUGGED_DIR.mkdir(parents=True, exist_ok=True)
    METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    with METADATA_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "target_id", "bugged_id", "position_bucket", "bug_type", 
            "bug_line", "original_segment", "bugged_segment", "line_count"
        ])
        writer.writeheader()
        
        injected = 0
        for idx, row in targets.iterrows():
            snippet_path = SNIPPETS_DIR / row["file_name"]
            
            # Try to inject bugs at each position
            buckets = get_position_buckets(row["line_count"])
            for position, start, end in buckets:
                metadata = inject_bug_at_position(snippet_path, row["snippet_id"], position, start, end)
                if metadata:
                    writer.writerow(metadata)
                    injected += 1
            
            if (idx + 1) % 50 == 0:
                print(f"Processed {idx + 1}/{len(targets)} snippets...")
    
    print(f"\nInjected {injected} bugs across early/mid/late positions.")
    print(f"Metadata saved to {METADATA_PATH}")