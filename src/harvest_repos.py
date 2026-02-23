REPOS = [
    "https://github.com/pandas-dev/pandas",
    "https://github.com/django/django",
    "https://github.com/scikit-learn/scikit-learn",
    "https://github.com/scrapy/scrapy",
    "https://github.com/matplotlib/matplotlib",
    "https://github.com/psf/requests",
]


if __name__ == "__main__":
    for url in REPOS:
        print("Will clone:", url)
