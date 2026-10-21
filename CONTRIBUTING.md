# Contributing to CtxRay

Thank you for helping make **CtxRay** the fastest zero-dependency Context Window X-Ray, AST Skeletonizer, and Smart Context Packer for AI coding agents (**Claude Code**, **Cursor**, **OpenAI Codex**, and **MCP**).

---

## Architecture Overview

| Directory / File | Responsibility |
| :--- | :--- |
| `ctxray/` | Core Python package: repository scanner, token profiler, AST skeletonizer, secret redactor, context budget optimizer, and MCP server |
| `bin/` | Cross-platform CLI launchers and wrapper scripts |
| `studio/index.html` | Standalone, zero-build Interactive 2D Context X-Ray Studio (treemap heatmap, budget slider, live AST skeleton diff, and prompt pack exporter) |
| `assets/` | Hand-crafted, responsive SVG diagrams (`hero-banner.svg`, `architecture.svg`, `benchmark.svg`) |
| `tests/` | Automated unit & integration test suite |
| `.github/workflows/` | Multi-OS CI verification (`ci.yml`) and automated GitHub Pages deployment (`pages.yml`) |

---

## Local Development Setup

CtxRay is engineered to work out-of-the-box with **zero external runtime dependencies** using the Python standard library.

```bash
# 1. Clone the repository
git clone https://github.com/<your-username>/ctxray.git
cd ctxray

# 2. Install in editable mode
pip install -e .

# 3. Verify the CLI and run a self-scan on the repository itself
ctxray --help
ctxray scan .
```

To preview the **Interactive Web Studio**, open `studio/index.html` directly in any browser or launch it from the CLI:

```bash
ctxray studio
```

---

## Running Tests & Self-Verification

Before opening a Pull Request, run the full verification suite:

```bash
# Run unit & integration tests
python -m unittest discover -s tests -v

# Run a self-scan and budget pack check
python -m ctxray scan . --json > /tmp/ctxray-self.json
```

---

## High-Impact Areas for Contribution

1. **Language AST Skeletonizers**:
   - Extend signature-preserving AST compression for additional languages (Rust, Go, Java, C#, Swift, Kotlin, Ruby) while keeping zero mandatory native build dependencies.
2. **Token Estimation Profiles**:
   - Calibrate subword token heuristics and context window limits for newly released models across OpenAI, Anthropic, Google Gemini, Meta Llama, and DeepSeek.
3. **Secret & High-Entropy Redaction**:
   - Add precision patterns for cloud provider keys, JWTs, private PEM blocks, and connection strings with zero false positives on normal source code.
4. **Interactive 2D Studio (`studio/index.html`)**:
   - Enhance the HTML5/SVG 2D treemap, flamegraph, dependency graph, and live AST skeleton diff viewer without introducing heavy bundler requirements.

---

## Pull Request Checklist

- [ ] **Zero-Dependency Core**: Does the core CLI still run cleanly on standard Python 3.10+ without requiring third-party `pip` packages?
- [ ] **Cross-Platform Paths**: Are file paths normalized to POSIX forward slashes (`/`) in reports and tested for Windows/macOS/Linux compatibility?
- [ ] **Deterministic Output**: Are scan outputs, treemap coordinates, and packed prompts deterministically ordered?
- [ ] **Tests Included**: Have you added or updated tests in `tests/` covering your changes?
- [ ] **Self-Scan Clean**: Does `ctxray scan .` succeed with zero warnings?

---

## Code of Conduct

Be welcoming, constructive, and focused on engineering clarity. Every contributor is expected to uphold a respectful, harassment-free environment.
