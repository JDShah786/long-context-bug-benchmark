# Long-Context Bug Benchmark - Project Summary

**Author:** Hamid Shah  
**Start Date:** February 23, 2026  
**Last Updated:** June 3, 2026

## Project Overview

### Research Question
How does the position of a bug within large code contexts affect an LLM's ability to identify and fix it? Does the "Lost in the Middle" phenomenon observed in text retrieval tasks also apply to code debugging?

**Hypothesis:** LLMs will perform worse at detecting and fixing bugs located in the middle (40-60% token position) of long code files compared to bugs at the beginning or end.

### Models to Test
1. **GPT-5.1-Codex-Max** (OpenAI) - frontier proprietary coding model
2. **DeepSeek-Coder** - open-source repository-level code model (up to 128K context)
3. **StarCoder2-15B** - open-source code model (16K context window)

---

## Project Structure

```
long-context-bug-benchmark/
├── src/
│   ├── harvest_repos.py           # Clone source repositories
│   ├── extract_snippets.py        # Extract long functions/classes
│   ├── catalog_snippets.py        # Create metadata catalog with token counts
│   ├── select_targets.py          # Select ~500 long-context targets
│   ├── inject_bugs.py             # Inject synthetic bugs at early/mid/late positions
│   ├── sample_for_tests.py        # Sample bugs for validation
│   └── validate_bugs.py           # Validate bug quality
├── data/
│   ├── raw_repos/                 # Cloned Python repositories (gitignored)
│   ├── snippets/                  # Extracted long code snippets (gitignored)
│   ├── bugged/                    # Bug-injected versions (gitignored)
│   ├── snippets_catalog.csv       # Metadata: line counts, token counts
│   ├── target_snippets.csv        # Selected targets (347 snippets ≥3k tokens)
│   ├── bug_metadata.csv           # Bug injection metadata
│   ├── test_sample.csv            # Sample for validation
│   └── validation_report.txt      # Bug validation results
├── tests/                         # (Future: test harnesses)
├── .gitignore
└── README.md
```

---

## Completed Phases

### ✅ Phase 0: Repository Setup and Harvesting
**Completed:** February 23, 2026

**What was done:**
- Created project structure with git initialization
- Wrote `harvest_repos.py` to clone 6 large Python repositories:
  - **pandas** (pandas-dev/pandas)
  - **Django** (django/django)
  - **scikit-learn** (scikit-learn/scikit-learn)
  - **Scrapy** (scrapy/scrapy)
  - **Matplotlib** (matplotlib/matplotlib)
  - **Requests** (psf/requests)

**Results:**
- 6 repositories cloned into `data/raw_repos/`
- Combined codebase: ~1.3 million lines of production Python code

**Key commits:**
- Initial project structure
- Working cloning script

---

### ✅ Phase 1: Snippet Extraction
**Completed:** March 2, 2026

**What was done:**
- Implemented `extract_snippets.py` using Python AST parsing
- Scanned all `.py` files in harvested repos
- Filtered out test files, docs, examples, migrations
- Extracted functions and classes ≥80 lines
- Saved each as standalone snippet with descriptive ID

**Results:**
- **2,588 long code snippets** extracted
- Average: 248 lines per snippet
- Range: 80 to 18,417 lines
- Median: 138 lines

**Technical approach:**
- Used Python `ast` module for parsing
- Applied `ast.walk()` to find `FunctionDef`, `AsyncFunctionDef`, `ClassDef` nodes
- Extracted source text using line numbers
- Generated unique IDs: `{repo}__{module}__{symbol}__{start}_{end}_{idx}.py`

**Key commits:**
- Add long snippet extraction script and ignore generated data

---

### ✅ Phase 1.5: Catalog and Target Selection
**Completed:** March 23, 2026

**What was done:**

**1. Catalog Creation (`catalog_snippets.py`):**
- Scanned all 2,588 extracted snippets
- Counted lines per snippet
- Added token counting using `tiktoken` (GPT-4 tokenizer: `cl100k_base`)
- Generated `snippets_catalog.csv` with metadata

**2. Target Selection (`select_targets.py`):**
- Filtered snippets with ≥3,000 tokens ("long context")
- Randomly sampled up to 500 targets (seed: 42)
- Generated `target_snippets.csv`

**Results:**
- Token statistics across all 2,588 snippets:
  - Mean: 2,065 tokens
  - Median: 1,167 tokens
  - Range: 478 to 150,756 tokens

