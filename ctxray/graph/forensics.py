from __future__ import annotations

import math
import re
import subprocess
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple


# =====================================================================
# ARCHITECTURAL LAYER DEFINITIONS & HIERARCHY
# =====================================================================
# Rank hierarchy from lowest/innermost (1 = foundational domain models)
# to highest/outermost (6 = test suites).
# In a clean layered architecture, higher-numbered layers may depend on
# lower-numbered layers, whereas dependencies from lower-numbered layers
# upward to higher-numbered layers constitute architectural violations.
LAYER_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "domain/models": {
        "rank": 1,
        "title": "Domain & Schemas",
        "description": "Core domain entities, data models, schemas, types, protocols, and contracts.",
        "color_fill": "#1e1b4b",
        "color_stroke": "#818cf8",
    },
    "infra/db": {
        "rank": 2,
        "title": "Infrastructure & Persistence",
        "description": "Database adapters, repositories, migrations, storage, caching, and external clients.",
        "color_fill": "#042f2e",
        "color_stroke": "#2dd4bf",
    },
    "core/services": {
        "rank": 3,
        "title": "Core Engine & Services",
        "description": "Application business logic, compilers, parsers, graph algorithms, and use-case services.",
        "color_fill": "#0f172a",
        "color_stroke": "#38bdf8",
    },
    "api/routers/controllers": {
        "rank": 4,
        "title": "API, CLI & Transport",
        "description": "HTTP routers, REST/GraphQL/gRPC controllers, MCP servers, CLI entrypoints, and middleware.",
        "color_fill": "#1f2937",
        "color_stroke": "#fbbf24",
    },
    "ui/components": {
        "rank": 5,
        "title": "UI & Presentation",
        "description": "Frontend components, interactive studio views, hooks, pages, and visual assets.",
        "color_fill": "#3b0764",
        "color_stroke": "#e879f9",
    },
    "tests": {
        "rank": 6,
        "title": "Tests & Verification",
        "description": "Unit, integration, end-to-end tests, fixtures, benchmarks, and example scripts.",
        "color_fill": "#14532d",
        "color_stroke": "#4ade80",
    },
}


# =====================================================================
# DATA MODELS
# =====================================================================


@dataclass
class CycleReport:
    """Represents a strongly connected circular dependency component discovered by Tarjan's algorithm."""
    cycle_id: str
    nodes: List[str]
    cycle_chain: List[str]
    edges_in_cycle: List[Tuple[str, str]]
    severity: str
    severity_score: float
    suggested_edge_to_break: Tuple[str, str]
    breaking_rationale: str
    def to_dict(self) -> Dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "size": len(self.nodes),
            "nodes": self.nodes,
            "cycle_chain": self.cycle_chain,
            "cycle_display": " -> ".join(self.cycle_chain),
            "edges_in_cycle": [{"source": u, "target": v} for u, v in self.edges_in_cycle],
            "severity": self.severity,
            "severity_score": round(self.severity_score, 3),
            "suggested_edge_to_break": {
                "source": self.suggested_edge_to_break[0],
                "target": self.suggested_edge_to_break[1],
            },
            "breaking_rationale": self.breaking_rationale,
        }


@dataclass
class LayerClassification:
    """Represents the assigned architectural layer for a repository file."""
    rel_path: str
    layer: str
    rank: int
    confidence: float
    matched_signals: List[str] = field(default_factory=list)
    def to_dict(self) -> Dict[str, Any]:
        return {
            "rel_path": self.rel_path,
            "layer": self.layer,
            "rank": self.rank,
            "title": LAYER_DEFINITIONS.get(self.layer, {}).get("title", self.layer),
            "confidence": round(self.confidence, 2),
            "matched_signals": self.matched_signals,
        }


@dataclass
class LayerViolation:
    """Represents an upward or forbidden dependency between two architectural layers."""
    source: str
    target: str
    source_layer: str
    target_layer: str
    source_rank: int
    target_rank: int
    violation_type: str
    severity: str
    explanation: str
    remediation: str
    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "source_layer": self.source_layer,
            "target_layer": self.target_layer,
            "source_rank": self.source_rank,
            "target_rank": self.target_rank,
            "violation_type": self.violation_type,
            "severity": self.severity,
            "explanation": self.explanation,
            "remediation": self.remediation,
        }


@dataclass
class FileHotspot:
    """Represents a file's Git churn, PageRank centrality, and combined Risk Gravity Score."""
    rel_path: str
    churn_commits: int
    pagerank: float
    risk_gravity_score: float
    normalized_risk_score: float
    risk_tier: str
    in_degree: int = 0
    out_degree: int = 0
    layer: str = "core/services"
    def to_dict(self) -> Dict[str, Any]:
        return {
            "rel_path": self.rel_path,
            "churn_commits": self.churn_commits,
            "pagerank": round(self.pagerank, 5),
            "risk_gravity_score": round(self.risk_gravity_score, 5),
            "normalized_risk_score": round(self.normalized_risk_score, 1),
            "risk_tier": self.risk_tier,
            "in_degree": self.in_degree,
            "out_degree": self.out_degree,
            "layer": self.layer,
        }


@dataclass
class CoChangePair:
    """Represents two files that frequently change together across Git commits."""
    file_a: str
    file_b: str
    co_change_commits: int
    jaccard_coupling: float
    has_direct_import: bool
    coupling_kind: str
    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_a": self.file_a,
            "file_b": self.file_b,
            "co_change_commits": self.co_change_commits,
            "jaccard_coupling": round(self.jaccard_coupling, 3),
            "has_direct_import": self.has_direct_import,
            "coupling_kind": self.coupling_kind,
        }


