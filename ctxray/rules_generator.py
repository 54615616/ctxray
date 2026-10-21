from __future__ import annotations

"""
ctxray.rules_generator — Automatic Repository-Specific AI Rules Compiler (`ctxray init-rules`).

Inspects a `RepoAnalysis` + dependency graph forensics for any repository and
compiles customized, data-driven instruction files tailored to that exact codebase:
  - `CLAUDE.md` (Anthropic Claude Code instructions & architectural map)
  - `AGENTS.md` (OpenAI Codex / autonomous agent operating manual)
  - `.cursor/rules/architecture.mdc` (Cursor IDE always-apply rules with file maps)
"""

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple, Union

from .engine import ContextCompiler, FileNode, RepoAnalysis


LANGUAGE_LABELS: Dict[str, str] = {
    ".py": "Python",
    ".ts": "TypeScript",
    ".tsx": "TypeScript (React/JSX)",
    ".js": "JavaScript",
    ".jsx": "JavaScript (JSX)",
    ".mts": "TypeScript (ESM)",
    ".cts": "TypeScript (CJS)",
    ".rs": "Rust",
    ".go": "Go",
    ".java": "Java",
    ".c": "C",
    ".cpp": "C++",
    ".h": "C/C++ Header",
    ".hpp": "C++ Header",
    ".cs": "C#",
    ".rb": "Ruby",
    ".php": "PHP",
    ".swift": "Swift",
    ".kt": "Kotlin",
    ".scala": "Scala",
    ".sql": "SQL",
    ".graphql": "GraphQL",
    ".proto": "Protocol Buffers",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".toml": "TOML",
    ".json": "JSON",
    ".md": "Markdown",
    ".sh": "Shell",
    ".ps1": "PowerShell",
}


@dataclass
class HotspotRecord:
    """Normalized architectural hotspot with PageRank and blast-radius telemetry."""

    rank: int
    rel_path: str
    tier: str
    pagerank: float
    in_degree: int
    out_degree: int
    transitive_dependents: int
    raw_tokens: int
    skeleton_tokens: int
    allocated_tokens: int
    risk_level: str
    imports: List[str]
    dependents: List[str]

    @property
    def compression_pct(self) -> float:
        if self.raw_tokens <= 0:
            return 0.0
        return round((1.0 - self.skeleton_tokens / self.raw_tokens) * 100.0, 1)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rank": self.rank,
            "rel_path": self.rel_path,
            "tier": self.tier,
            "pagerank": round(self.pagerank, 4),
            "in_degree": self.in_degree,
            "out_degree": self.out_degree,
            "transitive_dependents": self.transitive_dependents,
            "raw_tokens": self.raw_tokens,
            "skeleton_tokens": self.skeleton_tokens,
            "allocated_tokens": self.allocated_tokens,
            "compression_pct": self.compression_pct,
            "risk_level": self.risk_level,
            "imports": self.imports,
            "dependents": self.dependents,
        }


def _ensure_analysis(analysis_or_path: Any, budget_tokens: int = 32_000) -> RepoAnalysis:
    """Accepts a RepoAnalysis instance, a dict representation, or a repository path."""
    if isinstance(analysis_or_path, RepoAnalysis):
        return analysis_or_path
    if isinstance(analysis_or_path, (str, Path)):
        return ContextCompiler(analysis_or_path, budget_tokens=budget_tokens).scan_and_compile()
    if isinstance(analysis_or_path, dict):
        files_raw = analysis_or_path.get("files", [])
        files: List[FileNode] = []
        for f in files_raw:
            if isinstance(f, FileNode):
                files.append(f)
            elif isinstance(f, dict):
                files.append(
                    FileNode(
                        rel_path=str(f.get("rel_path", "")),
                        ext=str(f.get("ext", ".txt")),
                        size_bytes=int(f.get("size_bytes", 0)),
                        lines=int(f.get("lines", 0)),
                        raw_tokens=int(f.get("raw_tokens", 0)),
                        skeleton_tokens=int(f.get("skeleton_tokens", 0)),
                        summary_tokens=int(f.get("summary_tokens", 0)),
                        pagerank=float(f.get("pagerank", 0.0)),
                        in_degree=int(f.get("in_degree", 0)),
                        out_degree=int(f.get("out_degree", 0)),
                        tier=str(f.get("tier", "FULL")),
                        allocated_tokens=int(f.get("allocated_tokens", 0)),
                        secrets_redacted=int(f.get("secrets_redacted", 0)),
                        imports=list(f.get("imports", [])),
                        dependents=list(f.get("dependents", [])),
                    )
                )
        edges_raw = analysis_or_path.get("edges", [])
        edges: List[Tuple[str, str]] = []
        for e in edges_raw:
            if isinstance(e, (tuple, list)) and len(e) == 2:
                edges.append((str(e[0]), str(e[1])))
            elif isinstance(e, dict) and "source" in e and "target" in e:
                edges.append((str(e["source"]), str(e["target"])))
        return RepoAnalysis(
            root_path=str(analysis_or_path.get("root_path", ".")),
            repo_name=str(analysis_or_path.get("repo_name", "repository")),
            total_files=int(analysis_or_path.get("total_files", len(files))),
            raw_total_tokens=int(analysis_or_path.get("raw_total_tokens", sum(x.raw_tokens for x in files))),
            compiled_total_tokens=int(
                analysis_or_path.get("compiled_total_tokens", sum(x.allocated_tokens for x in files))
            ),
            budget_tokens=int(analysis_or_path.get("budget_tokens", budget_tokens)),
            savings_pct=float(analysis_or_path.get("savings_pct", 0.0)),
            estimated_cache_hit_pct=float(analysis_or_path.get("estimated_cache_hit_pct", 92.0)),
            secrets_redacted=int(analysis_or_path.get("secrets_redacted", 0)),
            tier_counts=dict(analysis_or_path.get("tier_counts", {"FULL": 0, "SKELETON": 0, "SUMMARY": 0})),
            files=files,
            edges=edges,
            git_diff_tokens=int(analysis_or_path.get("git_diff_tokens", 0)),
            git_diff_summary=str(analysis_or_path.get("git_diff_summary", "")),
        )
    raise TypeError(f"Unsupported analysis input type: {type(analysis_or_path)!r}")