- **347 target snippets** selected (≥3k tokens):
  - Mean: 7,373 tokens
  - Median: 4,257 tokens
  - 25th percentile: 3,518 tokens
  - 75th percentile: 6,353 tokens

**Key commits:**
- Add token counting to catalog and select 347 long-context targets

---

### ✅ Phase 2: Bug Injection
**Completed:** April 20, 2026

**What was done:**

**1. Bug Template Design:**
Implemented two synthetic bug types:

**a) Off-by-one errors (`inject_off_by_one`):**
- Target: `for` loops with `range()` calls
- Modifications:
  - `range(10)` → `range(9)`
  - `range(len(x))` → `range(len(x) - 1)`

**b) Wrong comparison operators (`inject_wrong_comparison`):**
- Target: comparison operators in conditionals
- Swaps:
  - `<=` ↔ `<`
  - `>=` ↔ `>`
  - `==` ↔ `!=`

**2. Position-Aware Injection:**
For each target snippet, attempted bug injection at three positions:
- **Early:** 0-20% of lines
- **Mid:** 40-60% of lines
- **Late:** 80-100% of lines

**Implementation approach:**
- Used AST to locate candidate nodes (loops, comparisons)
- Filtered nodes by line position to match target bucket
- Applied text-based replacement to inject bug
- Preserved syntactic validity
- Generated unique bugged file IDs: `{snippet_id}_{position}_bug.py`

**Results:**
- **635 bugs injected** across 347 target snippets
- Position distribution:
  - Early: 131 bugs (21%)
  - Mid: 243 bugs (38%)
  - Late: 261 bugs (41%)
- Bug type distribution:
  - Wrong comparison: 312 bugs (49%)
  - Off-by-one: 11 bugs (2%)
  - (Note: lower off-by-one count due to fewer applicable sites)

**Metadata logged:**
- `target_id`: original snippet identifier
- `bugged_id`: bugged version identifier
- `position_bucket`: early/mid/late
- `bug_type`: template used
- `bug_line`: approximate line number of bug
- `original_segment`: code before injection
- `bugged_segment`: code after injection
- `line_count`: total lines in snippet

**Key commits:**
- Implement off-by-one bug template
- Add wrong_comparison template
- Add position-aware bug injection (early/mid/late)

---

### ✅ Phase 3: Validation
**Completed:** April 20, 2026

**What was done:**

**1. Stratified Sampling (`sample_for_tests.py`):**
- Sampled 20 bugs balanced across:
  - Position buckets (early/mid/late)
  - Bug types (off-by-one, wrong comparison)
- Saved to `test_sample.csv`

**2. Automated Validation (`validate_bugs.py`):**
For each sampled bug:
- Verified original file exists and parses correctly
- Verified bugged file exists and parses correctly
- Confirmed original and bugged code differ
- Extracted and logged before/after segments
- Generated `validation_report.txt`

**Results:**
- All 20 sampled bugs passed validation:
  - ✓ Syntactically valid Python
  - ✓ Differ from originals
  - ✓ Bugs injected at correct positions
- No syntax errors or failed injections detected

**Key commits:**
- Add test validation framework - Phase 3 complete

---

## Current Status

### Dataset Summary
- **Source repositories:** 6 major Python projects
- **Total snippets extracted:** 2,588
- **Long-context targets selected:** 347 (≥3k tokens)
- **Bugs injected:** 635
  - Early position: 131
  - Mid position: 243
  - Late position: 261
- **Validation:** 20/20 sample bugs passed quality checks

### Progress: ~45% Complete

**Completed:**
- ✅ Phase 0: Repository harvesting
- ✅ Phase 1: Snippet extraction
- ✅ Phase 1.5: Cataloging and target selection
- ✅ Phase 2: Position-aware bug injection
- ✅ Phase 3: Validation

**Remaining:**
- ⏳ Phase 4: Model evaluation (run GPT-5.1-Codex-Max, DeepSeek-Coder, StarCoder2)
- ⏳ Phase 5: Analysis and results
- ⏳ Phase 6: Paper write-up

---

## Next Steps (Phase 4: Model Evaluation)

### Tasks
1. **Obtain API access:**
   - GPT-5.1-Codex-Max (OpenAI)
   - DeepSeek-Coder API
   - StarCoder2 (HuggingFace or local inference)

2. **Design prompts:**
   - Standardized debugging prompt template
   - JSON-structured output format
   - Temperature and max_tokens settings

