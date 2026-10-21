from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from . import __version__
from .engine import ContextCompiler, PolyglotSkeletonizer, SecretGuard, TokenEstimator
from .exporters import PayloadExporter
from .graph import run_forensics_report
from .parsers import extract_file_symbols
from .rules_generator import RulesGenerator
from .trace_analyzer import analyze_trace, format_trace_report


class CtxRayMCPServer:
    """
    Zero-dependency Model Context Protocol (MCP) JSON-RPC 2.0 Server over stdio.
    Plugs directly into Claude Desktop, Claude Code, Cursor, Windsurf, and Codex.
    """

    TOOLS = [
        {
            "name": "ctxray_repo_map",
            "description": (
                "Compute the Dependency PageRank architectural map and token distribution "
                "of a repository within a target token budget."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Repository root path (default '.')"},
                    "budget_tokens": {"type": "integer", "description": "Target token ceiling (default 32000)"},
                },
            },
        },
        {
            "name": "ctxray_blast_radius",
            "description": (
                "Analyze the upstream and downstream dependency blast radius of modifying a specific file or module."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Repository root path (default '.')"},
                    "target": {"type": "string", "description": "File path or module substring to inspect"},
                },
                "required": ["target"],
            },
        },
        {
            "name": "ctxray_skeletonize",
            "description": (
                "Compress a source file into an AST signature skeleton (preserving types, interfaces, "
                "signatures, and docstrings while folding function bodies)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Path to the source code file"},
                },
                "required": ["file_path"],
            },
        },
        {
            "name": "ctxray_forensics",
            "description": (
                "Run Tarjan SCC circular dependency detection, architectural layer violation checks, "
                "Git churn hotspot analysis, and Mermaid graph compilation on a repository."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Repository root path (default '.')"},
                },
            },
        },
        {
            "name": "ctxray_init_rules",
            "description": (
                "Auto-generate repository-specific CLAUDE.md, AGENTS.md, and .cursor/rules/architecture.mdc "
                "based on live Dependency PageRank hotspots and circular dependency diagnostics."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Repository root path (default '.')"},
                    "write": {"type": "boolean", "description": "Write files to disk (default true)"},
                },
            },
        },
        {
            "name": "ctxray_trace",
            "description": (
                "Analyze AI coding agent session JSONL logs (Claude Code, Codex, Cursor) to pinpoint "
                "context bloat offenders, prompt-cache breaks, and token/USD savings."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "trace_path": {"type": "string", "description": "Optional path to session trace file"},
                    "demo": {"type": "boolean", "description": "Run on built-in benchmark session trace"},
                },
            },
        },
        {
            "name": "ctxray_pack",
            "description": (
                "Compile a repository into a cache-pinned, secret-redacted LLM context bundle (xml or md)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Repository root path (default '.')"},
                    "budget_tokens": {"type": "integer", "description": "Target token budget (default 32000)"},
                    "format": {"type": "string", "enum": ["xml", "md", "json"], "description": "Output format"},
                },
            },
        },
    ]

    def handle_request(self, req: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        method = req.get("method", "")
        req_id = req.get("id")
        params = req.get("params") or {}

        if method == "notifications/initialized":
            return None

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "ctxray-mcp", "version": __version__},
                },
            }

        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": self.TOOLS},
            }

        if method == "tools/call":
            name = params.get("name", "")
            args = params.get("arguments") or {}
            try:
                text_out = self._dispatch_tool(name, args)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": text_out}],
                        "isError": False,
                    },
                }
            except Exception as exc:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": f"ctxray error: {exc}"}],
                        "isError": True,
                    },
                }

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }

    def _dispatch_tool(self, name: str, args: Dict[str, Any]) -> str:
        if name == "ctxray_repo_map":
            root = args.get("path", ".")
            budget = int(args.get("budget_tokens", 32_000))
            compiler = ContextCompiler(root, budget_tokens=budget)
            analysis = compiler.scan_and_compile()
            lines = [
                f"Repository: {analysis.repo_name} ({analysis.total_files} files)",
                f"Tokens: {analysis.raw_total_tokens:,} raw -> {analysis.compiled_total_tokens:,} compiled (-{analysis.savings_pct}%)",
                f"Prefix Cache Hit Est: {analysis.estimated_cache_hit_pct}% | Secrets Redacted: {analysis.secrets_redacted}",
                "",
                "Top Architectural Nodes (by Dependency PageRank):",
            ]
            for f in analysis.files[:40]:
                lines.append(
                    f"  [{f.tier:8s}] PR={f.pagerank:.3f} | {f.allocated_tokens:5d}/{f.raw_tokens:5d} tok | "
                    f"{f.rel_path} (dependents={f.in_degree}, imports={f.out_degree})"
                )
            return "\n".join(lines)

        if name == "ctxray_blast_radius":
            root = args.get("path", ".")
            target = str(args.get("target", ""))
            compiler = ContextCompiler(root)
            return json.dumps(compiler.blast_radius(target), indent=2, ensure_ascii=False)

        if name == "ctxray_skeletonize":
            fpath = Path(str(args.get("file_path", ""))).resolve()
            raw = fpath.read_text(encoding="utf-8", errors="ignore")
            clean, redacted = SecretGuard.redact(raw)
            skel = PolyglotSkeletonizer.skeletonize(clean, fpath.suffix)
            raw_tok = TokenEstimator.estimate(clean)
            skel_tok = TokenEstimator.estimate(skel)
            saved = round((1.0 - skel_tok / max(1, raw_tok)) * 100.0, 1)
            header = (
                f"# ctxray AST Skeleton: {fpath.name}\n"
                f"# Tokens: {raw_tok} -> {skel_tok} (-{saved}%) | Secrets Redacted: {redacted}\n\n"
            )
            return header + skel

        if name == "ctxray_forensics":
            root = args.get("path", ".")
            compiler = ContextCompiler(root)
            analysis = compiler.scan_and_compile()
            report = run_forensics_report(root, analysis)
            return json.dumps(report.to_dict(), indent=2, ensure_ascii=False)

        if name == "ctxray_init_rules":
            root = args.get("path", ".")
            write_flag = bool(args.get("write", True))
            gen = RulesGenerator(root)
            res = gen.compile(write=write_flag)
            return json.dumps(
                {
                    "repo_name": res.get("repo_name"),
                    "written_files": res.get("written_files"),
                    "hotspots_count": res.get("hotspots_count"),
                    "cycles_count": res.get("cycles_count"),
                },
                indent=2,
                ensure_ascii=False,
            )

        if name == "ctxray_trace":
            tpath = args.get("trace_path")
            demo = bool(args.get("demo", not bool(tpath)))
            rep = analyze_trace(trace_path=tpath, demo=demo)
            return format_trace_report(rep, fmt="text")

        if name == "ctxray_pack":
            root = args.get("path", ".")
            budget = int(args.get("budget_tokens", 32_000))
            fmt = str(args.get("format", "xml"))
            compiler = ContextCompiler(root, budget_tokens=budget)
            analysis = compiler.scan_and_compile()
            return compiler.format_bundle(analysis, fmt=fmt)

        raise ValueError(f"Unknown tool: {name}")

    def serve_stdio(self) -> None:
        for raw_line in sys.stdin:
            line = raw_line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
            except json.JSONDecodeError:
                continue
            resp = self.handle_request(req)
            if resp is not None:
                sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
                sys.stdout.flush()