@dataclass
class ForensicsReport:
    """Complete architectural graph & git forensics report for a repository."""
    repo_root: str
    architecture_health_score: float
    cycles: List[CycleReport]
    layer_map: Dict[str, LayerClassification]
    layer_violations: List[LayerViolation]
    hotspots: List[FileHotspot]
    co_change_pairs: List[CoChangePair]
    git_commits_analyzed: int
    git_history_mode: str
    mermaid_diagram: str
    def to_dict(self) -> Dict[str, Any]:
        layer_counts: Dict[str, int] = defaultdict(int)
        for lc in self.layer_map.values():
            layer_counts[lc.layer] += 1
        return {
            "repo_root": self.repo_root,
            "architecture_health_score": round(self.architecture_health_score, 1),
            "summary": {
                "total_files": len(self.layer_map),
                "circular_dependency_count": len(self.cycles),
                "layer_violation_count": len(self.layer_violations),
                "critical_hotspot_count": sum(
                    1 for h in self.hotspots if h.risk_tier in {"CRITICAL", "HIGH"}
                ),
                "co_change_pair_count": len(self.co_change_pairs),
                "git_commits_analyzed": self.git_commits_analyzed,
                "git_history_mode": self.git_history_mode,
                "layer_distribution": dict(layer_counts),
            },
            "cycles": [c.to_dict() for c in self.cycles],
            "layer_classifications": {k: v.to_dict() for k, v in self.layer_map.items()},
            "layer_violations": [v.to_dict() for v in self.layer_violations],
            "hotspots": [h.to_dict() for h in self.hotspots],
            "co_change_pairs": [p.to_dict() for p in self.co_change_pairs],
            "mermaid_diagram": self.mermaid_diagram,
        }


# =====================================================================
# INTERNAL NORMALIZATION HELPERS
# =====================================================================


def _normalize_files_and_edges(
    files_or_analysis: Any,
    edges: Optional[Sequence[Tuple[str, str]]] = None,
) -> Tuple[Dict[str, Dict[str, Any]], List[Tuple[str, str]]]:
    """
    Accepts a RepoAnalysis instance, a list of FileNode objects, a list of file dicts,
    or a list of file path strings, and returns normalized node metadata + edge tuples.
    """
    node_meta: Dict[str, Dict[str, Any]] = {}
    edge_list: List[Tuple[str, str]] = []
    if hasattr(files_or_analysis, "files") and hasattr(files_or_analysis, "edges"):
        raw_files = getattr(files_or_analysis, "files", [])
        raw_edges = edges if edges is not None else getattr(files_or_analysis, "edges", [])
    elif isinstance(files_or_analysis, dict):
        # Already a normalized node_meta dictionary
        all_vals = list(files_or_analysis.values())
        if all_vals and isinstance(all_vals[0], dict) and "rel_path" in all_vals[0]:
            node_meta = {k: dict(v) for k, v in files_or_analysis.items()}
            raw_files = []
            raw_edges = list(edges) if edges is not None else []
        else:
            raw_files = [files_or_analysis]
            raw_edges = list(edges) if edges is not None else []
    else:
        raw_files = files_or_analysis or []
        raw_edges = list(edges) if edges is not None else []
    for item in raw_files:
        if hasattr(item, "rel_path"):
            p = item.rel_path
            node_meta[p] = {
                "rel_path": p,
                "pagerank": float(getattr(item, "pagerank", 0.1) or 0.1),
                "in_degree": int(getattr(item, "in_degree", 0) or 0),
                "out_degree": int(getattr(item, "out_degree", 0) or 0),
                "raw_tokens": int(getattr(item, "raw_tokens", 100) or 100),
                "lines": int(getattr(item, "lines", 25) or 25),
                "tier": str(getattr(item, "tier", "FULL") or "FULL"),
                "raw_content": str(getattr(item, "raw_content", "") or ""),
                "imports": list(getattr(item, "imports", []) or []),
            }
            if edges is None and not hasattr(files_or_analysis, "edges"):
                for imp in node_meta[p]["imports"]:
                    raw_edges.append((p, imp))
        elif isinstance(item, dict):
            p = str(item.get("rel_path") or item.get("path") or "")
            if not p:
                continue
            node_meta[p] = {
                "rel_path": p,
                "pagerank": float(item.get("pagerank", 0.1) or 0.1),
                "in_degree": int(item.get("in_degree", 0) or 0),
                "out_degree": int(item.get("out_degree", 0) or 0),
                "raw_tokens": int(item.get("raw_tokens", 100) or 100),
                "lines": int(item.get("lines", 25) or 25),
                "tier": str(item.get("tier", "FULL") or "FULL"),
                "raw_content": str(item.get("raw_content", "") or ""),
                "imports": list(item.get("imports", []) or []),
            }
            if edges is None:
                for imp in node_meta[p]["imports"]:
                    raw_edges.append((p, imp))
        elif isinstance(item, str):
            node_meta[item] = {
                "rel_path": item,
                "pagerank": 0.25,
                "in_degree": 0,
                "out_degree": 0,
                "raw_tokens": 100,
                "lines": 25,
                "tier": "FULL",
                "raw_content": "",
                "imports": [],
            }
    for e in raw_edges:
        if isinstance(e, dict):
            u = str(e.get("source", ""))
            v = str(e.get("target", ""))
        elif isinstance(e, (tuple, list)) and len(e) >= 2:
            u, v = str(e[0]), str(e[1])
        else:
            continue
        if not u or not v:
            continue
        edge_list.append((u, v))
        for endpoint in (u, v):
            if endpoint not in node_meta:
                node_meta[endpoint] = {
                    "rel_path": endpoint,
                    "pagerank": 0.2,
                    "in_degree": 0,
                    "out_degree": 0,
                    "raw_tokens": 100,
                    "lines": 25,
                    "tier": "SKELETON",
                    "raw_content": "",
                    "imports": [],
                }
    # Recompute degrees if missing
    in_deg: Dict[str, int] = defaultdict(int)
    out_deg: Dict[str, int] = defaultdict(int)
    for u, v in edge_list:
        out_deg[u] += 1
        in_deg[v] += 1
    for p, meta in node_meta.items():
        if meta["in_degree"] == 0 and in_deg[p] > 0:
            meta["in_degree"] = in_deg[p]
        if meta["out_degree"] == 0 and out_deg[p] > 0:
            meta["out_degree"] = out_deg[p]
    return node_meta, edge_list