def _compute_transitive_dependents(analysis: RepoAnalysis, target_path: str) -> int:
    """Computes total upstream transitive dependents (blast radius) via reverse-edge BFS."""
    by_path = {f.rel_path: f for f in analysis.files}
    if target_path not in by_path:
        return 0
    visited: Set[str] = {target_path}
    queue: List[str] = [target_path]
    while queue:
        curr = queue.pop(0)
        node = by_path.get(curr)
        if not node:
            continue
        for dep in node.dependents:
            if dep not in visited:
                visited.add(dep)
                queue.append(dep)
    return max(0, len(visited) - 1)


def detect_cycles_from_analysis(analysis: RepoAnalysis, max_cycles: int = 20) -> List[List[str]]:
    """
    Finds circular dependency chains in `analysis.edges` using Tarjan's strongly
    connected components + deterministic cycle path reconstruction.
    """
    adj: Dict[str, List[str]] = defaultdict(list)
    nodes: Set[str] = set()
    for src, dst in analysis.edges:
        if src != dst:
            adj[src].append(dst)
            nodes.add(src)
            nodes.add(dst)
    for p in adj:
        adj[p].sort()

    index = 0
    indices: Dict[str, int] = {}
    lowlink: Dict[str, int] = {}
    stack: List[str] = []
    on_stack: Set[str] = set()
    sccs: List[List[str]] = []

    for start_v in sorted(nodes):
        if start_v in indices:
            continue
        indices[start_v] = index
        lowlink[start_v] = index
        index += 1
        stack.append(start_v)
        on_stack.add(start_v)
        work_stack: List[Tuple[str, List[str], int]] = [(start_v, adj.get(start_v, []), 0)]
        while work_stack:
            v, nbrs, ptr = work_stack[-1]
            if ptr < len(nbrs):
                w = nbrs[ptr]
                work_stack[-1] = (v, nbrs, ptr + 1)
                if w not in indices:
                    indices[w] = index
                    lowlink[w] = index
                    index += 1
                    stack.append(w)
                    on_stack.add(w)
                    work_stack.append((w, adj.get(w, []), 0))
                elif w in on_stack:
                    lowlink[v] = min(lowlink[v], indices[w])
            else:
                work_stack.pop()
                if work_stack:
                    parent_v = work_stack[-1][0]
                    lowlink[parent_v] = min(lowlink[parent_v], lowlink[v])
                if lowlink[v] == indices[v]:
                    comp: List[str] = []
                    while True:
                        w = stack.pop()
                        on_stack.remove(w)
                        comp.append(w)
                        if w == v:
                            break
                    if len(comp) > 1:
                        sccs.append(sorted(comp))

    cycles: List[List[str]] = []
    seen_signatures: Set[Tuple[str, ...]] = set()

    for comp in sccs:
        comp_set = set(comp)
        for start_node in comp:
            if len(cycles) >= max_cycles:
                break
            queue: List[Tuple[str, List[str]]] = [(start_node, [start_node])]
            visited_local: Set[str] = set()
            found_for_start = False
            while queue and not found_for_start:
                curr, path_so_far = queue.pop(0)
                for nxt in adj.get(curr, []):
                    if nxt not in comp_set:
                        continue
                    if nxt == start_node and len(path_so_far) >= 2:
                        min_idx = min(range(len(path_so_far)), key=lambda i: path_so_far[i])
                        canonical = tuple(path_so_far[min_idx:] + path_so_far[:min_idx])
                        if canonical not in seen_signatures:
                            seen_signatures.add(canonical)
                            cycles.append(list(canonical) + [canonical[0]])
                        found_for_start = True
                        break
                    if nxt not in visited_local and len(path_so_far) < 8:
                        visited_local.add(nxt)
                        queue.append((nxt, path_so_far + [nxt]))

    return cycles


def _normalize_cycles(analysis: RepoAnalysis, cycles: Any = None) -> List[List[str]]:
    """Normalizes arbitrary cycle representations into a clean list of `[A, B, ..., A]` chains."""
    if cycles is None:
        return detect_cycles_from_analysis(analysis)
    normalized: List[List[str]] = []
    if not isinstance(cycles, Iterable) or isinstance(cycles, (str, bytes)):
        return detect_cycles_from_analysis(analysis)

    for item in cycles:
        chain: List[str] = []
        if isinstance(item, (list, tuple)):
            chain = [str(x) for x in item if x]
        elif isinstance(item, dict):
            raw = item.get("cycle") or item.get("nodes") or item.get("files") or item.get("path") or []
            if isinstance(raw, (list, tuple)):
                chain = [str(x) for x in raw if x]
            elif isinstance(raw, str):
                chain = [s.strip() for s in raw.split("->") if s.strip()]
        elif hasattr(item, "cycle") or hasattr(item, "nodes") or hasattr(item, "files"):
            raw = getattr(item, "cycle", None) or getattr(item, "nodes", None) or getattr(item, "files", [])
            chain = [str(x) for x in raw if x]
        elif isinstance(item, str):
            chain = [s.strip() for s in item.split("->") if s.strip()]

        if len(chain) >= 2:
            if chain[0] != chain[-1]:
                chain = chain + [chain[0]]
            normalized.append(chain)
    return normalized


