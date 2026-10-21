# AGENTS.md — OpenAI Codex & Autonomous Agent Guidelines (ctxray)

Use **ctxray** to navigate the dependency graph, compress file context via AST skeletons, and verify change blast radius before committing multi-file modifications.

## Core Agent Protocol

### Phase 1: Fast Orientation (Token-Budgeted)
- Run `python ctxray.py rank . --top 15` or call MCP `ctxray_repo_map` to identify high-PageRank hub modules and entrypoints.
- Use `python ctxray.py map . --budget 2000 --query "<task>"` to assemble a task-focused context pack in one call.

### Phase 2: Impact & Blast-Radius Verification
- **Before** editing any shared module, run:
  ```bash
  python ctxray.py blast <path/to/file> --depth 2
  ```
- If the blast radius reports **HIGH** or **CRITICAL** risk (or >5 transitive dependents), inspect every direct caller via `python ctxray.py skel <caller>` and include affected downstream tests in your verification step.

### Phase 3: Surgical Reading & Editing
- Prefer `python ctxray.py skel <file>` (`ctxray_skeletonize`) when you only need class/function signatures, types, or imports.
- Reserve full-file reads for the exact files being patched with `apply_patch`.

## MCP Server Registration
To expose `ctxray` as native MCP tools (`ctxray_repo_map`, `ctxray_blast_radius`, `ctxray_skeletonize`), add to your MCP config:
```json
{
  "mcpServers": {
    "ctxray": {
      "command": "python",
      "args": ["ctxray.py", "mcp"]
    }
  }
}
```
