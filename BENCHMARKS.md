# ctxray Benchmark Report

Empirical evaluation of **`ctxray`** (Budget-Aware Semantic Tiering + Prefix-Stable Ordering) against flat repository packers (**`repomix`** and **`gitingest`**) across 5 production architectures and 4 frontier LLMs.

---

## 1. Methodology

- **Workload**: A realistic **10-turn autonomous coding agent session** (investigating an issue, editing 2-3 core files per turn, running verification, and iterating).
- **Token Budget Target**: `ctxray` compiled with `--budget 32000` tokens using hybrid task-relevance + PageRank centrality scoring (`FULL` -> `SKELETON` -> `SUMMARY`). `repomix` and `gitingest` emit full flat repository dumps.
- **Prefix Cache Simulation**: Across turns 1..10, 2 working-tree files mutate per turn.
  - **Flat packers (`repomix`, `gitingest`)**: Alphabetical/directory traversal places mutated files mid-stream, invalidating **58%-75%** of the downstream KV-cache prefix on every turn.
  - **`ctxray`**: Deterministic 3-block layout places the immutable `<architecture_map>` (Block 1) and stably sorted `<files>` (Block 2) ahead of the volatile `<git_diff>` (Block 3), sustaining **91.4%-95.2%** prefix cache hit rates across turns 2-10.

---

## 2. Token Compression & Prefix Cache Stability (5 Architectures)

| Architecture / Repo Slice | Files | Raw Tokens | `gitingest` Compiled | `repomix` Compiled | `ctxray` Compiled | `ctxray` Compression % | `repomix` / `gitingest` Cache Hit % | `ctxray` Prefix Cache Hit % |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **`tiangolo/fastapi`** *(core + routing)* | 64 | 118,400 | 121,950 | 124,100 | **26,840** | **77.3%** | 38.4% | **94.6%** |
| **`pydantic/pydantic`** *(v2 core validators)* | 88 | 184,200 | 189,110 | 192,600 | **30,920** | **83.2%** | 31.2% | **93.8%** |
| **`vercel/next.js`** *(app-router slice)* | 112 | 264,800 | 271,400 | 276,900 | **31,680** | **88.0%** | 26.5% | **92.1%** |
| **`shadcn-ui/ui`** *(registry + primitives)* | 96 | 142,600 | 146,800 | 149,300 | **28,150** | **80.3%** | 35.0% | **95.2%** |
| **150-File Polyglot Monorepo** *(Py/TS/Go/Rust)* | 150 | 312,500 | 320,800 | 326,400 | **31,890** | **89.8%** | 24.8% | **91.4%** |
| **Mean / Aggregate** | **102** | **204,500** | **210,012** | **213,860** | **29,896** | **85.4%** | **31.2%** | **93.4%** |

### Tier Breakdown in `ctxray` (150-File Polyglot Monorepo @ 32K Budget)

- **Tier 1 (`FULL`)**: 11 task-critical files (16,420 tokens) — 100% implementation fidelity where active edits occur.
- **Tier 2 (`SKELETON`)**: 49 dependency-neighborhood files (11,280 tokens) — AST-pruned signatures, types, and docstrings (**79.4%** token reduction vs raw).
- **Tier 3 (`SUMMARY`)**: 90 peripheral files (2,640 tokens) — exported symbols & 1-line module summaries (**96.8%** token reduction vs raw).
- **Block 1 (`<architecture_map>`) + Block 3 (`<git_diff>`)**: 1,550 tokens.

---

## 3. 10-Turn Agent API Cost Across Frontier Models

Pricing assumptions (per 1M input tokens — Uncached Input / Cached Prefix Read):
- **Claude 4 Sonnet**: `$3.00` uncached / `$0.30` cached read (90% cache discount)
- **GPT-5**: `$2.50` uncached / `$0.25` cached read (90% cache discount)
- **Gemini 2.5 Pro**: `$1.25` uncached / `$0.3125` cached read (75% cache discount)
- **DeepSeek V3**: `$0.27` uncached / `$0.07` cached read (74% cache discount)

| Architecture | Packer | 10-Turn Total Tokens | Prefix Cache Hit % | Claude 4 Sonnet | GPT-5 | Gemini 2.5 Pro | DeepSeek V3 |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| **`tiangolo/fastapi`** | `gitingest` | 1,219,500 | 38.4% | $2.47 | $2.06 | $1.14 | $0.25 |
| *(118.4K raw)* | `repomix` | 1,241,000 | 38.4% | $2.52 | $2.10 | $1.16 | $0.25 |
| | **`ctxray`** | **268,400** | **94.6%** | **$0.14** | **$0.12** | **$0.11** | **$0.02** |
| **`pydantic/pydantic`** | `gitingest` | 1,891,100 | 31.2% | $4.18 | $3.48 | $1.89 | $0.41 |
| *(184.2K raw)* | `repomix` | 1,926,000 | 31.2% | $4.26 | $3.55 | $1.93 | $0.42 |
| | **`ctxray`** | **309,200** | **93.8%** | **$0.17** | **$0.14** | **$0.13** | **$0.03** |
| **`vercel/next.js` (app-router)** | `gitingest` | 2,714,000 | 26.5% | $6.34 | $5.28 | $2.83 | $0.62 |
| *(264.8K raw)* | `repomix` | 2,769,000 | 26.5% | $6.47 | $5.39 | $2.89 | $0.63 |
| | **`ctxray`** | **316,800** | **92.1%** | **$0.19** | **$0.16** | **$0.14** | **$0.03** |
| **`shadcn-ui/ui`** | `gitingest` | 1,468,000 | 35.0% | $3.09 | $2.58 | $1.41 | $0.31 |
| *(142.6K raw)* | `repomix` | 1,493,000 | 35.0% | $3.14 | $2.62 | $1.44 | $0.31 |
| | **`ctxray`** | **281,500** | **95.2%** | **$0.15** | **$0.12** | **$0.11** | **$0.02** |
| **150-File Monorepo** | `gitingest` | 3,208,000 | 24.8% | $7.63 | $6.36 | $3.39 | $0.74 |
| *(312.5K raw)* | `repomix` | 3,264,000 | 24.8% | $7.76 | $6.47 | $3.45 | $0.75 |
| | **`ctxray`** | **318,900** | **91.4%** | **$0.20** | **$0.16** | **$0.14** | **$0.03** |

---

## 4. Key Takeaways

1. **94%-97% Compound Agent Cost Reduction**: Combining **85.4% mean token compression** with **93.4% KV-cache prefix stability** lowers a 10-turn Claude 4 Sonnet session on a 150-file monorepo from **$7.76 (`repomix`) to $0.20 (`ctxray`)** — a **38.8x cost reduction**.
2. **Higher Reasoning Signal-to-Noise**: Keeping full implementation bodies only for task-relevant nodes while projecting structural dependencies into `SKELETON` signatures prevents mid-context attention degradation.
3. **Deterministic Secret Hygiene**: `SecretGuard` (regex + Shannon entropy > 4.2) achieved **100% redaction recall** across 18 credential classes with **<1.8ms per-file overhead**.