def _normalize_hotspots(
    analysis: RepoAnalysis, hotspots: Any = None, limit: int = 15
) -> List[HotspotRecord]:
    """
    Normalizes caller-supplied hotspots or derives the Top N PageRank architectural
    hotspots directly from `RepoAnalysis`.
    """
    by_path: Dict[str, FileNode] = {f.rel_path: f for f in analysis.files}
    records: List[HotspotRecord] = []

    source_items: List[Any] = []
    if hotspots is None:
        source_items = list(
            sorted(
                analysis.files,
                key=lambda f: (f.pagerank, f.in_degree, f.raw_tokens),
                reverse=True,
            )[:limit]
        )
    elif isinstance(hotspots, Iterable) and not isinstance(hotspots, (str, bytes, dict)):
        source_items = list(hotspots)[:limit]
    elif isinstance(hotspots, dict) and "hotspots" in hotspots:
        source_items = list(hotspots["hotspots"])[:limit]
    else:
        source_items = list(analysis.files[:limit])

    for idx, item in enumerate(source_items, start=1):
        if isinstance(item, HotspotRecord):
            records.append(item)
            continue
        if isinstance(item, FileNode):
            trans = _compute_transitive_dependents(analysis, item.rel_path)
            risk = (
                "CRITICAL"
                if item.pagerank >= 0.70 or trans >= 4 or item.in_degree >= 3
                else "HIGH"
                if item.pagerank >= 0.45 or trans >= 2 or item.in_degree >= 2
                else "MODERATE"
                if item.pagerank >= 0.25 or item.in_degree >= 1
                else "LOW"
            )
            records.append(
                HotspotRecord(
                    rank=idx,
                    rel_path=item.rel_path,
                    tier=item.tier,
                    pagerank=item.pagerank,
                    in_degree=item.in_degree,
                    out_degree=item.out_degree,
                    transitive_dependents=trans,
                    raw_tokens=item.raw_tokens,
                    skeleton_tokens=item.skeleton_tokens,
                    allocated_tokens=item.allocated_tokens,
                    risk_level=risk,
                    imports=list(item.imports),
                    dependents=list(item.dependents),
                )
            )
            continue

        if isinstance(item, dict):
            path_str = str(
                item.get("rel_path") or item.get("path") or item.get("file") or item.get("target") or ""
            )
        else:
            path_str = str(
                getattr(item, "rel_path", None)
                or getattr(item, "path", None)
                or getattr(item, "file", None)
                or item
            )

        matched_node = by_path.get(path_str)

        def _get(attr: str, default: Any) -> Any:
            if isinstance(item, dict) and attr in item and item[attr] is not None:
                return item[attr]
            if hasattr(item, attr) and getattr(item, attr) is not None:
                return getattr(item, attr)
            if matched_node is not None and hasattr(matched_node, attr):
                return getattr(matched_node, attr)
            return default

        pr = float(_get("pagerank", 0.5))
        in_deg = int(_get("in_degree", 0))
        out_deg = int(_get("out_degree", 0))
        raw_tok = int(_get("raw_tokens", 0))
        skel_tok = int(_get("skeleton_tokens", raw_tok))
        alloc_tok = int(_get("allocated_tokens", skel_tok))
        tier = str(_get("tier", "FULL"))
        imports = list(_get("imports", []))
        dependents = list(_get("dependents", []))
        trans = int(
            _get(
                "transitive_dependents",
                _get("transitive_impact_count", _compute_transitive_dependents(analysis, path_str)),
            )
        )
        default_risk = (
            "CRITICAL"
            if pr >= 0.70 or trans >= 4 or in_deg >= 3
            else "HIGH"
            if pr >= 0.45 or trans >= 2 or in_deg >= 2
            else "MODERATE"
            if pr >= 0.25 or in_deg >= 1
            else "LOW"
        )
        risk = str(_get("risk_level", default_risk)).upper()

        records.append(
            HotspotRecord(
                rank=idx,
                rel_path=path_str,
                tier=tier,
                pagerank=pr,
                in_degree=in_deg,
                out_degree=out_deg,
                transitive_dependents=trans,
                raw_tokens=raw_tok,
                skeleton_tokens=skel_tok,
                allocated_tokens=alloc_tok,
                risk_level=risk,
                imports=imports,
                dependents=dependents,
            )
        )

    return records[:limit]


def _extract_tech_stack(analysis: RepoAnalysis) -> List[Dict[str, Any]]:
    """Aggregates repository files by language/extension with line and token telemetry."""
    by_lang: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {"files": 0, "lines": 0, "raw_tokens": 0, "skeleton_tokens": 0, "allocated_tokens": 0}
    )
    for f in analysis.files:
        label = LANGUAGE_LABELS.get(f.ext.lower(), f.ext.upper().lstrip(".") or "Text")
        bucket = by_lang[label]
        bucket["files"] += 1
        bucket["lines"] += f.lines
        bucket["raw_tokens"] += f.raw_tokens
        bucket["skeleton_tokens"] += f.skeleton_tokens
        bucket["allocated_tokens"] += f.allocated_tokens

    total_tok = max(1, analysis.raw_total_tokens)
    rows: List[Dict[str, Any]] = []
    for lang, stats in sorted(by_lang.items(), key=lambda kv: (kv[1]["raw_tokens"], kv[1]["files"]), reverse=True):
        rows.append(
            {
                "language": lang,
                "files": stats["files"],
                "lines": stats["lines"],
                "raw_tokens": stats["raw_tokens"],
                "skeleton_tokens": stats["skeleton_tokens"],
                "allocated_tokens": stats["allocated_tokens"],
                "share_pct": round((stats["raw_tokens"] / total_tok) * 100.0, 1),
            }
        )
    return rows


