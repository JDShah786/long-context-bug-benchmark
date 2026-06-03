# Long-Context Bug Benchmark

**Research Project:** Evaluating Long-Context Recall and Debugging Performance in Large Language Models

## Overview

This project investigates whether the "Lost in the Middle" phenomenon affects LLM debugging performance. We test whether bugs located in the middle of long code files are detected less often than bugs at the beginning or end.

### Models Under Test
- GPT-5.1-Codex-Max (OpenAI)
- DeepSeek-Coder
- StarCoder2-15B

## Quick Stats

- **635 bugs** injected across 347 long Python code snippets
- **3 position buckets:** Early (21%), Mid (38%), Late (41%)
- **Source:** 6 major Python projects (pandas, Django, scikit-learn, Scrapy, Matplotlib, Requests)
- **Average snippet size:** 7,373 tokens

## Project Structure

```
├── src/                    # Python scripts for pipeline
├── data/                   # Generated datasets and metadata
│   ├── snippets_catalog.csv
│   ├── target_snippets.csv
│   └── bug_metadata.csv
├── PROJECT_SUMMARY.md      # Detailed project documentation
└── README.md              # This file
```

## Setup

### Clone and Install Dependencies

```bash
git clone <your-repo-url>
cd long-context-bug-benchmark
pip install pandas tiktoken
```

### Regenerate Dataset (if needed)

```bash
# 1. Harvest repositories
python src/harvest_repos.py

# 2. Extract long snippets
python src/extract_snippets.py

# 3. Catalog with token counts
python src/catalog_snippets.py

# 4. Select targets
python src/select_targets.py

# 5. Inject bugs
python src/inject_bugs.py

# 6. Validate
python src/validate_bugs.py
```

## Current Status

**Completed:**
- ✅ Dataset generation (635 bugs with position diversity)
- ✅ Validation (20/20 sample bugs passed)

**Next:**
- ⏳ Model evaluation with GPT-5.1-Codex-Max, DeepSeek-Coder, StarCoder2
- ⏳ Analysis and visualization
- ⏳ Paper write-up

## Key Files

- `PROJECT_SUMMARY.md` - Complete project documentation
- `data/bug_metadata.csv` - Metadata for all 635 bugs
- `data/target_snippets.csv` - Info on 347 target snippets
- `src/inject_bugs.py` - Position-aware bug injection

## License

Research project - Academic use only

## Author

Hamid Shah - Spring 2026