3. **Build evaluation pipeline (`src/run_models.py`):**
   - Load `bug_metadata.csv`
   - For each bugged snippet:
     - Construct prompt with bugged code
     - Query each model
     - Parse response (bug location + fix)
     - Log raw outputs
   - Save results to `model_outputs/`

4. **Implement grading (`src/evaluate_results.py`):**
   - **Detection metric:** Did model identify correct line ±5 lines?
   - **Fix metric:** Does suggested fix restore original behavior?
   - Aggregate by:
     - Model
     - Position bucket (early/mid/late)
     - Bug type

5. **Generate visualizations:**
   - Heatmaps: position × detection rate per model
   - Bar charts: fix success rate by position
   - Statistical significance tests (chi-square, ANOVA)

### Expected Outputs
- Detection rates by position and model
- Fix success rates by position and model
- Heat maps showing "Lost in the Middle" effect
- Quantitative evidence for position-dependent debugging performance

---

## Technical Details

### Bug Injection Algorithm

```python
def inject_bug_at_position(snippet, position_bucket):
    """
    1. Parse snippet with ast.parse()
    2. Get position line range (early/mid/late)
    3. Walk AST to find candidate nodes in range
    4. Try bug templates in random order:
       - inject_off_by_one(tree, lines, start, end)
       - inject_wrong_comparison(tree, lines, start, end)
    5. Apply first successful template
    6. Write bugged code to data/bugged/
    7. Log metadata to bug_metadata.csv
    """
```

### Tokenization
- Tokenizer: `tiktoken.get_encoding("cl100k_base")` (GPT-4/GPT-5 compatible)
- Used for:
  - Filtering targets (≥3k tokens)
  - Future: position buckets at token level (not yet implemented)

### Bug Templates

**Off-by-one:**
```python
# Before
for i in range(len(items)):
    process(items[i])

# After
for i in range(len(items) - 1):  # Bug: skips last item
    process(items[i])
```

**Wrong comparison:**
```python
# Before
if count <= threshold:
    accept()

# After
if count < threshold:  # Bug: off-by-one boundary error
    accept()
```

---

## Dependencies

```text
pandas
tiktoken
gitpython  # (optional, for automated cloning)
```

Install:
```bash
pip install pandas tiktoken
```

---

## Repository Setup

### Local
```bash
git init
git add .
git commit -m "Initial commit"
```

### GitHub (Private Repo)
```bash
# After creating private repo on GitHub:
git remote add origin https://github.com/<username>/long-context-bug-benchmark.git
git branch -M main
git push -u origin main
```

---

## Key Design Decisions

1. **Why these repos?**
   - Large, mature, diverse Python codebases
   - Real-world production code (not toy examples)
   - Well-structured with long, complex functions

2. **Why ≥3k tokens?**
   - "Long context" regime for most models
   - Large enough to exhibit "Lost in the Middle" effects
   - Small enough to fit in 16K context windows

3. **Why early/mid/late positions?**
   - Tests the core "Lost in the Middle" hypothesis
   - Prior work shows U-shaped performance (good at start/end, poor in middle)
   - Need position diversity to measure effect

4. **Why synthetic bugs?**
   - Controllable: know exact bug location and type
   - Repeatable: same bug can be placed at different positions
   - Gradeable: can verify fix correctness automatically
   - Scalable: generate hundreds of examples programmatically

5. **Why these bug types?**
   - Off-by-one and wrong comparisons are common real-world bugs
   - Easy to inject via AST manipulation
   - Subtle enough to require reasoning, not just syntax checking

---

## Timeline

- **Week 1-3 (Feb 23 - Mar 23):** Dataset generation (Phases 0-2)
- **Week 4 (Apr 20):** Bug injection and validation (Phase 3)
- **Week 5-6 (TBD):** Model evaluation (Phase 4)
- **Week 7-8 (TBD):** Analysis and visualization (Phase 5)
- **Week 9-10 (TBD):** Paper draft and revisions (Phase 6)

---

## References

- **Lost in the Middle:** Liu et al. (2023) - https://arxiv.org/abs/2307.03172
- **StarCoder2:** BigCode et al. (2024)
- **DeepSeek-Coder:** DeepSeek-AI (2024)
- **GPT-5.1-Codex-Max:** OpenAI (2025)

---

## Contact

**Student:** Hamid Shah  
**Project:** Evaluating Long-Context Recall and Debugging Performance in LLMs  
**Institution:** [Your University]  
**Date:** Spring 2026
