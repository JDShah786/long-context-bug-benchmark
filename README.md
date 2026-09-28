# Long-Context Bug Benchmark

Does a bug's position in a long Python context change how often an LLM finds and fixes it?

This is a controlled test of the "Lost in the Middle" effect ([Liu et al., 2023](https://arxiv.org/abs/2307.03172)) on debugging.

## Design

- **Needle:** a short real function with one injected single-line bug.
- **Haystack:** unrelated real functions around it.
- The same bug is placed at ~10%, ~50% and ~90% depth (by tokens), in contexts of 4k, 16k and 32k tokens. Position and length are the only things that change.
- **Bug kinds:** comparison flips (`<`↔`<=`, `>`↔`>=`), off-by-one in `for ... in range(x)`, and a few `==`↔`!=`.
- **Models (free only):** Gemini Flash (API), Qwen2.5-Coder-7B (local, Ollama), DeepSeek-Coder-V2-Lite (local, stretch goal).
- **Prompt:** "This code contains exactly one bug." The model returns the buggy line and a fixed line.
- **Scoring:**
  - *Found* = the quoted line matches the bugged line.
  - *Fixed* = the fix matches the original line (strict; whitespace ignored).
- **Analysis:** accuracy per cell with 95% CIs, and a paired McNemar test (mid vs. ends).

## Status

| Step | State |
|---|---|
| 1. Bug injector (`src/bugs.py`) | Done, 28 tests |
| 2. Needle + haystack builder (`src/haystack.py`) | Builder done, 24 tests; dataset script next |
| 3. Prompt + response parser | Not started |
| 4. Scorer | Not started |
| 5. Model clients | Not started |
| 6. Pilot (10 bugs) | Not started |
| 7. Full run (50 bugs × 9 cells × each model) | Not started |
| 8. Charts + stats | Not started |
| 9. Writeup | Not started |

No results yet.

## Run the tests

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pytest tests -q
```
