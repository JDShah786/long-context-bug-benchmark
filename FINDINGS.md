# Findings log

A running record of what each run showed. Newest entries go at the bottom. Numbers only come from files in `results/` or from checks described here.

---

## 2026-10-12 — Smoke test (1 paper per model)

- **Paper:** `n06_32000_0.5` from the *old* dataset (later rebuilt). One paper only, so treat this as "does it run", not a result.
- **Time per 32k paper:**
  - Qwen2.5-Coder 7B: 56 s
  - DeepSeek-Coder-V2-Lite 16B: 133 s. It uses ~10.5 GB of the 12 GB VRAM; the rest runs on the CPU.
  - Gemini 3.8 Flash: 267 s, mostly waiting out "server busy" (HTTP 503) errors.
- **Token counts differ by model** for the same ~31.5k-token paper (cl100k): Qwen 31,926; Gemini 37,942; DeepSeek 39,307.
  - DeepSeek came within ~1.6k of the 40,960 context limit.
  - So `run.py` now flags any answer whose prompt was within 1,024 tokens of the limit (`near_limit`).
- All 3 models missed the bug on that one paper.

## 2026-10-12/13 — Dataset problems found and fixed

1. **Third-party code in the "stdlib" dataset.**
   - The loader searched all of `Lib/`, including `Lib/site-packages/`. Of 3,372 files there, 1,524 (45%) were `pip` and `yt_dlp`.
   - This made the dataset depend on what was installed on the machine.
   - Found because Gemini flagged `if callable(to_screen) is not None:`. That's a real bug in yt_dlp (`callable()` never returns `None`), sitting in the padding.
   - **Fix:** skip `site-packages`, and only check folder names *inside* `Lib/`.
2. **Too few off-by-one candidates after the fix.**
   - Pure stdlib top-level functions of 80–300 tokens gave only 8 off-by-one candidates. The plan needed 15.
   - **Decision:** also use methods of top-level classes, un-indented. That gives 27 candidates, so the planned 30/15/5 mix is kept.
3. **Duplicate padding.**
   - `encodings/` has ~100 near-identical `getregentry()` functions, so a paper could repeat the same block many times.
   - **Fix:** each function appears at most once in the pool.

**Rebuilt dataset (seed 42, Python 3.14.5):** 450 papers from 50 needles (30 comparison flip / 15 off-by-one / 5 eq flip).
- Sizes: 3,916–3,940 / 15,690–15,744 / 31,401–31,465 tokens.
- Every bug is within 0.035 of its target depth.
- The bugged line is unique in every paper, and no paper has a duplicate function.

**Run note:** a first Qwen pilot accidentally ran on the old dataset while the rebuild was in progress. Those 13 answers were discarded.

## 2026-10-13 — Qwen2.5-Coder 7B pilot (`results/qwen_pilot.jsonl`)

- 10 needles (6 / 3 / 1 by kind) × 3 sizes × 3 depths = **90 papers**. Run time was 17 min (avg 4.5 s at 4k, 9.6 s at 16k, 19.9 s at 32k).
- **Answered 90/90, found 0/90, fixed 0/90.** No errors, no `near_limit` flags.

| Size | 10% | 50% | 90% |
|---|---|---|---|
| 4k | 0/10 | 0/10 | 0/10 |
| 16k | 0/10 | 0/10 | 0/10 |
| 32k | 0/10 | 0/10 | 0/10 |

