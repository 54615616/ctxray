from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from pathlib import Path
from typing import List, Optional

from . import __version__
from .engine import ContextCompiler, PolyglotSkeletonizer, SecretGuard, TokenEstimator
from .exporters import PayloadExporter
from .graph import run_forensics_report
from .mcp_server import CtxRayMCPServer
from .parsers import extract_file_symbols
from .rules_generator import RulesGenerator
from .server import run_studio_server
from .trace_analyzer import analyze_trace, format_trace_report


def _parse_budget(val: str) -> int:
    s = val.strip().lower().replace(",", "")
    if s.endswith("k"):
        return int(float(s[:-1]) * 1000)
    if s.endswith("m"):
        return int(float(s[:-1]) * 1_000_000)
    return int(s)


def _bar(ratio: float, width: int = 18) -> str:
    filled = max(0, min(width, int(round(ratio * width))))
    return "#" * filled + "-" * (width - filled)


def cmd_scan(args: argparse.Namespace) -> int:
    budget = _parse_budget(args.budget)
    compiler = ContextCompiler(args.path, budget_tokens=budget)
    analysis = compiler.scan_and_compile()
    bundle = compiler.format_bundle(analysis, fmt=args.format)

    if args.output:
        out_path = Path(args.output)
        out_path.write_text(bundle, encoding="utf-8")
        print(
            f"[ctxray] Compiled {analysis.total_files} files: "
            f"{analysis.raw_total_tokens:,} -> {analysis.compiled_total_tokens:,} tokens "
            f"(-{analysis.savings_pct}%) | Cache Hit Est: {analysis.estimated_cache_hit_pct}% "
            f"-> saved to {out_path}",
            file=sys.stderr,
        )
    else:
        sys.stdout.write(bundle + "\n")
    return 0


def cmd_rank(args: argparse.Namespace) -> int:
    budget = _parse_budget(args.budget)
    compiler = ContextCompiler(args.path, budget_tokens=budget)
    analysis = compiler.scan_and_compile()

    print("=" * 86)
    print(
        f" CTXRAY ARCHITECTURAL X-RAY  |  Repo: {analysis.repo_name}  |  Files: {analysis.total_files}"
    )
    print(
        f" Raw Tokens: {analysis.raw_total_tokens:,}  ->  Compiled: {analysis.compiled_total_tokens:,} "
        f"(-{analysis.savings_pct}%)  |  Budget: {analysis.budget_tokens:,}"
    )
    print(
        f" Tiers: FULL={analysis.tier_counts['FULL']}  SKELETON={analysis.tier_counts['SKELETON']}  "
        f"SUMMARY={analysis.tier_counts['SUMMARY']}  |  Prefix Cache Hit Est: {analysis.estimated_cache_hit_pct}%"
    )
    print("=" * 86)
    print(f"{'TIER':<10} {'PAGERANK':<24} {'TOKENS (COMP/RAW)':<20} {'IN/OUT':<8} {'FILE PATH'}")
    print("-" * 86)

    for f in analysis.files[: args.top]:
        pr_bar = _bar(f.pagerank, 12)
        tok_str = f"{f.allocated_tokens:>5}/{f.raw_tokens:<5}"
        deg_str = f"{f.in_degree:>2}/{f.out_degree:<2}"
        print(
            f"[{f.tier:<8}] {pr_bar} {f.pagerank:0.3f}   {tok_str:<20} {deg_str:<8} {f.rel_path}"
        )
    print("=" * 86)
    return 0


def cmd_blast(args: argparse.Namespace) -> int:
    compiler = ContextCompiler(args.path)
    report = compiler.blast_radius(args.target)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def cmd_skeleton(args: argparse.Namespace) -> int:
    fpath = Path(args.file).resolve()
    if not fpath.is_file():
        print(f"Error: file not found: {fpath}", file=sys.stderr)
        return 1
    raw = fpath.read_text(encoding="utf-8", errors="ignore")
    clean, redacted = SecretGuard.redact(raw)
    skel = PolyglotSkeletonizer.skeletonize(clean, fpath.suffix)
    raw_tok = TokenEstimator.estimate(clean)
    skel_tok = TokenEstimator.estimate(skel)
    saved = round((1.0 - skel_tok / max(1, raw_tok)) * 100.0, 1)
    print(
        f"# [ctxray skeleton] {fpath.name} | {raw_tok} -> {skel_tok} tokens (-{saved}%) | secrets redacted: {redacted}"
    )
    print(skel)
    if getattr(args, "symbols", False):
        deep = extract_file_symbols(fpath, content=clean)
        print("\n# [ctxray deep symbols & routes]")
        print(json.dumps(deep.to_dict(), indent=2, ensure_ascii=False))
    return 0


