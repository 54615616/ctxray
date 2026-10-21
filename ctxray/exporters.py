from __future__ import annotations

from typing import Dict, List, Optional

from .engine import RepoAnalysis


class PayloadExporter:
    """
    Production exporters that transform a compiled RepoAnalysis into:
    1. Anthropic Messages API payload with explicit ephemeral prompt-cache breakpoints.
    2. OpenAI Responses / Chat Completions API payload optimized for automatic prefix caching.
    3. GitHub Pull Request Markdown X-Ray & Blast-Radius comment report.
    """

    @staticmethod
    def to_anthropic_cached_messages(
        analysis: RepoAnalysis,
        user_task: str = "Analyze the repository architecture and implement the requested changes.",
    ) -> Dict[str, object]:
        """
        Builds an Anthropic Messages API payload using 3 deterministic cache_control breakpoints:
        - Breakpoint 1: Static Architectural PageRank Map
        - Breakpoint 2: Tier 1 (FULL) & Tier 2 (SKELETON) source modules
        - Uncached Tail: Tier 3 summaries, volatile git diff, and the active user task
        """
        arch_lines = [
            f"<architecture_map repo='{analysis.repo_name}' files='{analysis.total_files}'>"
        ]
        for f in analysis.files:
            arch_lines.append(
                f"  <node path='{f.rel_path}' pagerank='{f.pagerank:.3f}' tier='{f.tier}' "
                f"tokens='{f.allocated_tokens}' dependents='{f.in_degree}' />"
            )
        arch_lines.append("</architecture_map>")

        core_blocks: List[str] = []
        tail_blocks: List[str] = []
        for f in sorted(
            analysis.files,
            key=lambda n: (0 if n.tier == "FULL" else 1 if n.tier == "SKELETON" else 2, n.rel_path),
        ):
            if f.tier in {"FULL", "SKELETON"}:
                body = f.raw_content if f.tier == "FULL" else f.skeleton_content
                core_blocks.append(
                    f"<file path='{f.rel_path}' tier='{f.tier}' pagerank='{f.pagerank:.3f}'>\n{body}\n</file>"
                )
            else:
                tail_blocks.append(
                    f"<file path='{f.rel_path}' tier='SUMMARY'>\n{f.summary_content}\n</file>"
                )

        if analysis.git_diff_summary:
            tail_blocks.append(f"<git_diff>\n{analysis.git_diff_summary}\n</git_diff>")

        return {
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 8192,
            "system": [
                {
                    "type": "text",
                    "text": (
                        "You are an expert software architect operating on a ctxray-compiled repository bundle. "
                        "Files marked [SKELETON] have implementation bodies folded while preserving 100% of "
                        "signatures, types, interfaces, and docstrings."
                    ),
                },
                {
                    "type": "text",
                    "text": "\n".join(arch_lines),
                    "cache_control": {"type": "ephemeral"},
                },
                {
                    "type": "text",
                    "text": "\n\n".join(core_blocks),
                    "cache_control": {"type": "ephemeral"},
                },
            ],
            "messages": [
                {
                    "role": "user",
                    "content": "\n\n".join(tail_blocks + [f"<task>\n{user_task}\n</task>"]),
                }
            ],
        }

    @staticmethod
    def to_openai_responses_payload(
        analysis: RepoAnalysis,
        user_task: str = "Analyze the repository architecture and implement the requested changes.",
    ) -> Dict[str, object]:
        """
        Builds an OpenAI Responses API payload with deterministic prefix ordering
        and prompt_cache_key for >90% prefix cache hit rates on GPT-5 / o-series models.
        """
        static_prefix: List[str] = [
            f"# Repository Architecture Map ({analysis.repo_name})",
            f"# Compiled Tokens: {analysis.compiled_total_tokens} (Saved {analysis.savings_pct}%)",
        ]
        for f in sorted(analysis.files, key=lambda n: n.rel_path):
            if f.tier in {"FULL", "SKELETON"}:
                body = f.raw_content if f.tier == "FULL" else f.skeleton_content
                static_prefix.append(
                    f"## [{f.tier}] {f.rel_path} (PageRank={f.pagerank:.3f})\n{body}"
                )

        volatile_tail: List[str] = []
        for f in sorted(analysis.files, key=lambda n: n.rel_path):
            if f.tier == "SUMMARY":
                volatile_tail.append(f.summary_content)
        if analysis.git_diff_summary:
            volatile_tail.append(f"## Git Working Tree Diff\n{analysis.git_diff_summary}")
        volatile_tail.append(f"## User Objective\n{user_task}")

        return {
            "model": "gpt-5",
            "prompt_cache_key": f"ctxray:{analysis.repo_name}:v1",
            "input": [
                {
                    "role": "developer",
                    "content": "\n\n".join(static_prefix),
                },
                {
                    "role": "user",
                    "content": "\n\n".join(volatile_tail),
                },
            ],
        }

    @staticmethod
    def to_github_pr_markdown(
        analysis: RepoAnalysis,
        cycles: Optional[List[List[str]]] = None,
        hotspots: Optional[List[Dict[str, object]]] = None,
    ) -> str:
        """Generates a GitHub Pull Request comment summarizing architectural impact and token budget."""
        bt = chr(96)
        lines = [
            f"## ⚡ {bt}ctxray{bt} Architectural X-Ray & Token Budget Report",
            "",
            "| Metric | Value | Status |",
            "| :--- | :--- | :--- |",
            f"| **Repository Files** | {bt}{analysis.total_files}{bt} | ✅ Scanned |",
            f"| **Raw -> Compiled Tokens** | {bt}{analysis.raw_total_tokens:,}{bt} -> **{bt}{analysis.compiled_total_tokens:,}{bt}** | 🚀 **-{analysis.savings_pct}% saved** |",
            f"| **Tier Distribution** | {bt}FULL: {analysis.tier_counts['FULL']}{bt} • {bt}SKELETON: {analysis.tier_counts['SKELETON']}{bt} • {bt}SUMMARY: {analysis.tier_counts['SUMMARY']}{bt} | 🎯 Budget {bt}{analysis.budget_tokens:,}{bt} |",
            f"| **Prefix Cache Hit Est.** | **{bt}{analysis.estimated_cache_hit_pct}%{bt}** | ⚡ Pinned Prefix |",
            f"| **Secrets Redacted** | {bt}{analysis.secrets_redacted}{bt} | 🛡️ Guard Active |",
            "",
            "### Top 10 Architectural Gravity Nodes (PageRank)",
            "",
            "| Tier | PageRank | Tokens (Comp/Raw) | Dependents (Blast) | File Path |",
            "| :--- | :--- | :--- | :--- | :--- |",
        ]
        for f in analysis.files[:10]:
            lines.append(
                f"| {bt}{f.tier}{bt} | {bt}{f.pagerank:.3f}{bt} | {bt}{f.allocated_tokens:,} / {f.raw_tokens:,}{bt} | {bt}{f.in_degree}{bt} | {bt}{f.rel_path}{bt} |"
            )

        if cycles:
            lines.extend([
                "",
                f"### ⚠️ Circular Dependencies Detected ({bt}{len(cycles)}{bt} SCC cycles)",
                "",
            ])
            for cyc in cycles[:5]:
                chain = " -> ".join([f"{bt}{p}{bt}" for p in cyc])
                lines.append(f"- 🔄 {chain}")

        if hotspots:
            lines.extend([
                "",
                "### 🔥 Top Git Churn × PageRank Hotspots",
                "",
            ])
            for h in hotspots[:5]:
                lines.append(
                    f"- {bt}{h.get('path')}{bt} — Risk Score: **{bt}{h.get('risk_score')}{bt}** "
                    f"(Commits: {bt}{h.get('commits')}{bt}, PageRank: {bt}{h.get('pagerank')}{bt})"
                )

        return "\n".join(lines)