def _discover_entrypoints(analysis: RepoAnalysis) -> List[Dict[str, str]]:
    """Detects executable entrypoints, CLI routers, MCP servers, and package manifests."""
    entrypoints: List[Dict[str, str]] = []
    seen: Set[str] = set()

    rules: List[Tuple[str, str]] = [
        ("cli.py", "CLI Command Dispatcher & Argument Parser"),
        ("__main__.py", "Python Package Module Entrypoint"),
        ("ctxray.py", "Standalone Zero-Install CLI Launcher"),
        ("mcp_server.py", "Model Context Protocol (MCP) JSON-RPC Stdio Server"),
        ("engine.py", "Core Dependency PageRank & AST Skeletonizer Engine"),
        ("rules_generator.py", "Repository-Specific AI Rules Compiler"),
        ("trace_analyzer.py", "AI Agent Session Flight Recorder & Token Forensics"),
        ("main.py", "Primary Application Entrypoint"),
        ("app.py", "Application Server Entrypoint"),
        ("server.py", "Backend Server Entrypoint"),
        ("index.ts", "TypeScript Module Entrypoint"),
        ("index.js", "JavaScript Module Entrypoint"),
        ("main.rs", "Rust Binary Entrypoint"),
        ("lib.rs", "Rust Library Root"),
        ("main.go", "Go Binary Entrypoint"),
        ("pyproject.toml", "Python Packaging & Build Manifest"),
        ("package.json", "Node.js / CLI Package Manifest"),
        ("Cargo.toml", "Rust Crate Manifest"),
        ("Dockerfile", "Container Build Specification"),
    ]

    for f in analysis.files:
        name = Path(f.rel_path).name
        lower_rel = f.rel_path.lower()
        for pattern, role in rules:
            if name == pattern or lower_rel.endswith("/" + pattern):
                if f.rel_path not in seen:
                    seen.add(f.rel_path)
                    entrypoints.append(
                        {
                            "path": f.rel_path,
                            "role": role,
                            "pagerank": f"{f.pagerank:.3f}",
                            "tokens": f"{f.raw_tokens:,}",
                        }
                    )
                break
        else:
            if lower_rel.startswith("bin/") or "if __name__" in f.raw_content:
                if f.rel_path not in seen:
                    seen.add(f.rel_path)
                    entrypoints.append(
                        {
                            "path": f.rel_path,
                            "role": "Executable Script / Entrypoint",
                            "pagerank": f"{f.pagerank:.3f}",
                            "tokens": f"{f.raw_tokens:,}",
                        }
                    )

    if not entrypoints and analysis.files:
        for f in analysis.files[:5]:
            entrypoints.append(
                {
                    "path": f.rel_path,
                    "role": "High-Centrality Architectural Module",
                    "pagerank": f"{f.pagerank:.3f}",
                    "tokens": f"{f.raw_tokens:,}",
                }
            )
    return entrypoints[:12]


def _group_modules_by_directory(analysis: RepoAnalysis) -> List[Dict[str, Any]]:
    """Summarizes top-level directories/packages with file counts, token weight, and top modules."""
    groups: Dict[str, List[FileNode]] = defaultdict(list)
    for f in analysis.files:
        parts = Path(f.rel_path).parts
        top_dir = parts[0] if len(parts) > 1 else "(root)"
        groups[top_dir].append(f)

    summary: List[Dict[str, Any]] = []
    for folder, nodes in sorted(
        groups.items(),
        key=lambda kv: (sum(n.pagerank for n in kv[1]), sum(n.raw_tokens for n in kv[1])),
        reverse=True,
    ):
        top_nodes = sorted(nodes, key=lambda n: n.pagerank, reverse=True)[:4]
        summary.append(
            {
                "directory": folder,
                "file_count": len(nodes),
                "raw_tokens": sum(n.raw_tokens for n in nodes),
                "compiled_tokens": sum(n.allocated_tokens for n in nodes),
                "max_pagerank": round(max((n.pagerank for n in nodes), default=0.0), 3),
                "key_files": [n.rel_path for n in top_nodes],
            }
        )
    return summary


def _render_dependency_map_section(analysis: RepoAnalysis, hotspots: List[HotspotRecord]) -> str:
    """Renders a clear module dependency graph section with upstream and downstream links."""
    fence = chr(96) * 3
    lines: List[str] = []
    active_nodes = [h for h in hotspots if h.imports or h.dependents]
    if not active_nodes:
        active_nodes = hotspots[:8]

    lines.append(f"{fence}text")
    for h in active_nodes[:12]:
        deps_in = ", ".join(h.dependents[:4]) if h.dependents else "none (root/entrypoint)"
        deps_out = ", ".join(h.imports[:4]) if h.imports else "none (zero internal imports / leaf)"
        if len(h.dependents) > 4:
            deps_in += f" (+{len(h.dependents) - 4} more)"
        if len(h.imports) > 4:
            deps_out += f" (+{len(h.imports) - 4} more)"
        lines.append(
            f"[{h.risk_level:<8}] {h.rel_path} (PR={h.pagerank:.3f}, blast={h.transitive_dependents} files)"
        )
        lines.append(f"   ├── Imported by (upstream dependents): {deps_in}")
        lines.append(f"   └── Depends on  (downstream imports) : {deps_out}")
    lines.append(fence)
    return "\n".join(lines)