# =====================================================================
# 1. TARJAN'S STRONGLY CONNECTED COMPONENTS (SCC) CYCLE DETECTOR
# =====================================================================


def detect_cycles(
    files_or_analysis: Any,
    edges: Optional[Sequence[Tuple[str, str]]] = None,
    layer_map: Optional[Dict[str, LayerClassification]] = None,
) -> List[CycleReport]:
    """
    Runs Tarjan's Strongly Connected Components (SCC) algorithm in O(V + E) time
    across the repository import graph to discover all circular dependency chains,
    reconstruct explicit cycle paths (A -> B -> C -> A), score their architectural
    severity, and recommend the optimal edge to break.
    """
    node_meta, edge_list = _normalize_files_and_edges(files_or_analysis, edges)
    if layer_map is None:
        layer_map = classify_layers(node_meta)
    adj: Dict[str, List[str]] = defaultdict(list)
    self_loops: Set[str] = set()
    for u, v in edge_list:
        if u == v:
            self_loops.add(u)
        elif v not in adj[u]:
            adj[u].append(v)
    for u in adj:
        adj[u].sort()
    index_counter = 0
    indices: Dict[str, int] = {}
    lowlink: Dict[str, int] = {}
    stack: List[str] = []
    on_stack: Set[str] = set()
    sccs: List[List[str]] = []
    for start_node in sorted(node_meta.keys()):
        if start_node in indices:
            continue
        indices[start_node] = index_counter
        lowlink[start_node] = index_counter
        index_counter += 1
        stack.append(start_node)
        on_stack.add(start_node)
        call_stack: List[Tuple[str, List[str], int]] = [
            (start_node, adj.get(start_node, []), 0)
        ]
        while call_stack:
            node, neighbors, ptr = call_stack[-1]
            if ptr < len(neighbors):
                neighbor = neighbors[ptr]
                call_stack[-1] = (node, neighbors, ptr + 1)
                if neighbor not in indices:
                    indices[neighbor] = index_counter
                    lowlink[neighbor] = index_counter
                    index_counter += 1
                    stack.append(neighbor)
                    on_stack.add(neighbor)
                    call_stack.append((neighbor, adj.get(neighbor, []), 0))
                elif neighbor in on_stack:
                    lowlink[node] = min(lowlink[node], indices[neighbor])
            else:
                call_stack.pop()
                if call_stack:
                    parent = call_stack[-1][0]
                    lowlink[parent] = min(lowlink[parent], lowlink[node])
                if lowlink[node] == indices[node]:
                    component: List[str] = []
                    while True:
                        w = stack.pop()
                        on_stack.remove(w)
                        component.append(w)
                        if w == node:
                            break
                    if len(component) > 1 or (len(component) == 1 and component[0] in self_loops):
                        component.reverse()
                        sccs.append(component)
    reports: List[CycleReport] = []
    for idx, comp in enumerate(sccs, start=1):
        comp_set = set(comp)
        comp_edges: List[Tuple[str, str]] = []
        for u in comp:
            if u in self_loops:
                comp_edges.append((u, u))
            for v in adj.get(u, []):
                if v in comp_set:
                    comp_edges.append((u, v))
        cycle_chain = _reconstruct_cycle_chain(comp, adj, comp_set)
        avg_pr = sum(node_meta.get(n, {}).get("pagerank", 0.2) for n in comp) / max(1, len(comp))
        max_pr = max((node_meta.get(n, {}).get("pagerank", 0.2) for n in comp), default=0.2)
        severity_score = round(
            (len(comp) * 1.6) + (max_pr * 4.5) + (avg_pr * 2.5) + (len(comp_edges) * 0.4), 3
        )
        if severity_score >= 7.5 or len(comp) >= 4 or max_pr >= 0.8:
            severity = "CRITICAL"
        elif severity_score >= 5.0 or len(comp) == 3 or max_pr >= 0.5:
            severity = "HIGH"
        elif severity_score >= 3.0:
            severity = "MODERATE"
        else:
            severity = "LOW"
        best_edge, rationale = _select_edge_to_break(comp_edges, node_meta, layer_map)
        reports.append(
            CycleReport(
                cycle_id=f"SCC-{idx:02d}",
                nodes=sorted(comp),
                cycle_chain=cycle_chain,
                edges_in_cycle=comp_edges,
                severity=severity,
                severity_score=severity_score,
                suggested_edge_to_break=best_edge,
                breaking_rationale=rationale,
            )
        )
    reports.sort(key=lambda r: r.severity_score, reverse=True)
    return reports


