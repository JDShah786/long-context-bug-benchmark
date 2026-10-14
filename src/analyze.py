"""Turn saved answers into scores, confidence ranges and the middle-vs-ends test."""
import math
from collections import defaultdict

Z95 = 1.959964  # 95% two-sided


def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float]:
    """95% Wilson interval for k successes out of n. Stays sensible at 0/n and n/n, unlike +/- 2 SE."""
    if n == 0:
        raise ValueError("no trials")
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, center - margin), min(1.0, center + margin)


def mcnemar(b: int, c: int) -> float:
    """Exact two-sided McNemar test: if position didn't matter, each disagreement is a coin flip."""
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def cell_rates(results: list[dict]) -> list[dict]:
    cells = defaultdict(list)
    for r in results:
        cells[(r["size"], r["depth"])].append(r)
    out = []
    for (size, depth), rows in cells.items():
        n, found, fixed = len(rows), sum(r["found"] for r in rows), sum(r["fixed"] for r in rows)
        found_lo, found_hi = wilson(found, n)
        fixed_lo, fixed_hi = wilson(fixed, n)
        out.append({"size": size, "depth": depth, "n": n, "found": found, "fixed": fixed,
                    "found_lo": found_lo, "found_hi": found_hi, "fixed_lo": fixed_lo, "fixed_hi": fixed_hi})
    return out


def paired_test(results: list[dict], end: float, middle: float = 0.5, size=None, measure: str = "found") -> dict:
    """Same needle, same size: middle vs one end. Only the pairs that disagree carry information."""
    by_key = {(r["needle_id"], r["size"], r["depth"]): r[measure] for r in results
              if size is None or r["size"] == size}
    middle_only = end_only = pairs = 0
    for (needle, sz, depth), mid in by_key.items():
        if depth != middle or (needle, sz, end) not in by_key:
            continue
        other = by_key[(needle, sz, end)]
        pairs += 1
        middle_only += mid and not other
        end_only += other and not mid
    return {"pairs": pairs, "middle_only": middle_only, "end_only": end_only, "p": mcnemar(middle_only, end_only)}


# ---------- chart ----------

SIZE_COLORS = {4000: "#2a78d6", 16000: "#eb6834", 32000: "#1baf7a"}  # validated categorical slots 1-3
INK, INK_2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"


def series(results: list[dict]) -> dict:
    """{size: [(depth, rate, lo, hi), ...]} in depth order, for found. 'alone' rows are left out."""
    lines = defaultdict(list)
    for c in sorted(cell_rates([r for r in results if r["size"] != "alone"]), key=lambda c: c["depth"]):
        lines[c["size"]].append((c["depth"], c["found"] / c["n"], c["found_lo"], c["found_hi"]))
    return dict(lines)


def baseline(alone: list[dict]) -> tuple[float, float, float]:
    k, n = sum(r["found"] for r in alone), len(alone)
    return (k / n, *wilson(k, n))


def matching_alone(results: list[dict], alone: list[dict]) -> list[dict]:
    """The baseline must cover the same bugs as the results it's compared with."""
    needles = {r["needle_id"] for r in results}
    return [a for a in alone if a["needle_id"] in needles]


