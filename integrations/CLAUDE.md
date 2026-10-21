# CLAUDE.md — ctxray Context & Blast-Radius Workflow

This repository uses **ctxray** for AST skeletonization, PageRank dependency mapping, and blast-radius analysis. Follow these rules to keep context usage low and avoid breaking downstream dependents.

## 1. Quick Commands (CLI & MCP)

If the `ctxray` MCP server is configured (`python ctxray.py mcp`), prefer its tools directly:
- `ctxray_repo_map`: PageRank-ranked repository overview fitted to a token budget.
- `ctxray_skeletonize`: Strip function bodies while preserving signatures, types, and docstrings (~70–85% token reduction).
- `ctxray_blast_radius`: Compute direct/transitive reverse dependencies and risk score for any file.

Equivalent CLI commands:
```bash
# Ranked architectural overview within a 2,500-token budget
python ctxray.py map . --budget 2500 --query "auth middleware"

# Top central files by dependency PageRank & token cost
python ctxray.py rank . --top 15

# Reverse dependency & risk X-Ray before editing a module
python ctxray.py blast src/core/engine.py --depth 3

# Signature-only AST skeleton of a large file
python ctxray.py skel src/core/engine.py
```

## 2. Operating Rules for Claude Code

1. **Map First, Read Second**: Start unfamiliar tasks with `ctxray_repo_map` (or `python ctxray.py map .`) instead of reading dozens of files into context.
2. **Skeletonize Large Files**: For modules >200 LOC, inspect their interface via `ctxray_skeletonize` first, then read targeted line ranges for edits.
3. **Mandatory Blast-Radius Check**: Before changing public signatures, data models, or shared utilities, run `ctxray_blast_radius` on the target file and verify every impacted caller and test suite.
4. **Stay Under Context Budgets**: Keep initial discovery under 3,000 tokens using `--budget` so working memory remains clean for multi-step implementation and verification.
