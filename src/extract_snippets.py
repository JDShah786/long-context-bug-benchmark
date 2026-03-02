from pathlib import Path
import ast
import textwrap

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "raw_repos"
SNIPPETS_DIR = BASE_DIR / "data" / "snippets"

MIN_FILE_LINES = 150      # threshold to even look inside a file
MIN_SNIPPET_LINES = 80    # threshold for a function/class to count as "long"


def iter_python_files():
    for path in RAW_DIR.rglob("*.py"):
        parts = {p.name for p in path.parents}
        if {"tests", "test", "docs", "examples", "migrations"} & parts:
            continue
        yield path


def get_long_files():
    for py_file in iter_python_files():
        try:
            lines = py_file.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception as e:
            print("Error reading", py_file, ":", e)
            continue

        if len(lines) >= MIN_FILE_LINES:
            yield py_file, lines


def extract_long_nodes(py_file: Path, lines: list[str]):
    """Yield (node, source_text) for long functions/classes in this file."""
    try:
        tree = ast.parse("\n".join(lines), filename=str(py_file))
    except SyntaxError as e:
        print("SyntaxError parsing", py_file, ":", e)
        return

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            # Python 3.8+ has end_lineno
            end_lineno = getattr(node, "end_lineno", None)
            if end_lineno is None:
                continue
            start = node.lineno - 1  # 0-based index
            end = end_lineno        # slice is exclusive

            span = end - start
            if span < MIN_SNIPPET_LINES:
                continue

            snippet_lines = lines[start:end]
            source = "\n".join(snippet_lines)
            yield node, source, start + 1, end  # return 1-based line numbers


def sanitize_name(name: str) -> str:
    return "".join(c if c.isalnum() or c in ("_",) else "_" for c in name)


if __name__ == "__main__":
    SNIPPETS_DIR.mkdir(parents=True, exist_ok=True)
    total_snippets = 0

    for py_file, lines in get_long_files():
        rel_path = py_file.relative_to(RAW_DIR)
        # e.g. django/django/contrib/admin/views/main.py -> django__django__contrib__admin__views__main
        base_id = sanitize_name(str(rel_path.with_suffix("")).replace("\\", "__").replace("/", "__"))

        for idx, (node, source, start_line, end_line) in enumerate(extract_long_nodes(py_file, lines), start=1):
            node_type = type(node).__name__.lower()  # functiondef, classdef, etc.
            name_part = sanitize_name(getattr(node, "name", node_type))
            snippet_id = f"{base_id}__{name_part}__{start_line}_{end_line}_{idx}"

            out_path = SNIPPETS_DIR / f"{snippet_id}.py"
            # Optional: de-indent to a reasonable level
            cleaned = textwrap.dedent(source).strip() + "\n"

            out_path.write_text(cleaned, encoding="utf-8")
            total_snippets += 1

            print(f"[SNIPPET] {snippet_id} ({end_line - start_line + 1} lines)")

    print("Total long snippets extracted:", total_snippets)