def _reconstruct_cycle_chain(
    comp: List[str], adj: Dict[str, List[str]], comp_set: Set[str]
) -> List[str]:
    """Finds a representative elementary cycle path A -> B -> ... -> A inside an SCC."""
    if len(comp) == 1:
        return [comp[0], comp[0]]
    start = sorted(comp)[0]
    visited: Set[str] = {start}
    parent_map: Dict[str, str] = {}
    queue: List[str] = [start]
    while queue:
        curr = queue.pop(0)
        for nxt in adj.get(curr, []):
            if nxt not in comp_set:
                continue
            if nxt == start and curr != start:
                rev_chain = [start, curr]
                trace_curr = curr
                while trace_curr in parent_map:
                    trace_curr = parent_map[trace_curr]
                    rev_chain.append(trace_curr)
                rev_chain.reverse()
                return rev_chain
            if nxt not in visited:
                visited.add(nxt)
                parent_map[nxt] = curr
                queue.append(nxt)
    ordered = sorted(comp)
    return ordered + [ordered[0]]


def _select_edge_to_break(
    comp_edges: List[Tuple[str, str]],
    node_meta: Dict[str, Dict[str, Any]],
    layer_map: Dict[str, LayerClassification],
) -> Tuple[Tuple[str, str], str]:
    """
    Scores each edge in an SCC to find the most surgical feedback edge to sever:
    1. Prioritizes edges that violate architectural layering (foundational module importing higher layer).
    2. Otherwise picks the edge where a high-PageRank core module imports a lower-PageRank peripheral module.
    """
    if not comp_edges:
        return (("", ""), "No edges in cycle.")
    best_edge = comp_edges[0]
    best_score = -1e9
    best_reason = ""
    for u, v in comp_edges:
        u_layer = layer_map.get(u)
        v_layer = layer_map.get(v)
        u_rank = u_layer.rank if u_layer else 3
        v_rank = v_layer.rank if v_layer else 3
        u_pr = float(node_meta.get(u, {}).get("pagerank", 0.2))
        v_pr = float(node_meta.get(v, {}).get("pagerank", 0.2))
        v_in = int(node_meta.get(v, {}).get("in_degree", 1))
        layer_delta = v_rank - u_rank
        pr_delta = u_pr - v_pr
        score = (layer_delta * 3.0) + (pr_delta * 2.5) - (v_in * 0.15)
        if score > best_score:
            best_score = score
            best_edge = (u, v)
            if layer_delta > 0 and u_layer and v_layer:
                best_reason = (
                    f"Break '{u} -> {v}': '{u}' ({u_layer.layer}) is a lower-level module importing "
                    f"higher-layer '{v}' ({v_layer.layer}). Invert the dependency via a shared interface/protocol "
                    f"or move shared types into 'domain/models'."
                )
            else:
                best_reason = (
                    f"Break '{u} -> {v}': '{u}' (PageRank={u_pr:.3f}) has higher architectural gravity than "
                    f"'{v}' (PageRank={v_pr:.3f}). Extract shared data contracts or use lazy/callback injection "
                    f"so '{u}' does not directly import '{v}'."
                )
    return best_edge, best_reason


# =====================================================================
# 2. ARCHITECTURAL LAYER CLASSIFIER & VIOLATION DETECTOR
# =====================================================================