def cmd_cycles(args: argparse.Namespace) -> int:
    compiler = ContextCompiler(args.path)
    analysis = compiler.scan_and_compile()
    forensics = run_forensics_report(args.path, analysis)
    print("=" * 86)
    print(
        f" CTXRAY TARJAN SCC CYCLE & LAYER FORENSICS  |  Repo: {analysis.repo_name}  |  Health: {forensics.architecture_health_score}/100"
    )
    print("=" * 86)
    if not forensics.cycles:
        print(" [OK] Zero circular dependency chains detected across repository import graph.")
    else:
        for c in forensics.cycles:
            chain = " -> ".join(c.nodes)
            print(f" [{c.severity}] Cycle ({len(c.nodes)} modules): {chain}")
            print(f"   Suggested Edge to Break: {c.suggested_edge_to_break[0]} -> {c.suggested_edge_to_break[1]} ({c.rationale})")
    if forensics.layer_violations:
        print("-" * 86)
        print(f" Upward Architectural Layer Violations ({len(forensics.layer_violations)}):")
        for v in forensics.layer_violations[:10]:
            print(f"   * {v.source_path} [{v.source_layer}] -> {v.target_path} [{v.target_layer}]: {v.reason}")
    print("=" * 86)
    return 0


def cmd_hotspots(args: argparse.Namespace) -> int:
    compiler = ContextCompiler(args.path)
    analysis = compiler.scan_and_compile()
    forensics = run_forensics_report(args.path, analysis)
    print("=" * 86)
    print(
        f" CTXRAY GIT CHURN x PAGERANK HOTSPOTS  |  Commits Analyzed: {forensics.git_commits_analyzed} ({forensics.git_history_mode})"
    )
    print("=" * 86)
    print(f"{'RISK GRAVITY':<14} {'PAGERANK':<12} {'COMMITS':<10} {'LAYER':<16} {'FILE PATH'}")
    print("-" * 86)
    for h in forensics.hotspots[:20]:
        print(
            f"{h.risk_gravity:<14.4f} {h.pagerank:<12.4f} {h.commit_count:<10d} {h.layer:<16} {h.path}"
        )
    print("=" * 86)
    return 0


def cmd_mermaid(args: argparse.Namespace) -> int:
    compiler = ContextCompiler(args.path)
    analysis = compiler.scan_and_compile()
    forensics = run_forensics_report(args.path, analysis)
    print(forensics.mermaid_diagram)
    return 0


def cmd_init_rules(args: argparse.Namespace) -> int:
    budget = _parse_budget(args.budget)
    gen = RulesGenerator(args.path, budget_tokens=budget)
    res = gen.compile(output_dir=args.output_dir, write=not args.dry_run)
    if args.dry_run:
        print(res["contents"]["CLAUDE.md"])
    else:
        print(f"[ctxray] Generated repository-specific AI context rules for '{res['repo_name']}':")
        for wf in res["written_files"]:
            print(f"  + {wf}")
    return 0


def cmd_trace(args: argparse.Namespace) -> int:
    rep = analyze_trace(
        trace_path=args.trace_path,
        demo=args.demo or not bool(args.trace_path),
        model=args.model,
    )
    print(format_trace_report(rep, fmt=args.format))
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    budget = _parse_budget(args.budget)
    compiler = ContextCompiler(args.path, budget_tokens=budget)
    analysis = compiler.scan_and_compile()
    if args.target == "anthropic":
        payload = PayloadExporter.to_anthropic_cached_messages(analysis, user_task=args.task)
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    elif args.target == "openai":
        payload = PayloadExporter.to_openai_responses_payload(analysis, user_task=args.task)
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        forensics = run_forensics_report(args.path, analysis)
        cycles_raw = [c.nodes for c in forensics.cycles]
        hotspots_raw = [
            {"path": h.path, "risk_score": h.risk_gravity, "commits": h.commit_count, "pagerank": h.pagerank}
            for h in forensics.hotspots
        ]
        print(PayloadExporter.to_github_pr_markdown(analysis, cycles=cycles_raw, hotspots=hotspots_raw))
    return 0