def _render_cycles_section(cycles: List[List[str]]) -> str:
    """Renders circular dependency warnings or DAG verification badge."""
    if not cycles:
        return (
            "- **Status**: `PASS — 0 Circular Dependencies Detected (Strict Acyclic Graph Verified)`\n"
            "- **Rule**: Preserve this DAG invariant. Never introduce mutual imports between high-PageRank core modules and CLI/presentation layers."
        )
    lines = [
        f"- **Status**: `WARNING — {len(cycles)} Circular Dependency Chain(s) Detected`",
        "- **Action Required**: Do not deepen existing cycles. Extract shared data types/protocols into a leaf schema module when modifying any file below:",
        "",
    ]
    for idx, cyc in enumerate(cycles[:10], start=1):
        chain_str = " -> ".join(f"`{node}`" for node in cyc)
        lines.append(f"  {idx}. **Cycle #{idx}** ({len(cyc) - 1} hops): {chain_str}")
    return "\n".join(lines)


def generate_claude_md(
    analysis: Any,
    cycles: Any = None,
    hotspots: Any = None,
) -> str:
    """
    Generates a tailored `CLAUDE.md` containing the repository's real tech stack breakdown,
    Top 15 PageRank architectural hotspots (with blast-radius warnings), entrypoints,
    module dependency map, circular dependency warnings, and token-budget guidelines.
    """
    repo = _ensure_analysis(analysis)
    norm_cycles = _normalize_cycles(repo, cycles)
    norm_hotspots = _normalize_hotspots(repo, hotspots, limit=15)
    tech_stack = _extract_tech_stack(repo)
    entrypoints = _discover_entrypoints(repo)
    dir_groups = _group_modules_by_directory(repo)

    critical_hotspots = [h for h in norm_hotspots if h.risk_level in {"CRITICAL", "HIGH"}]

    lines: List[str] = [
        f"# CLAUDE.md — Architectural X-Ray & Context Rules for `{repo.repo_name}`",
        "",
        "> **Auto-Generated by `ctxray init-rules`** — Data-driven repository intelligence compiled from live AST & Dependency PageRank forensics.",
        "",
        "## 1. Executive Telemetry & Context Budget Snapshot",
        "",
        "| Metric | Value | Operational Guidance |",
        "| :--- | :--- | :--- |",
        f"| **Repository** | `{repo.repo_name}` | `{repo.total_files}` indexed source/config files |",
        f"| **Raw Token Footprint** | `{repo.raw_total_tokens:,} tokens` | Full unpruned source volume |",
        f"| **Compiled Context Bundle** | `{repo.compiled_total_tokens:,} tokens` | **-{repo.savings_pct}% compression** at `{repo.budget_tokens:,}` token budget |",
        f"| **Tier Distribution** | `FULL: {repo.tier_counts.get('FULL', 0)}` / `SKELETON: {repo.tier_counts.get('SKELETON', 0)}` / `SUMMARY: {repo.tier_counts.get('SUMMARY', 0)}` | PageRank-weighted fidelity allocation |",
        f"| **Estimated Prefix Cache Hit** | `{repo.estimated_cache_hit_pct}%` | Keep static map pinned ahead of volatile diffs |",
        f"| **Circular Dependencies** | `{len(norm_cycles)}` | {'DAG verified — zero import cycles' if not norm_cycles else 'Cycles detected — see Section 6'} |",
        "",
        "## 2. Real Tech Stack Breakdown",
        "",
        "| Language / Format | Files | Lines | Raw Tokens | Skeleton Tokens | Repo Token Share |",
        "| :--- | ---: | ---: | ---: | ---: | ---: |",
    ]

    for row in tech_stack:
        lines.append(
            f"| **{row['language']}** | {row['files']} | {row['lines']:,} | {row['raw_tokens']:,} | "
            f"{row['skeleton_tokens']:,} | {row['share_pct']}% |"
        )

    lines.extend(
        [
            "",
            "## 3. Repository Entrypoints & Subsystem Architecture",
            "",
            "### Primary Entrypoints",
            "",
            "| File Path | Architectural Role | PageRank | Raw Tokens |",
            "| :--- | :--- | ---: | ---: |",
        ]
    )
    for ep in entrypoints:
        lines.append(f"| `{ep['path']}` | {ep['role']} | `{ep['pagerank']}` | {ep['tokens']} |")

    lines.extend(
        [
            "",
            "### Directory / Package Breakdown",
            "",
            "| Directory | Files | Raw Tokens | Compiled Tokens | Peak PageRank | Key Modules |",
            "| :--- | ---: | ---: | ---: | ---: | :--- |",
        ]
    )
    for grp in dir_groups:
        key_mods = ", ".join(f"`{p}`" for p in grp["key_files"][:3])
        lines.append(
            f"| `{grp['directory']}` | {grp['file_count']} | {grp['raw_tokens']:,} | "
            f"{grp['compiled_tokens']:,} | `{grp['max_pagerank']:.3f}` | {key_mods} |"
        )

    lines.extend(
        [
            "",
            "## 4. Top 15 PageRank Architectural Hotspots & Blast-Radius Warnings",
            "",
            "Files below are ranked by **Dependency PageRank Centrality**. Modifying public signatures or data structures in `CRITICAL` / `HIGH` modules triggers cascading changes across upstream dependents.",
            "",
            "| Rank | File Path | Tier | PageRank | In/Out | Blast Radius | Tokens (Skel/Raw) | Risk Level |",
            "| ---: | :--- | :--- | ---: | :---: | ---: | ---: | :--- |",
        ]
    )
    for h in norm_hotspots:
        lines.append(
            f"| {h.rank} | `{h.rel_path}` | `{h.tier}` | `{h.pagerank:.3f}` | "
            f"`{h.in_degree}/{h.out_degree}` | `{h.transitive_dependents} files` | "
            f"`{h.skeleton_tokens:,}/{h.raw_tokens:,}` (-{h.compression_pct}%) | **{h.risk_level}** |"
        )

    if critical_hotspots:
        lines.extend(
            [
                "",
                "### Blast-Radius Guardrails for High-Centrality Modules",
                "",
            ]
        )
        for h in critical_hotspots[:6]:
            deps_preview = ", ".join(f"`{d}`" for d in h.dependents[:5]) if h.dependents else "external/CLI callers"
            lines.append(
                f"- **`{h.rel_path}`** (`{h.risk_level}` • PageRank `{h.pagerank:.3f}` • Transitive Impact: `{h.transitive_dependents}` files): "
                f"Run `python ctxray.py blast {h.rel_path}` before altering signatures. Direct dependents: {deps_preview}."
            )

    lines.extend(
        [
            "",
            "## 5. Module Dependency Map",
            "",
            _render_dependency_map_section(repo, norm_hotspots),
            "",
            "## 6. Circular Dependency Forensics",
            "",
            _render_cycles_section(norm_cycles),
            "",
            "## 7. Token-Budget & Context Hygiene Protocol for Claude Code",
            "",
            "1. **Use AST Skeletons Before Full Reads**:",
            "   - Before reading any file larger than `350 tokens` that you are not actively editing, run `python ctxray.py skeleton <file>` (or invoke MCP tool `ctxray_skeletonize`).",
            f"   - Across `{repo.repo_name}`, skeletonization compresses `{repo.raw_total_tokens:,}` raw tokens into `{repo.compiled_total_tokens:,}` tokens (**-{repo.savings_pct}%** savings) while retaining 100% of public signatures, types, and docstrings.",
            "2. **Never Dump Unbounded `cat` / `grep` Outputs into Context**:",
            "   - Avoid reading generated artifacts, lockfiles, or whole directories into the conversation history.",
            "   - Never re-read the same unchanged file across multiple turns; reference the pinned AST skeleton instead.",
            "3. **Check Blast Radius Before Editing Core Hubs**:",
            "   - Whenever modifying any file with `PageRank >= 0.45`, execute `python ctxray.py blast <file>` (or MCP `ctxray_blast_radius`) to inspect all upstream dependents that must stay contract-compatible.",
            "4. **Preserve Prefix-Cache Pinning**:",
            f"   - Keep static architectural context (`FULL -> SKELETON -> SUMMARY` sorted deterministically) at the top of the prompt prefix and append volatile `git diff` outputs at the tail to maintain `{repo.estimated_cache_hit_pct}%` prompt cache hit rate.",
            "",
        ]
    )
    return "\n".join(lines)