def classify_layers(
    files_or_analysis: Any,
) -> Dict[str, LayerClassification]:
    """
    Classifies each file in the repository into one of the 6 canonical architectural layers:
    - domain/models (rank 1)
    - infra/db (rank 2)
    - core/services (rank 3)
    - api/routers/controllers (rank 4)
    - ui/components (rank 5)
    - tests (rank 6)
    Uses path segment heuristics, filename conventions, extensions, and source content signals.
    """
    node_meta, _ = _normalize_files_and_edges(files_or_analysis)
    classifications: Dict[str, LayerClassification] = {}
    for rel_path, meta in sorted(node_meta.items()):
        norm = rel_path.replace("\\", "/").lower()
        parts = [p for p in norm.split("/") if p]
        fname = parts[-1] if parts else norm
        stem = Path(fname).stem.lower()
        ext = Path(fname).suffix.lower()
        content = meta.get("raw_content", "")
        signals: List[str] = []
        layer = "core/services"
        confidence = 0.72
        # 1. Tests & Verification (Rank 6)
        if (
            any(
                p in {"test", "tests", "__tests__", "spec", "specs", "fixtures", "benchmarks", "examples", "e2e"}
                for p in parts
            )
            or stem.startswith("test_")
            or stem.endswith(("_test", ".test", ".spec", "_spec"))
            or "bench" in stem
        ):
            layer = "tests"
            confidence = 0.96
            signals.append("test/example path or filename pattern")
        # 2. UI & Presentation (Rank 5)
        elif (
            any(
                p in {"ui", "components", "views", "pages", "studio", "frontend", "web", "widgets", "assets", "styles"}
                for p in parts
            )
            or ext in {".tsx", ".jsx", ".css", ".scss", ".html", ".svg"}
            or bool(re.search(r"\buse(?:State|Effect|Memo|Callback|Ref)\b", content))
        ):
            if "/api/" in norm and (stem in {"route", "index"} or "NextResponse" in content):
                layer = "api/routers/controllers"
                confidence = 0.94
                signals.append("Next.js API route handler")
            else:
                layer = "ui/components"
                confidence = 0.92
                signals.append("UI directory, JSX/HTML/SVG extension, or React hook usage")
        # 3. API, Routers, CLI & Transport (Rank 4)
        elif (
            any(
                p
                in {
                    "api",
                    "apis",
                    "router",
                    "routers",
                    "routes",
                    "controllers",
                    "handlers",
                    "transport",
                    "grpc",
                    "graphql",
                    "cli",
                    "bin",
                    "cmd",
                    "middleware",
                }
                for p in parts
            )
            or any(
                k in stem
                for k in ("router", "controller", "handler", "endpoint", "cli", "mcp_server", "server", "main", "app")
            )
            or bool(re.search(r"@(?:app|router|api_router|bp)\.(?:get|post|put|delete|patch|route|websocket)\b", content))
        ):
            layer = "api/routers/controllers"
            confidence = 0.90
            signals.append("API/router/controller/CLI entrypoint or route decorator")
        # 4. Infrastructure & Persistence (Rank 2)
        elif (
            any(
                p
                in {
                    "infra",
                    "infrastructure",
                    "db",
                    "database",
                    "storage",
                    "repositories",
                    "repository",
                    "persistence",
                    "migrations",
                    "cache",
                    "redis",
                    "adapters",
                    "clients",
                }
                for p in parts
            )
            or any(
                k in stem
                for k in ("repo", "repository", "database", "storage", "migration", "cache", "adapter", "client", "dao")
            )
            or ext == ".sql"
        ):
            layer = "infra/db"
            confidence = 0.89
            signals.append("database/storage/adapter/repository path or SQL schema")
        # 5. Domain & Models (Rank 1)
        elif (
            any(
                p in {"domain", "models", "model", "schemas", "schema", "entities", "types", "contracts", "proto", "dtos"}
                for p in parts
            )
            or any(
                k in stem
                for k in ("model", "models", "schema", "schemas", "entity", "types", "dto", "contract", "protocol")
            )
            or ext in {".proto", ".graphql", ".gql"}
            or (
                bool(re.search(r"\bclass\s+\w+\((?:BaseModel|Protocol|TypedDict|Enum)\)", content))
                and not bool(re.search(r"@(?:app|router)\.", content))
            )
        ):
            layer = "domain/models"
            confidence = 0.91
            signals.append("domain/model/schema/types path, IDL file, or pure schema declarations")
        # 6. Core Engine & Services (Rank 3)
        else:
            layer = "core/services"
            if any(
                p in {"core", "services", "service", "engine", "parsers", "graph", "usecases", "compiler", "lib", "pkg"}
                for p in parts
            ):
                confidence = 0.90
                signals.append("core/service/engine/parser/graph module")
            else:
                confidence = 0.75
                signals.append("default core application module")
        rank = int(LAYER_DEFINITIONS[layer]["rank"])
        classifications[rel_path] = LayerClassification(
            rel_path=rel_path,
            layer=layer,
            rank=rank,
            confidence=confidence,
            matched_signals=signals,
        )
    return classifications


def detect_layer_violations(
    files_or_analysis: Any,
    edges: Optional[Sequence[Tuple[str, str]]] = None,
    layer_map: Optional[Dict[str, LayerClassification]] = None,
) -> List[LayerViolation]:
    """
    Inspects every dependency edge (source -> target) and flags upward or forbidden
    architectural layer dependencies:
    - Any production layer importing tests (CRITICAL)
    - domain/models (rank 1) importing infra/db, core/services, api/routers/controllers, or ui/components
    - infra/db (rank 2) importing api/routers/controllers or ui/components
    - core/services (rank 3) importing api/routers/controllers or ui/components
    """
    node_meta, edge_list = _normalize_files_and_edges(files_or_analysis, edges)
    if layer_map is None:
        layer_map = classify_layers(node_meta)
    violations: List[LayerViolation] = []
    seen: Set[Tuple[str, str]] = set()
    for src, dst in edge_list:
        if src == dst or (src, dst) in seen:
            continue
        src_cls = layer_map.get(src)
        dst_cls = layer_map.get(dst)
        if not src_cls or not dst_cls:
            continue
        s_layer, t_layer = src_cls.layer, dst_cls.layer
        s_rank, t_rank = src_cls.rank, dst_cls.rank
        if s_layer == t_layer:
            continue
        # Rule 1: Production code importing tests
        if s_layer != "tests" and t_layer == "tests":
            seen.add((src, dst))
            violations.append(
                LayerViolation(
                    source=src,
                    target=dst,
                    source_layer=s_layer,
                    target_layer=t_layer,
                    source_rank=s_rank,
                    target_rank=t_rank,
                    violation_type="PROD_IMPORTS_TEST",
                    severity="CRITICAL",
                    explanation=(
                        f"Production module '{src}' ({s_layer}) imports test/verification module '{dst}' ({t_layer})."
                    ),
                    remediation=(
                        f"Move shared helpers or fixtures out of '{dst}' into a core or domain module so production code never depends on test suites."
                    ),
                )
            )
            continue
        # Rule 2: Lower/inner architectural layer importing a higher/outer architectural layer
        is_upward = False
        if s_layer == "domain/models" and t_rank > 1:
            is_upward = True
        elif s_layer in {"infra/db", "core/services"} and t_layer in {"api/routers/controllers", "ui/components"}:
            is_upward = True
        elif s_layer == "api/routers/controllers" and t_layer == "ui/components":
            is_upward = True
        if is_upward:
            seen.add((src, dst))
            rank_gap = t_rank - s_rank
            severity = "CRITICAL" if (s_layer == "domain/models" and t_rank >= 4) or rank_gap >= 3 else "HIGH"
            violations.append(
                LayerViolation(
                    source=src,
                    target=dst,
                    source_layer=s_layer,
                    target_layer=t_layer,
                    source_rank=s_rank,
                    target_rank=t_rank,
                    violation_type="UPWARD_LAYER_DEPENDENCY",
                    severity=severity,
                    explanation=(
                        f"Inner layer '{src}' [{s_layer}, rank {s_rank}] imports outer layer "
                        f"'{dst}' [{t_layer}, rank {t_rank}], inverting the clean dependency direction."
                    ),
                    remediation=(
                        f"Invert the dependency: extract interfaces/types into 'domain/models' or pass callbacks "
                        f"from '{t_layer}' down into '{s_layer}'."
                    ),
                )
            )
    severity_order = {"CRITICAL": 0, "HIGH": 1, "MODERATE": 2, "LOW": 3}
    violations.sort(key=lambda v: (severity_order.get(v.severity, 9), -(v.target_rank - v.source_rank), v.source))
    return violations