def cmd_studio(args: argparse.Namespace) -> int:
    if getattr(args, "serve", False):
        budget = _parse_budget(getattr(args, "budget", "32k"))
        return run_studio_server(
            root_path=getattr(args, "path", "."),
            port=getattr(args, "port", 8420),
            open_browser=not args.no_open,
            default_budget=budget,
        )
    studio_html = Path(__file__).resolve().parent.parent / "studio" / "index.html"
    if not studio_html.is_file():
        print(f"Error: studio/index.html not found at {studio_html}", file=sys.stderr)
        return 1
    print(f"[ctxray] Visual X-Ray Studio ready at: {studio_html}")
    if not args.no_open:
        webbrowser.open(studio_html.as_uri())
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ctxray",
        description="ctxray — Visual Context Compiler, Dependency PageRank & AST Skeletonizer for AI Agents",
    )
    parser.add_argument("--version", action="version", version=f"ctxray {__version__}")
    sub = parser.add_subparsers(dest="command")

    p_scan = sub.add_parser("scan", help="Compile a repository into a cache-pinned context bundle")
    p_scan.add_argument("path", nargs="?", default=".", help="Repository path (default: .)")
    p_scan.add_argument("-b", "--budget", default="32k", help="Token budget, e.g. 16k, 32k, 64k")
    p_scan.add_argument("-f", "--format", choices=["xml", "md", "json"], default="xml", help="Output format")
    p_scan.add_argument("-o", "--output", help="Write compiled bundle to file")

    p_rank = sub.add_parser("rank", help="Display terminal Dependency PageRank & Token X-Ray table")
    p_rank.add_argument("path", nargs="?", default=".", help="Repository path (default: .)")
    p_rank.add_argument("-b", "--budget", default="32k", help="Token budget (default: 32k)")
    p_rank.add_argument("-n", "--top", type=int, default=25, help="Max files to display")

    p_blast = sub.add_parser("blast", help="Analyze upstream/downstream blast radius for a file")
    p_blast.add_argument("target", help="Target file path or module substring")
    p_blast.add_argument("-p", "--path", default=".", help="Repository root path")

    p_skel = sub.add_parser("skeleton", help="Extract AST signature skeleton from a single source file")
    p_skel.add_argument("file", help="Path to source file")
    p_skel.add_argument("--symbols", action="store_true", help="Include deep symbol, route & schema extraction JSON")

    p_cycles = sub.add_parser("cycles", help="Detect circular dependencies (Tarjan SCC) & layer violations")
    p_cycles.add_argument("path", nargs="?", default=".", help="Repository path (default: .)")

    p_hot = sub.add_parser("hotspots", help="Analyze Git commit churn x Dependency PageRank hotspots")
    p_hot.add_argument("path", nargs="?", default=".", help="Repository path (default: .)")

    p_merm = sub.add_parser("mermaid", help="Compile repository architecture into a Mermaid.js flowchart")
    p_merm.add_argument("path", nargs="?", default=".", help="Repository path (default: .)")

    p_rules = sub.add_parser("init-rules", help="Auto-generate repo-specific CLAUDE.md, AGENTS.md & Cursor rules")
    p_rules.add_argument("path", nargs="?", default=".", help="Repository path (default: .)")
    p_rules.add_argument("-b", "--budget", default="32k", help="Token budget (default: 32k)")
    p_rules.add_argument("-o", "--output-dir", help="Custom output directory")
    p_rules.add_argument("--dry-run", action="store_true", help="Preview generated CLAUDE.md to stdout")

    p_trace = sub.add_parser("trace", help="Analyze AI agent session logs for token bloat & prompt cache breaks")
    p_trace.add_argument("trace_path", nargs="?", help="Path to session JSONL/JSON log")
    p_trace.add_argument("--demo", action="store_true", help="Run on built-in 12-turn benchmark agent session")
    p_trace.add_argument("-m", "--model", default="claude-sonnet-4", help="Pricing model (claude-sonnet-4, gpt-5, etc.)")
    p_trace.add_argument("-f", "--format", choices=["text", "md", "json"], default="text", help="Report format")

    p_exp = sub.add_parser("export", help="Export cache-pinned payloads for Anthropic, OpenAI, or GitHub PRs")
    p_exp.add_argument("target", choices=["anthropic", "openai", "pr-report"], help="Export target format")
    p_exp.add_argument("path", nargs="?", default=".", help="Repository path (default: .)")
    p_exp.add_argument("-b", "--budget", default="32k", help="Token budget (default: 32k)")
    p_exp.add_argument("-t", "--task", default="Analyze architecture and implement requested changes.", help="Task prompt")

    p_studio = sub.add_parser("studio", help="Launch the interactive Visual X-Ray Web Studio")
    p_studio.add_argument("path", nargs="?", default=".", help="Repository path to inspect")
    p_studio.add_argument("--serve", action="store_true", help="Start live local HTTP API server on port 8420")
    p_studio.add_argument("-p", "--port", type=int, default=8420, help="HTTP server port (default: 8420)")
    p_studio.add_argument("-b", "--budget", default="32k", help="Default token budget")
    p_studio.add_argument("--no-open", action="store_true", help="Print Studio path without opening browser")

    sub.add_parser("mcp", help="Start the Model Context Protocol (MCP) stdio server")

    args = parser.parse_args(argv)
    if not args.command:
        args = parser.parse_args(["rank", "."])

    if args.command == "scan":
        return cmd_scan(args)
    if args.command == "rank":
        return cmd_rank(args)
    if args.command == "blast":
        return cmd_blast(args)
    if args.command == "skeleton":
        return cmd_skeleton(args)
    if args.command == "cycles":
        return cmd_cycles(args)
    if args.command == "hotspots":
        return cmd_hotspots(args)
    if args.command == "mermaid":
        return cmd_mermaid(args)
    if args.command == "init-rules":
        return cmd_init_rules(args)
    if args.command == "trace":
        return cmd_trace(args)
    if args.command == "export":
        return cmd_export(args)
    if args.command == "studio":
        return cmd_studio(args)
    if args.command == "mcp":
        CtxRayMCPServer().serve_stdio()
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