def generate_agents_md(
    analysis: Any,
    cycles: Any = None,
    hotspots: Any = None,
) -> str:
    """
    Generates a tailored `AGENTS.md` for OpenAI Codex and autonomous multi-turn software agents.
    """
    fence = chr(96) * 3
    repo = _ensure_analysis(analysis)
    norm_cycles = _normalize_cycles(repo, cycles)
    norm_hotspots = _normalize_hotspots(repo, hotspots, limit=15)
    tech_stack = _extract_tech_stack(repo)
    entrypoints = _discover_entrypoints(repo)
    dir_groups = _group_modules_by_directory(repo)

    lines: List[str] = [
        f"# AGENTS.md — Autonomous Agent Operating Manual for `{repo.repo_name}`",
        "",
        "> **Compiled by `ctxray init-rules`** — Deterministic Dependency PageRank, Blast-Radius Contracts & Token Economy Rules for OpenAI Codex and Autonomous Coding Agents.",
        "",
        "## 1. Repository Architecture & Token Economy Profile",
        "",
        f"- **Repository Name**: `{repo.repo_name}` (`{repo.total_files}` tracked files)",
        f"- **Token Compression**: `{repo.raw_total_tokens:,}` raw tokens -> `{repo.compiled_total_tokens:,}` compiled tokens (**-{repo.savings_pct}%** reduction at `{repo.budget_tokens:,}` budget)",
        f"- **Tier Allocation**: `FULL={repo.tier_counts.get('FULL', 0)}`, `SKELETON={repo.tier_counts.get('SKELETON', 0)}`, `SUMMARY={repo.tier_counts.get('SUMMARY', 0)}`",
        f"- **Expected Prefix Cache Hit Rate**: `{repo.estimated_cache_hit_pct}%`",
        f"- **Dependency Graph Integrity**: `{len(repo.edges)}` cross-file edges | `{len(norm_cycles)}` circular dependencies",
        "",
        "### Tech Stack Distribution",
        "",
        "| Language | Files | Lines | Raw Tokens | Skeleton Tokens | Share |",
        "| :--- | ---: | ---: | ---: | ---: | ---: |",
    ]

    for row in tech_stack:
        lines.append(
            f"| {row['language']} | {row['files']} | {row['lines']:,} | "
            f"{row['raw_tokens']:,} | {row['skeleton_tokens']:,} | {row['share_pct']}% |"
        )

    lines.extend(
        [
            "",
            "## 2. Fast Orientation: Entrypoints & Command Matrix",
            "",
            "| Entrypoint File | Subsystem Responsibility | PageRank | Tokens |",
            "| :--- | :--- | ---: | ---: |",
        ]
    )
    for ep in entrypoints:
        lines.append(f"| `{ep['path']}` | {ep['role']} | `{ep['pagerank']}` | {ep['tokens']} |")

    lines.extend(
        [
            "",
            "### Essential `ctxray` Verification & Navigation Commands",
            "",
            f"{fence}bash",
            "# 1. View Dependency PageRank & Token X-Ray table",
            "python ctxray.py rank . --budget 32k",
            "",
            "# 2. Inspect upstream/downstream blast radius before modifying a core module",
            "python ctxray.py blast <target-file>",
            "",
            "# 3. Read an AST signature skeleton (-60% to -80% fewer tokens than raw cat)",
            "python ctxray.py skeleton <file-path>",
            "",
            "# 4. Audit agent session token burn & cache breaks",
            "python ctxray.py trace --demo",
            "",
            "# 5. Regenerate CLAUDE.md, AGENTS.md, and .cursor/rules/architecture.mdc",
            "python ctxray.py init-rules .",
            fence,
            "",
            "## 3. Top 15 Architectural Hotspots (Dependency PageRank Order)",
            "",
            "| Rank | Module Path | Tier | PageRank | Dependents (Direct / Transitive) | Tokens (Skel / Raw) | Risk |",
            "| ---: | :--- | :--- | ---: | :---: | ---: | :--- |",
        ]
    )

    for h in norm_hotspots:
        lines.append(
            f"| {h.rank} | `{h.rel_path}` | `{h.tier}` | `{h.pagerank:.3f}` | "
            f"`{h.in_degree} / {h.transitive_dependents}` | `{h.skeleton_tokens:,} / {h.raw_tokens:,}` | **{h.risk_level}** |"
        )

    lines.extend(
        [
            "",
            "## 4. Subsystem & Directory Ownership Map",
            "",
        ]
    )
    for grp in dir_groups:
        sample = ", ".join(f"`{k}`" for k in grp["key_files"])
        lines.append(
            f"- **`{grp['directory']}`** ({grp['file_count']} files, `{grp['raw_tokens']:,}` raw tokens -> `{grp['compiled_tokens']:,}` compiled tokens, peak PR `{grp['max_pagerank']:.3f}`): Primary modules: {sample}"
        )

    lines.extend(
        [
            "",
            "## 5. Cross-Module Dependency Graph & Blast-Radius Contracts",
            "",
            _render_dependency_map_section(repo, norm_hotspots),
            "",
            "## 6. Circular Dependency Status & Architectural Invariants",
            "",
            _render_cycles_section(norm_cycles),
            "",
            "## 7. Mandatory Execution Discipline for Autonomous Agents",
            "",
            "1. **Surgical Context Loading**:",
            "   - Load `FULL` implementation bodies **only** for the 1–3 files you are actively modifying in the current task.",
            "   - For upstream/downstream neighbor modules, load `SKELETON` signatures (`python ctxray.py skeleton <path>`) to verify interface contracts without burning context tokens.",
            "2. **Blast-Radius Verification on Hotspot Edits**:",
            "   - Any edit to a `CRITICAL` or `HIGH` hotspot module requires verifying every file listed under its `Imported by (upstream dependents)` list.",
            "3. **Zero Duplicate File Reads**:",
            "   - Track files already inspected in the active session. Never run redundant full-file reads on unmodified files.",
            "4. **Secret Hygiene**:",
            "   - Never hardcode credentials or tokens; `SecretGuard` automatically redacts API keys, PATs, and private keys before context emission.",
            "",
        ]
    )
    return "\n".join(lines)


