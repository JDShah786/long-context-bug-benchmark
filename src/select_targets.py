import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CATALOG_PATH = BASE_DIR / "data" / "snippets_catalog.csv"
TARGET_PATH = BASE_DIR / "data" / "target_snippets.csv"

MIN_TOKENS = 3000  # "long context" threshold
TARGET_COUNT = 500

if __name__ == "__main__":
    df = pd.read_csv(CATALOG_PATH)

    # Filter long snippets
    long_snippets = df[df.token_count >= MIN_TOKENS]
    print(f"Snippets >= {MIN_TOKENS} tokens: {len(long_snippets)}")

    # Random sample 500 (or all if fewer)
    targets = long_snippets.sample(min(TARGET_COUNT, len(long_snippets)), random_state=42)
    targets.to_csv(TARGET_PATH, index=False)
    print(f"Selected {len(targets)} target snippets to", TARGET_PATH)
    print("Sample sizes:", targets.token_count.describe())
