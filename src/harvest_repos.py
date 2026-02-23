import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "raw_repos"

REPOS = [
    "https://github.com/pandas-dev/pandas",
    "https://github.com/django/django",
    "https://github.com/scikit-learn/scikit-learn",
    "https://github.com/scrapy/scrapy",
    "https://github.com/matplotlib/matplotlib",
    "https://github.com/psf/requests",
]


if __name__ == "__main__":
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    for url in REPOS:
        name = url.rstrip("/").split("/")[-1]
        dest = RAW_DIR / name

        if dest.exists():
            print("Already cloned:", dest)
            continue

        print("Cloning", url, "into", dest)
        subprocess.run(["git", "clone", url, str(dest)], check=True)