- Wrong answers were not near-misses: 0/90 pointed within 15 lines of the bug.
- 38/90 gave a "fix" identical to the line they quoted.
- **Diagnostic** (ad hoc, n = 10: the 10 pilot needles' bugged functions shown *alone*, ~200 tokens, same prompt, temperature 0):
  - Found 3/10, fixed 2/10.
  - The result was the same with and without Ollama's JSON mode, so JSON mode is not the cause.
- **Reading:** Qwen 7B can sometimes find these bugs in isolation (3/10), but drops to 0 once surrounded by ~4k tokens of other real code. That's a **floor effect**: with 0% at every position, this pilot cannot show a position effect for this model. The drop from "alone" to 4k is itself worth reporting, but n = 10 for the "alone" condition is very small.
- **Next:** run the Gemini and DeepSeek pilots before changing the design. A possible change is adding a shorter size (1k–2k) so weaker models aren't at the floor.

## 2026-10-13 — DeepSeek-Coder-V2-Lite 16B pilot (`results/deepseek_pilot.jsonl`)

- Same 90 papers as the Qwen pilot. Total answer time was 106 min (avg 14 s at 4k, 75 s at 16k, 123 s at 32k).
  - The model doesn't fit fully in 12 GB of VRAM: 19 layers on the GPU, the rest on the CPU.
- The run was interrupted once after 9 papers, when the Ollama app was closed. It resumed from paper 10 with no duplicates.
- **Answered 90/90, found 1/90, fixed 0/90.** No errors, no `near_limit` flags.

| Size | 10% | 50% | 90% |
|---|---|---|---|
| 4k | 1/10 | 0/10 | 0/10 |
| 16k | 0/10 | 0/10 | 0/10 |
| 32k | 0/10 | 0/10 | 0/10 |

- The one hit (`n16_4000_0.1`) found `if ord(c) <= 128:` but the fix was wrong (`... or unicodedata.combining(c)`).
- Wrong answers were not near-misses: 0/89 within 15 lines of the bug. 26/90 gave a "fix" identical to the line they quoted.
- **Reading:** another **floor effect**. Like Qwen 7B, this model can't find these bugs once they're surrounded by 4k+ tokens of other code, so this pilot can't show a position effect for it either.
- **Both local models are at the floor.** The position question depends on Gemini, the only model so far with room to drop (1/1 found and fixed on its first paper; not yet meaningful).

## 2026-10-13 — Gemini pilot attempts (blocked by Google load)

- **gemini-3.8-flash:** 1/90 papers answered (`n47_32000_0.5`, found and fixed) at 14:46. After that, every attempt hit "high demand" (HTTP 503) through all 5 retries (~7.5 min), and one attempt stopped with a "per day" quota error after very few calls.
  - Which quota it was isn't known: the script didn't print it yet. It now does.
  - Tiny test calls to 3.8 sometimes succeed in ~2 s. Long (32k) prompts have mostly failed today.
- **gemini-3.6-flash:** also 503 most of the afternoon.
- **gemini-2.5-flash:** 404, "no longer available to new users".
- **gemini-3.5-flash:** a tiny call worked at ~16:20, but the pilot (16:24–16:32) got 503 on all 5 retries, so 0/90.
- **Setup:** `run.py` now has `gemini35` (3.5 Flash) as a separate model entry with its own results file. 3.8 stays as `gemini`, so the two models' answers never mix.
- Partial results (`results/gemini_pilot.jsonl`, 1 answer) are kept locally, not committed, until a pilot is complete.

## 2026-10-14 — Gemini still blocked

- A tiny "hi" call returned **HTTP 503 (UNAVAILABLE)** on both `gemini-3.8-flash` and `gemini-3.5-flash`. This is no longer only long prompts: the free tier was overloaded even for 2-token requests.
- Gemini pilot progress is unchanged: 3.8 has 1/90 (local only), 3.5 has 0/90.
- Over two days, Google free-tier load is now the main risk to finishing the study.
- **Options noted:**
  - **A:** a "patient" runner that waits ~15 min between busy periods and keeps going for hours (e.g. overnight).
  - **B:** a backup free provider with a strong model. Its current free limits, especially the max prompt size (needs ≥ 32k), must be checked first; Groq's free tier was already ruled out (8k tokens/min).

---

## Next steps / open decisions (as of 2026-10-14)

1. **Get Gemini answers:** choose option A (patient runner), B (backup provider), or both. Until then, retry at quiet times (night or early morning). Try 3.8 first (the stronger model); if still blocked, use 3.5:
   - `.venv\Scripts\python src/run.py gemini --pilot`
   - `.venv\Scripts\python src/run.py gemini35 --pilot`
   - If a daily-limit stop happens, the message now names the quota. Record it here.
2. **Decide:** add a **"function alone" baseline** (the 50 bugged functions with no padding) for every model? It's cheap (minutes locally, 50 Gemini calls), and it turns the local models' floor into a measured drop ("found X% alone → 0% with 4k padding").
3. **Decide:** skip the full 450-paper runs for Qwen and DeepSeek, since their pilots are already at the floor (0/90 and 1/90)? That saves ~1.5 h and ~6 h of laptop time for no new information. The skip would be stated in the writeup.
4. After the Gemini pilot: check for ceiling/floor. If Gemini has room to move, run its full 450 papers (several days on the free tier), then do charts + stats (step 8) and the writeup (step 9).