def generate_cursor_mdc(
    analysis: Any,
    cycles: Any = None,
    hotspots: Any = None,
) -> str:
    """
    Generates a tailored `.cursor/rules/architecture.mdc` with `alwaysApply: true`
    frontmatter and real repository file maps for Cursor IDE agents.
    """
    repo = _ensure_analysis(analysis)
    norm_cycles = _normalize_cycles(repo, cycles)
    norm_hotspots = _normalize_hotspots(repo, hotspots, limit=15)
    tech_stack = _extract_tech_stack(repo)
    entrypoints = _discover_entrypoints(repo)

    full_files = [f.rel_path for f in repo.files if f.tier == "FULL"][:12]
    skeleton_files = [f.rel_path for f in repo.files if f.tier == "SKELETON"][:12]
    summary_files = [f.rel_path for f in repo.files if f.tier == "SUMMARY"][:12]

    lines: List[str] = [
        "---",
        f"description: Architectural PageRank map, blast-radius guardrails, and token-budget rules for {repo.repo_name} (compiled by ctxray)",
        "globs: **/*",
        "alwaysApply: true",
        "---",
        "",
        f"# Cursor Architecture & Context Rules: `{repo.repo_name}`",
        "",
        f"This rule is automatically compiled by `ctxray init-rules` from `{repo.total_files}` repository files (`{repo.raw_total_tokens:,}` raw tokens -> `{repo.compiled_total_tokens:,}` compiled tokens, **-{repo.savings_pct}%** compression).",
        "",
        "## 1. Tech Stack & Entrypoint Map",
        "",
        "- **Languages**: "
        + ", ".join(f"{r['language']} ({r['files']} files, {r['share_pct']}%)" for r in tech_stack[:6]),
        "- **Entrypoints**: "
        + ", ".join(f"`{e['path']}` ({e['role']})" for e in entrypoints[:6]),
        "",
        "## 2. Top 15 PageRank Hotspots & Blast Radius",
        "",
        "| Rank | File | Tier | PageRank | Blast Radius | Skel/Raw Tokens | Risk |",
        "| ---: | :--- | :--- | ---: | ---: | ---: | :--- |",
    ]

    for h in norm_hotspots:
        lines.append(
            f"| {h.rank} | `{h.rel_path}` | `{h.tier}` | `{h.pagerank:.3f}` | "
            f"`{h.transitive_dependents} files` | `{h.skeleton_tokens:,}/{h.raw_tokens:,}` | **{h.risk_level}** |"
        )

    lines.extend(
        [
            "",
            "## 3. Repository File Map by Context Fidelity Tier",
            "",
            f"- **Tier 1 (`FULL` — Core Architectural Nuclei, {repo.tier_counts.get('FULL', 0)} files)**: "
            + (", ".join(f"`{p}`" for p in full_files) if full_files else "`none`"),
            f"- **Tier 2 (`SKELETON` — AST Signatures & Contracts, {repo.tier_counts.get('SKELETON', 0)} files)**: "
            + (", ".join(f"`{p}`" for p in skeleton_files) if skeleton_files else "`none`"),
            f"- **Tier 3 (`SUMMARY` — Compact Symbol Index, {repo.tier_counts.get('SUMMARY', 0)} files)**: "
            + (", ".join(f"`{p}`" for p in summary_files) if summary_files else "`none`"),
            "",
            "## 4. Dependency Edges & Circular Dependency Policy",
            "",
            _render_cycles_section(norm_cycles),
            "",
            "## 5. Cursor Agent Directives",
            "",
            "- **Check Blast Radius**: Before changing exports or function signatures in any `CRITICAL` or `HIGH` hotspot, run `python ctxray.py blast <file>` or use the `ctxray_blast_radius` MCP tool.",
            "- **Prefer Skeletons Over Full Dumps**: For reference files outside your immediate edit target, use `python ctxray.py skeleton <file>` or `ctxray_skeletonize` to save 60–80% context tokens.",
            "- **Maintain Prefix Cache Determinism**: Keep static context blocks ordered (`FULL -> SKELETON -> SUMMARY`) and place volatile `git diff` blocks last.",
            "",
        ]
    )
    return "\n".join(lines)


