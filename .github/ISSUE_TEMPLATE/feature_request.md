---
name: "Feature Request"
about: "Propose a new context-engineering feature, language parser, token model, or Studio visualization"
title: "[Feat]: "
labels: ["enhancement"]
assignees: []
---

## Context Engineering Problem

What context window bottleneck, token waste, or developer workflow friction does this feature address?
*(e.g., "When packing a mixed Rust + TypeScript monorepo for Claude Code, I want to keep trait signatures while pruning test fixtures under a 32k token budget.")*

## Proposed Solution

Describe the desired CLI command, flag, MCP tool, or Interactive Studio capability:

```bash
# Example proposed CLI usage
ctxray pack . --budget 32000 --strategy ast-skeleton --focus src/core
```

## Impact on Token Efficiency & Accuracy

How will this improve context signal-to-noise ratio (SNR), token compression, or agent task accuracy?

## Target Surface

- [ ] CLI Flag / Subcommand
- [ ] New Language AST Skeletonizer
- [ ] Model Tokenizer Profile (OpenAI `o200k_base` / `cl100k_base`, Claude, Gemini, DeepSeek)
- [ ] MCP Tool / Resource
- [ ] Interactive 2D X-Ray Studio (`studio/index.html`)

## Alternatives Considered

Describe any workarounds, `.ctxrayignore` rules, or external scripts you have tried.