# =====================================================================
# 3. GIT CHURN, CO-CHANGE COUPLING & RISK GRAVITY HOTSPOT ANALYZER
# =====================================================================


def analyze_git_hotspots(
    repo_root: str | Path,
    files_or_analysis: Any,
    edges: Optional[Sequence[Tuple[str, str]]] = None,
    layer_map: Optional[Dict[str, LayerClassification]] = None,
    max_commits: int = 250,
) -> Dict[str, Any]:
    """
    Runs git log --name-only --pretty=format:%H across repo_root (with a deterministic
    structural fallback when git history is shallow or unavailable) to compute:
    - File commit frequency (churn)
    - Temporal co-change coupling (pairs of files that change together across commits)
    - Risk Gravity Score: PageRank * log(1 + churn)
    """
    root_path = Path(repo_root).resolve()
    node_meta, edge_list = _normalize_files_and_edges(files_or_analysis, edges)
    if layer_map is None:
        layer_map = classify_layers(node_meta)
    known_paths = set(node_meta.keys())
    direct_edge_pairs: Set[Tuple[str, str]] = set()
    for u, v in edge_list:
        direct_edge_pairs.add((u, v))
        direct_edge_pairs.add((v, u))
    commits: List[List[str]] = []
    git_mode = "git_log"
    try:
        proc = subprocess.run(
            ["git", "log", f"-n{max_commits}", "--name-only", "--pretty=format:__COMMIT__%H"],
            cwd=str(root_path),
            capture_output=True,
            text=True,
            timeout=5.0,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            current_files: List[str] = []
            for raw_line in proc.stdout.splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                if line.startswith("__COMMIT__"):
                    if current_files:
                        commits.append(sorted(set(current_files)))
                        current_files = []
                else:
                    norm_f = line.replace("\\", "/")
                    if not known_paths or norm_f in known_paths:
                        current_files.append(norm_f)
            if current_files:
                commits.append(sorted(set(current_files)))
    except Exception:
        pass
    churn_map: Dict[str, int] = defaultdict(int)
    pair_counts: Dict[Tuple[str, str], int] = defaultdict(int)
    for c_files in commits:
        for f in c_files:
            churn_map[f] += 1
        filtered = c_files[:40]
        n_f = len(filtered)
        for i in range(n_f):
            for j in range(i + 1, n_f):
                a, b = filtered[i], filtered[j]
                pair_key = (a, b) if a < b else (b, a)
                pair_counts[pair_key] += 1
    # Safe fallback if repository has shallow history (<= 2 commits)
    if len(commits) <= 2:
        git_mode = "shallow_git_with_structural_priors" if commits else "structural_fallback"
        for p, meta in node_meta.items():
            base_c = churn_map.get(p, 0)
            lines_n = int(meta.get("lines", 30))
            in_deg = int(meta.get("in_degree", 0))
            out_deg = int(meta.get("out_degree", 0))
            synthetic_churn = max(
                1,
                base_c
                + int(math.ceil(lines_n / 85.0))
                + (in_deg * 2)
                + out_deg,
            )
            churn_map[p] = synthetic_churn
        for u, v in edge_list:
            if u == v:
                continue
            pair_key = (u, v) if u < v else (v, u)
            shared_weight = max(2, min(churn_map.get(u, 2), churn_map.get(v, 2)) // 2)
            pair_counts[pair_key] = max(pair_counts.get(pair_key, 0), shared_weight)
    hotspots: List[FileHotspot] = []
    max_raw_gravity = 1e-6
    raw_items: List[Tuple[str, int, float, float]] = []
    for p, meta in node_meta.items():
        churn = max(1, churn_map.get(p, 1))
        pr = max(0.01, float(meta.get("pagerank", 0.1)))
        # Risk Gravity Formula: PageRank * log(1 + churn)
        gravity = pr * math.log(1.0 + churn)
        if gravity > max_raw_gravity:
            max_raw_gravity = gravity
        raw_items.append((p, churn, pr, gravity))
    for p, churn, pr, gravity in raw_items:
        norm_score = round((gravity / max_raw_gravity) * 100.0, 1) if max_raw_gravity > 0 else 0.0
        if norm_score >= 75.0 or (pr >= 0.75 and churn >= 5):
            tier = "CRITICAL"
        elif norm_score >= 48.0 or (pr >= 0.45 and churn >= 3):
            tier = "HIGH"
        elif norm_score >= 22.0:
            tier = "MODERATE"
        else:
            tier = "LOW"
        meta = node_meta[p]
        layer_name = layer_map[p].layer if p in layer_map else "core/services"
        hotspots.append(
            FileHotspot(
                rel_path=p,
                churn_commits=churn,
                pagerank=pr,
                risk_gravity_score=round(gravity, 5),
                normalized_risk_score=norm_score,
                risk_tier=tier,
                in_degree=int(meta.get("in_degree", 0)),
                out_degree=int(meta.get("out_degree", 0)),
                layer=layer_name,
            )
        )
    hotspots.sort(key=lambda h: (h.risk_gravity_score, h.pagerank, h.churn_commits), reverse=True)
    co_change_list: List[CoChangePair] = []
    for (file_a, file_b), count in pair_counts.items():
        if count < 1:
            continue
        ca = max(1, churn_map.get(file_a, count))
        cb = max(1, churn_map.get(file_b, count))
        denom = max(1, ca + cb - count)
        jaccard = min(1.0, count / denom)
        has_imp = (file_a, file_b) in direct_edge_pairs
        coupling_kind = "explicit_import_cochange" if has_imp else "hidden_temporal_coupling"
        co_change_list.append(
            CoChangePair(
                file_a=file_a,
                file_b=file_b,
                co_change_commits=count,
                jaccard_coupling=round(jaccard, 3),
                has_direct_import=has_imp,
                coupling_kind=coupling_kind,
            )
        )
    co_change_list.sort(
        key=lambda c: (not c.has_direct_import, c.co_change_commits, c.jaccard_coupling),
        reverse=True,
    )
    return {
        "git_commits_analyzed": len(commits),
        "git_history_mode": git_mode,
        "hotspots": hotspots,
        "co_change_pairs": co_change_list[:35],
    }


# =====================================================================
# 4. MERMAID ARCHITECTURE DIAGRAM COMPILER
# =====================================================================


def compile_mermaid_graph(
    files_or_analysis: Any,
    edges: Optional[Sequence[Tuple[str, str]]] = None,
    layer_map: Optional[Dict[str, LayerClassification]] = None,
    cycles: Optional[Sequence[CycleReport]] = None,
    violations: Optional[Sequence[LayerViolation]] = None,
    max_nodes: int = 36,
) -> str:
    """
    Compiles a clean, color-coded flowchart TD Mermaid architecture diagram:
    - Groups repository files into subgraphs by architectural layer
    - Highlights top PageRank hotspots with distinct gold/amber borders
    - Marks circular dependency edges in dashed bold red (-. cycle .-> + red linkStyle)
    - Marks upward layer violation edges in bold orange/red (== violation ==>)
    """
    node_meta, edge_list = _normalize_files_and_edges(files_or_analysis, edges)
    if layer_map is None:
        layer_map = classify_layers(node_meta)
    if cycles is None:
        cycles = detect_cycles(node_meta, edge_list, layer_map=layer_map)
    if violations is None:
        violations = detect_layer_violations(node_meta, edge_list, layer_map=layer_map)
    cycle_edges: Set[Tuple[str, str]] = set()
    cycle_nodes: Set[str] = set()
    for c in cycles:
        cycle_nodes.update(c.nodes)
        for u, v in c.edges_in_cycle:
            cycle_edges.add((u, v))
    violation_edges: Set[Tuple[str, str]] = {(v.source, v.target) for v in violations}
    priority_nodes = cycle_nodes | {u for u, _ in violation_edges} | {v for _, v in violation_edges}
    sorted_paths = sorted(
        node_meta.keys(),
        key=lambda p: (p in priority_nodes, node_meta[p].get("pagerank", 0.0)),
        reverse=True,
    )[:max_nodes]
    selected_set = set(sorted_paths)
    pr_sorted = sorted(
        selected_set, key=lambda p: float(node_meta[p].get("pagerank", 0.0)), reverse=True
    )
    hotspot_cutoff = max(1, len(pr_sorted) // 4)
    hotspot_nodes: Set[str] = {
        p
        for idx, p in enumerate(pr_sorted)
        if idx < hotspot_cutoff or float(node_meta[p].get("pagerank", 0.0)) >= 0.65
    }
    node_ids: Dict[str, str] = {}
    for idx, p in enumerate(sorted(selected_set), start=1):
        safe = re.sub(r"[^A-Za-z0-9_]", "_", p)
        node_ids[p] = f"N{idx}_{safe[:28]}"
    display_layer_order = [
        "ui/components",
        "api/routers/controllers",
        "core/services",
        "infra/db",
        "domain/models",
        "tests",
    ]
    by_layer: Dict[str, List[str]] = defaultdict(list)
    for p in sorted(selected_set):
        layer_name = layer_map[p].layer if p in layer_map else "core/services"
        by_layer[layer_name].append(p)
    lines: List[str] = [
        "flowchart TD",
        "  %% ctxray Architectural X-Ray Diagram — Layered PageRank & Cycle Forensics",
        "  classDef default fill:#0f172a,stroke:#334155,stroke-width:1.5px,color:#e2e8f0;",
        "  classDef hotspot fill:#451a03,stroke:#f59e0b,stroke-width:2.5px,color:#fef3c7;",
        "  classDef cycleNode fill:#450a0a,stroke:#ef4444,stroke-width:2.5px,color:#fecaca;",
        "  classDef domainNode fill:#1e1b4b,stroke:#818cf8,stroke-width:1.5px,color:#e0e7ff;",
        "  classDef apiNode fill:#1f2937,stroke:#38bdf8,stroke-width:1.5px,color:#e0f2fe;",
    ]
    for layer_key in display_layer_order:
        layer_files = by_layer.get(layer_key, [])
        if not layer_files:
            continue
        layer_info = LAYER_DEFINITIONS.get(layer_key, {})
        sub_id = "LAYER_" + re.sub(r"[^A-Za-z0-9_]", "_", layer_key.upper())
        sub_title = layer_info.get("title", layer_key)
        lines.append(f'  subgraph {sub_id}["{sub_title} ({layer_key})"]')
        for p in layer_files:
            nid = node_ids[p]
            pr = float(node_meta[p].get("pagerank", 0.0))
            badge = "HOTSPOT " if p in hotspot_nodes else ("CYCLE " if p in cycle_nodes else "")
            label = f"{badge}{p}\\nPR: {pr:.2f}"
            lines.append(f'    {nid}["{label}"]')
        lines.append("  end")
    red_edge_indices: List[int] = []
    orange_edge_indices: List[int] = []
    edge_idx = 0
    for u, v in edge_list:
        if u not in selected_set or v not in selected_set:
            continue
        uid, vid = node_ids[u], node_ids[v]
        if (u, v) in cycle_edges:
            lines.append(f"  {uid} -. cycle .-> {vid}")
            red_edge_indices.append(edge_idx)
            edge_idx += 1
        elif (u, v) in violation_edges:
            lines.append(f"  {uid} == violation ==> {vid}")
            orange_edge_indices.append(edge_idx)
            edge_idx += 1
        else:
            lines.append(f"  {uid} --> {vid}")
            edge_idx += 1
    for p in sorted(selected_set):
        nid = node_ids[p]
        if p in cycle_nodes:
            lines.append(f"  class {nid} cycleNode;")
        elif p in hotspot_nodes:
            lines.append(f"  class {nid} hotspot;")
        elif layer_map.get(p) and layer_map[p].layer == "domain/models":
            lines.append(f"  class {nid} domainNode;")
        elif layer_map.get(p) and layer_map[p].layer == "api/routers/controllers":
            lines.append(f"  class {nid} apiNode;")
    for r_idx in red_edge_indices:
        lines.append(f"  linkStyle {r_idx} stroke:#ef4444,stroke-width:3px,color:#fca5a5;")
    for o_idx in orange_edge_indices:
        lines.append(f"  linkStyle {o_idx} stroke:#f97316,stroke-width:2.5px,color:#fdba74;")
    return "\n".join(lines)


# =====================================================================
# 5. UNIFIED ARCHITECTURAL FORENSICS ENGINE
# =====================================================================


class ArchitecturalForensicsEngine:
    """
    High-level engine that combines Tarjan's SCC cycle detection, architectural layer
    classification, upward dependency violation checks, Git churn & co-change coupling
    analysis, and Mermaid flowchart generation into a single diagnostic suite.
    """
    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
    def analyze(
        self,
        files_or_analysis: Any,
        edges: Optional[Sequence[Tuple[str, str]]] = None,
        max_commits: int = 250,
    ) -> ForensicsReport:
        node_meta, edge_list = _normalize_files_and_edges(files_or_analysis, edges)
        layer_map = classify_layers(node_meta)
        cycles = detect_cycles(node_meta, edge_list, layer_map=layer_map)
        violations = detect_layer_violations(node_meta, edge_list, layer_map=layer_map)
        git_data = analyze_git_hotspots(
            repo_root=self.repo_root,
            files_or_analysis=node_meta,
            edges=edge_list,
            layer_map=layer_map,
            max_commits=max_commits,
        )
        mermaid = compile_mermaid_graph(
            files_or_analysis=node_meta,
            edges=edge_list,
            layer_map=layer_map,
            cycles=cycles,
            violations=violations,
        )
        penalty = (len(cycles) * 12.0) + (len(violations) * 6.5)
        health_score = max(15.0, min(100.0, round(100.0 - penalty, 1)))
        return ForensicsReport(
            repo_root=str(self.repo_root),
            architecture_health_score=health_score,
            cycles=cycles,
            layer_map=layer_map,
            layer_violations=violations,
            hotspots=git_data["hotspots"],
            co_change_pairs=git_data["co_change_pairs"],
            git_commits_analyzed=git_data["git_commits_analyzed"],
            git_history_mode=git_data["git_history_mode"],
            mermaid_diagram=mermaid,
        )


def run_forensics_report(
    repo_root: str | Path,
    files_or_analysis: Any,
    edges: Optional[Sequence[Tuple[str, str]]] = None,
) -> ForensicsReport:
    """Convenience entrypoint to run the full architectural graph & git forensics suite."""
    engine = ArchitecturalForensicsEngine(repo_root=repo_root)
    return engine.analyze(files_or_analysis=files_or_analysis, edges=edges)