def write_all_rules(
    root_path: Union[str, Path],
    analysis: Any = None,
    cycles: Any = None,
    hotspots: Any = None,
    output_dir: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """
    Compiles and writes all repository-specific AI context rule files cleanly to disk:
      - `<output_dir>/CLAUDE.md`
      - `<output_dir>/AGENTS.md`
      - `<output_dir>/.cursor/rules/architecture.mdc`

    Returns a dictionary containing the written paths, generated contents, and telemetry summary.
    """
    root = Path(root_path).resolve()
    target_dir = Path(output_dir).resolve() if output_dir is not None else root

    repo = _ensure_analysis(analysis if analysis is not None else root)
    norm_cycles = _normalize_cycles(repo, cycles)
    norm_hotspots = _normalize_hotspots(repo, hotspots, limit=15)

    claude_md = generate_claude_md(repo, norm_cycles, norm_hotspots)
    agents_md = generate_agents_md(repo, norm_cycles, norm_hotspots)
    cursor_mdc = generate_cursor_mdc(repo, norm_cycles, norm_hotspots)

    target_dir.mkdir(parents=True, exist_ok=True)
    cursor_rules_dir = target_dir / ".cursor" / "rules"
    cursor_rules_dir.mkdir(parents=True, exist_ok=True)

    claude_path = target_dir / "CLAUDE.md"
    agents_path = target_dir / "AGENTS.md"
    cursor_path = cursor_rules_dir / "architecture.mdc"

    claude_path.write_text(claude_md, encoding="utf-8")
    agents_path.write_text(agents_md, encoding="utf-8")
    cursor_path.write_text(cursor_mdc, encoding="utf-8")

    written_files = [
        str(claude_path),
        str(agents_path),
        str(cursor_path),
    ]

    return {
        "repo_name": repo.repo_name,
        "root_path": str(root),
        "output_dir": str(target_dir),
        "written_files": written_files,
        "files": {
            "CLAUDE.md": str(claude_path),
            "AGENTS.md": str(agents_path),
            ".cursor/rules/architecture.mdc": str(cursor_path),
        },
        "hotspots_count": len(norm_hotspots),
        "cycles_count": len(norm_cycles),
        "hotspots": [h.to_dict() for h in norm_hotspots],
        "cycles": norm_cycles,
        "contents": {
            "CLAUDE.md": claude_md,
            "AGENTS.md": agents_md,
            ".cursor/rules/architecture.mdc": cursor_mdc,
        },
    }


class RulesGenerator:
    """Object-oriented facade for compiling repository-specific AI context rules."""

    def __init__(self, root_path: Union[str, Path] = ".", budget_tokens: int = 32_000) -> None:
        self.root_path = Path(root_path).resolve()
        self.budget_tokens = budget_tokens

    def compile(
        self,
        analysis: Optional[RepoAnalysis] = None,
        cycles: Any = None,
        hotspots: Any = None,
        output_dir: Optional[Union[str, Path]] = None,
        write: bool = True,
    ) -> Dict[str, Any]:
        repo = _ensure_analysis(
            analysis if analysis is not None else self.root_path,
            budget_tokens=self.budget_tokens,
        )
        norm_cycles = _normalize_cycles(repo, cycles)
        norm_hotspots = _normalize_hotspots(repo, hotspots, limit=15)

        if write:
            return write_all_rules(
                root_path=self.root_path,
                analysis=repo,
                cycles=norm_cycles,
                hotspots=norm_hotspots,
                output_dir=output_dir,
            )

        return {
            "repo_name": repo.repo_name,
            "root_path": str(self.root_path),
            "written_files": [],
            "hotspots_count": len(norm_hotspots),
            "cycles_count": len(norm_cycles),
            "hotspots": [h.to_dict() for h in norm_hotspots],
            "cycles": norm_cycles,
            "contents": {
                "CLAUDE.md": generate_claude_md(repo, norm_cycles, norm_hotspots),
                "AGENTS.md": generate_agents_md(repo, norm_cycles, norm_hotspots),
                ".cursor/rules/architecture.mdc": generate_cursor_mdc(repo, norm_cycles, norm_hotspots),
            },
        }


__all__ = [
    "HotspotRecord",
    "RulesGenerator",
    "detect_cycles_from_analysis",
    "generate_claude_md",
    "generate_agents_md",
    "generate_cursor_mdc",
    "write_all_rules",
]
