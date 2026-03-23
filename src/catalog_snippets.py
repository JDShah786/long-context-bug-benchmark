from pathlib import Path
import csv

BASE_DIR = Path(__file__).resolve().parent.parent
SNIPPETS_DIR = BASE_DIR / "data" / "snippets"
CATALOG_PATH = BASE_DIR / "data" / "snippets_catalog.csv"


if __name__ == "__main__":
    SNIPPETS_DIR.mkdir(parents=True, exist_ok=True)
    CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    with CATALOG_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["snippet_id", "file_name", "line_count"])

        count = 0
        for path in SNIPPETS_DIR.glob("*.py"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            line_count = len(text.splitlines())
            snippet_id = path.stem
            writer.writerow([snippet_id, path.name, line_count])
            count += 1

    print("Wrote catalog for", count, "snippets to", CATALOG_PATH)