def plot_models(models: dict, out_path) -> None:
    """One panel per model: % found vs bug position, a line per size, dashed line = function alone."""
    import matplotlib
    matplotlib.use("Agg")  # draw to a file, no window
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, len(models), figsize=(4.2 * len(models), 3.6), sharey=True, squeeze=False)
    fig.patch.set_facecolor(SURFACE)
    for ax, (name, (results, alone)) in zip(axes[0], models.items()):
        ax.set_facecolor(SURFACE)
        for i, (size, points) in enumerate(sorted(series(results).items())):
            dodge = (i - 1) * 0.015  # nudge sideways so whiskers at the same x don't hide each other
            xs = [d + dodge for d, *_ in points]
            ys = [100 * r for _, r, _, _ in points]
            err = [[100 * (r - lo) for _, r, lo, _ in points], [100 * (hi - r) for _, r, _, hi in points]]
            ax.errorbar(xs, ys, yerr=err, color=SIZE_COLORS.get(size, INK_2), lw=2, marker="o", ms=7,
                        elinewidth=1, capsize=0, label=f"{size // 1000}k tokens",
                        markeredgecolor=SURFACE, markeredgewidth=1.5)
        alone = matching_alone(results, alone or [])
        if alone:
            rate, _, _ = baseline(alone)
            ax.axhline(100 * rate, color=INK_2, lw=1.2, ls=(0, (4, 3)))
            x = 0.3 if rate >= 0.12 else 0.7  # a clear gap between whiskers; near zero, keep off the 10% points
            ax.text(x, 100 * rate + 2, f"same bugs alone: {100 * rate:.0f}%", color=INK_2, fontsize=8, ha="center")
        ax.set_title(name, color=INK, fontsize=10, loc="left")
        ax.set_xticks([0.1, 0.5, 0.9], ["10%", "50%", "90%"])
        ax.set_xlim(0, 1)
        ax.set_xlabel("Bug position in the context", color=INK_2, fontsize=9)
        ax.set_ylim(-3, 103)
        ax.grid(axis="y", color=GRID, lw=0.8)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(GRID)
        ax.tick_params(colors=INK_2, labelsize=8)
    axes[0][0].set_ylabel("Bugs found (%)", color=INK_2, fontsize=9)
    from matplotlib.lines import Line2D
    handles = [Line2D([], [], color=c, lw=2, marker="o", ms=6, markeredgecolor=SURFACE, label=f"{s // 1000}k tokens")
               for s, c in SIZE_COLORS.items()]
    if any(alone for _, alone in models.values()):
        handles.append(Line2D([], [], color=INK_2, lw=1.2, ls=(0, (4, 3)), label="same bugs, no padding"))
    fig.legend(handles=handles, loc="upper right", ncols=len(handles), frameon=False, fontsize=8, labelcolor=INK_2)
    fig.text(0.01, 0.01, "Whiskers: 95% Wilson intervals.", color=INK_2, fontsize=7)
    fig.tight_layout(rect=(0, 0.03, 1, 0.93))
    fig.savefig(out_path, dpi=200, facecolor=SURFACE)
    plt.close(fig)


if __name__ == "__main__":
    import json
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent
    load = lambda p: [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line]
    names = {"qwen": "Qwen2.5-Coder 7B", "deepseek": "DeepSeek-Coder-V2-Lite", "gemini": "Gemini 3.8 Flash",
             "gemini35": "Gemini 3.5 Flash"}
    models = {}
    for key, label in names.items():
        main = root / "results" / f"{key}.jsonl"
        main = main if main.exists() else root / "results" / f"{key}_pilot.jsonl"
        alone = root / "results" / f"{key}_alone.jsonl"
        if not main.exists() or len(load(main)) < 90:
            continue  # skip models with no complete pilot yet
        results, alone_rows = load(main), (load(alone) if alone.exists() else None)
        models[f"{label} ({main.stem.split('_')[-1] if '_' in main.stem else 'full'})"] = (results, alone_rows)

        print(f"\n{label}: {main.name}, {len(results)} answers")
        if alone_rows:
            for label_, rows_ in (("all bugs alone", alone_rows), ("same bugs alone", matching_alone(results, alone_rows))):
                rate, lo, hi = baseline(rows_)
                print(f"  {label_}: {sum(r['found'] for r in rows_)}/{len(rows_)} found "
                      f"({100 * rate:.0f}%, 95% CI {100 * lo:.0f}-{100 * hi:.0f}%)")
        for c in sorted(cell_rates(results), key=lambda c: (c["size"], c["depth"])):
            print(f"  {c['size']:>6} @ {int(100 * c['depth']):>2}%: found {c['found']}/{c['n']} "
                  f"(CI {100 * c['found_lo']:.0f}-{100 * c['found_hi']:.0f}%), fixed {c['fixed']}/{c['n']}")
        for end in (0.1, 0.9):
            t = paired_test(results, end=end)
            print(f"  middle vs {int(100 * end)}%: {t['pairs']} pairs, middle-only {t['middle_only']}, "
                  f"end-only {t['end_only']}, p = {t['p']:.3f}")

    out = root / "figures" / "position.png"
    out.parent.mkdir(exist_ok=True)
    plot_models(models, out)
    print(f"\nChart: {out}")
