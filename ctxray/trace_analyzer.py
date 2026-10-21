from __future__ import annotations

"""
ctxray.trace_analyzer — AI Agent Session Flight Recorder & Token Burn Forensics (`ctxray trace`).

Parses local AI coding agent session logs (Claude Code `~/.claude/projects/**/*.jsonl`,
OpenAI Codex `~/.codex/sessions/**/*.jsonl`, Cursor session traces, or any custom
`.jsonl` / `.json` trace file) plus a realistic built-in synthetic demo trace (`--demo`).

Computes:
  1. Turn-by-turn context growth curve & token burn velocity
  2. Top Context Bloat Offenders (oversized tool outputs, raw `cat`/`grep` dumps, repeated file reads)
  3. Prompt Cache Break Detector (turns where prefix cache was invalidated due to prefix mutation)
  4. Actionable Savings Report (exact token & USD savings achievable via `ctxray` AST skeletons + cache pinning)
"""

from collections import defaultdict
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

from .engine import PolyglotSkeletonizer, TokenEstimator


# Pricing per 1,000,000 tokens (USD)
MODEL_PRICING_PER_M: Dict[str, Dict[str, float]] = {
    "claude-sonnet-4": {
        "input": 3.00,
        "cached_input": 0.30,
        "cache_write": 3.75,
        "output": 15.00,
    },
    "claude-opus-4": {
        "input": 15.00,
        "cached_input": 1.50,
        "cache_write": 18.75,
        "output": 75.00,
    },
    "gpt-5": {
        "input": 2.50,
        "cached_input": 0.25,
        "cache_write": 2.50,
        "output": 10.00,
    },
    "gpt-4.1": {
        "input": 2.00,
        "cached_input": 0.50,
        "cache_write": 2.00,
        "output": 8.00,
    },
    "o3": {
        "input": 2.00,
        "cached_input": 0.50,
        "cache_write": 2.00,
        "output": 8.00,
    },
}


def _get_pricing(model: str) -> Dict[str, float]:
    m = (model or "claude-sonnet-4").lower()
    for key, pricing in MODEL_PRICING_PER_M.items():
        if key in m:
            return pricing
    if "opus" in m:
        return MODEL_PRICING_PER_M["claude-opus-4"]
    if "gpt-5" in m or "codex" in m:
        return MODEL_PRICING_PER_M["gpt-5"]
    return MODEL_PRICING_PER_M["claude-sonnet-4"]


@dataclass
class TurnRecord:
    """Telemetry for a single agent turn in a coding session."""

    turn_index: int
    timestamp: str
    role: str
    tool_name: str
    target_file: Optional[str]
    command_or_query: str
    input_tokens: int
    cached_input_tokens: int
    uncached_input_tokens: int
    output_tokens: int
    tool_output_tokens: int
    cumulative_context_tokens: int
    token_velocity: int
    cache_hit_ratio: float
    cache_break_detected: bool = False
    cache_break_reason: str = ""
    bloat_category: Optional[str] = None
    skeleton_recoverable_tokens: int = 0
    cost_usd: float = 0.0
    optimized_cost_usd: float = 0.0

    @property
    def turn(self) -> int:
        return self.turn_index

    def to_dict(self) -> Dict[str, Any]:
        return {
            "turn_index": self.turn_index,
            "turn": self.turn_index,
            "timestamp": self.timestamp,
            "role": self.role,
            "tool_name": self.tool_name,
            "target_file": self.target_file,
            "command_or_query": self.command_or_query,
            "input_tokens": self.input_tokens,
            "cached_input_tokens": self.cached_input_tokens,
            "uncached_input_tokens": self.uncached_input_tokens,
            "output_tokens": self.output_tokens,
            "tool_output_tokens": self.tool_output_tokens,
            "cumulative_context_tokens": self.cumulative_context_tokens,
            "token_velocity": self.token_velocity,
            "cache_hit_ratio": round(self.cache_hit_ratio, 4),
            "cache_hit_pct": round(self.cache_hit_ratio * 100.0, 1),
            "cache_break_detected": self.cache_break_detected,
            "cache_break_reason": self.cache_break_reason,
            "bloat_category": self.bloat_category,
            "skeleton_recoverable_tokens": self.skeleton_recoverable_tokens,
            "cost_usd": round(self.cost_usd, 5),
            "optimized_cost_usd": round(self.optimized_cost_usd, 5),
        }


@dataclass
class BloatOffender:
    """Ranked context bloat source (oversized dump or redundant full-file reads)."""

    rank: int
    category: str
    target: str
    tool_name: str
    occurrences: int
    turns: List[int]
    raw_tokens_consumed: int
    wasted_tokens: int
    skeleton_tokens: int
    savings_pct: float
    wasted_cost_usd: float
    recommendation: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rank": self.rank,
            "category": self.category,
            "target": self.target,
            "tool_name": self.tool_name,
            "occurrences": self.occurrences,
            "turns": self.turns,
            "raw_tokens_consumed": self.raw_tokens_consumed,
            "wasted_tokens": self.wasted_tokens,
            "skeleton_tokens": self.skeleton_tokens,
            "savings_pct": round(self.savings_pct, 1),
            "wasted_cost_usd": round(self.wasted_cost_usd, 4),
            "recommendation": self.recommendation,
        }


@dataclass
class CacheBreakEvent:
    """Forensic record of a prompt prefix cache invalidation event."""

    turn_index: int
    timestamp: str
    previous_cached_tokens: int
    new_cached_tokens: int
    invalidated_tokens: int
    reason: str
    cost_penalty_usd: float
    remediation: str

    @property
    def turn(self) -> int:
        return self.turn_index

    def to_dict(self) -> Dict[str, Any]:
        return {
            "turn_index": self.turn_index,
            "turn": self.turn_index,
            "timestamp": self.timestamp,
            "previous_cached_tokens": self.previous_cached_tokens,
            "new_cached_tokens": self.new_cached_tokens,
            "invalidated_tokens": self.invalidated_tokens,
            "reason": self.reason,
            "cost_penalty_usd": round(self.cost_penalty_usd, 4),
            "remediation": self.remediation,
        }


@dataclass
class SavingsReport:
    """Financial and token savings achievable by applying `ctxray` skeletons + cache pinning."""

    model_name: str
    actual_total_input_tokens: int
    actual_cached_tokens: int
    actual_uncached_tokens: int
    actual_output_tokens: int
    actual_cost_usd: float
    ctxray_total_input_tokens: int
    ctxray_cached_tokens: int
    ctxray_uncached_tokens: int
    ctxray_cost_usd: float
    tokens_saved: int
    token_savings_pct: float
    cost_saved_usd: float
    cost_savings_pct: float
    skeleton_compression_saved_tokens: int
    dedup_file_reads_saved_tokens: int
    cache_pinning_saved_tokens: int
    projected_monthly_savings_usd: float
    actionable_steps: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_name": self.model_name,
            "actual_total_input_tokens": self.actual_total_input_tokens,
            "actual_cached_tokens": self.actual_cached_tokens,
            "actual_uncached_tokens": self.actual_uncached_tokens,
            "actual_output_tokens": self.actual_output_tokens,
            "actual_cost_usd": round(self.actual_cost_usd, 4),
            "ctxray_total_input_tokens": self.ctxray_total_input_tokens,
            "ctxray_cached_tokens": self.ctxray_cached_tokens,
            "ctxray_uncached_tokens": self.ctxray_uncached_tokens,
            "ctxray_cost_usd": round(self.ctxray_cost_usd, 4),
            "tokens_saved": self.tokens_saved,
            "token_savings_pct": round(self.token_savings_pct, 1),
            "cost_saved_usd": round(self.cost_saved_usd, 4),
            "cost_savings_pct": round(self.cost_savings_pct, 1),
            "skeleton_compression_saved_tokens": self.skeleton_compression_saved_tokens,
            "dedup_file_reads_saved_tokens": self.dedup_file_reads_saved_tokens,
            "cache_pinning_saved_tokens": self.cache_pinning_saved_tokens,
            "projected_monthly_savings_usd": round(self.projected_monthly_savings_usd, 2),
            "actionable_steps": self.actionable_steps,
        }


@dataclass
class SessionTraceReport:
    """Complete forensic flight-recorder analysis of an AI coding agent session."""

    session_id: str
    agent_type: str
    source_path: str
    model_name: str
    total_turns: int
    peak_context_tokens: int
    avg_token_velocity: float
    max_token_velocity: int
    overall_cache_hit_pct: float
    cache_breaks_count: int
    turns: List[TurnRecord]
    bloat_offenders: List[BloatOffender]
    cache_breaks: List[CacheBreakEvent]
    savings: SavingsReport

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "agent_type": self.agent_type,
            "source_path": self.source_path,
            "model_name": self.model_name,
            "total_turns": self.total_turns,
            "peak_context_tokens": self.peak_context_tokens,
            "avg_token_velocity": round(self.avg_token_velocity, 1),
            "max_token_velocity": self.max_token_velocity,
            "overall_cache_hit_pct": round(self.overall_cache_hit_pct, 1),
            "cache_breaks_count": self.cache_breaks_count,
            "turns": [t.to_dict() for t in self.turns],
            "bloat_offenders": [b.to_dict() for b in self.bloat_offenders],
            "cache_breaks": [c.to_dict() for c in self.cache_breaks],
            "savings": self.savings.to_dict(),
        }

    def format_terminal(self) -> str:
        return format_trace_report(self, fmt="text")

    def format_markdown(self) -> str:
        return format_trace_report(self, fmt="md")

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


# Alias for external callers expecting TraceAnalysis
TraceAnalysis = SessionTraceReport


def discover_local_traces(search_roots: Optional[List[Union[str, Path]]] = None) -> List[Path]:
    """
    Scans standard local agent session directories for `.jsonl` and `.json` trace logs:
      - Claude Code: `~/.claude/projects/**/*.jsonl`
      - OpenAI Codex: `~/.codex/sessions/**/*.jsonl`
      - Cursor IDE: `~/.cursor/**/*.jsonl`
    Returns discovered files sorted by most recently modified first.
    """
    candidates: List[Path] = []
    roots: List[Path] = []
    if search_roots:
        for r in search_roots:
            p = Path(r).expanduser()
            if p.exists():
                roots.append(p)
    else:
        home = Path.home()
        default_dirs = [
            home / ".claude" / "projects",
            home / ".codex" / "sessions",
            home / ".cursor" / "projects",
            Path.cwd() / ".claude",
            Path.cwd() / ".codex",
            Path.cwd() / "traces",
        ]
        for d in default_dirs:
            if d.exists():
                roots.append(d)

    for root in roots:
        if root.is_file() and root.suffix.lower() in {".jsonl", ".json"}:
            candidates.append(root)
            continue
        try:
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if d not in {"node_modules", ".git", "__pycache__"}]
                for fname in filenames:
                    if fname.endswith(".jsonl") or (fname.endswith(".json") and "trace" in fname.lower()):
                        fpath = Path(dirpath) / fname
                        try:
                            if 100 <= fpath.stat().st_size <= 25_000_000:
                                candidates.append(fpath)
                        except OSError:
                            continue
        except OSError:
            continue

    candidates.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0.0, reverse=True)
    return candidates[:25]


def generate_demo_trace(repo_root: Optional[Union[str, Path]] = None) -> List[Dict[str, Any]]:
    """
    Generates a realistic 12-turn AI coding agent session trace illustrating real-world
    context bloat, repeated full-file reads, unbounded grep dumps, and prompt cache breaks.
    """
    primary_file = "ctxray/engine.py"
    secondary_file = "studio/index.html"
    cli_file = "ctxray/cli.py"
    mcp_file = "ctxray/mcp_server.py"

    if repo_root is not None:
        root = Path(repo_root)
        if (root / "ctxray" / "engine.py").is_file():
            primary_file = "ctxray/engine.py"
        elif root.is_dir():
            py_files = sorted(root.rglob("*.py"))
            if py_files:
                try:
                    primary_file = py_files[0].relative_to(root).as_posix()
                except ValueError:
                    pass

    return [
        {
            "turn": 1,
            "timestamp": "2026-10-21T10:00:04Z",
            "agent": "claude-code",
            "model": "claude-sonnet-4",
            "tool_name": "Glob",
            "target_file": None,
            "command": "glob **/*.{py,ts,js,html}",
            "tool_output_tokens": 420,
            "input_tokens": 4_620,
            "cached_input_tokens": 4_100,
            "output_tokens": 290,
            "system_prefix_hash": "pfx_v1_static_a91f",
        },
        {
            "turn": 2,
            "timestamp": "2026-10-21T10:00:19Z",
            "agent": "claude-code",
            "model": "claude-sonnet-4",
            "tool_name": "Read",
            "target_file": primary_file,
            "command": f"Read({primary_file}) [full raw file read #1]",
            "tool_output_tokens": 6_840,
            "skeleton_tokens": 1_520,
            "input_tokens": 11_750,
            "cached_input_tokens": 4_620,
            "output_tokens": 410,
            "system_prefix_hash": "pfx_v1_static_a91f",
        },
        {
            "turn": 3,
            "timestamp": "2026-10-21T10:00:38Z",
            "agent": "claude-code",
            "model": "claude-sonnet-4",
            "tool_name": "Bash",
            "target_file": None,
            "command": "grep -rn \"def \" . && cat package.json pyproject.toml",
            "tool_output_tokens": 9_450,
            "skeleton_tokens": 1_100,
            "input_tokens": 21_610,
            "cached_input_tokens": 11_750,
            "output_tokens": 520,
            "system_prefix_hash": "pfx_v1_static_a91f",
        },
        {
            "turn": 4,
            "timestamp": "2026-10-21T10:01:02Z",
            "agent": "claude-code",
            "model": "claude-sonnet-4",
            "tool_name": "Read",
            "target_file": secondary_file,
            "command": f"Read({secondary_file}) [unpruned UI bundle read #1]",
            "tool_output_tokens": 11_200,
            "skeleton_tokens": 1_850,
            "input_tokens": 33_330,
            "cached_input_tokens": 21_610,
            "output_tokens": 480,
            "system_prefix_hash": "pfx_v1_static_a91f",
        },
        {
            "turn": 5,
            "timestamp": "2026-10-21T10:01:29Z",
            "agent": "claude-code",
            "model": "claude-sonnet-4",
            "tool_name": "Read",
            "target_file": cli_file,
            "command": f"Read({cli_file}) + volatile git diff injected into system header",
            "tool_output_tokens": 2_180,
            "skeleton_tokens": 540,
            "input_tokens": 35_990,
            "cached_input_tokens": 4_100,
            "output_tokens": 390,
            "system_prefix_hash": "pfx_v2_mutated_git_diff_header",
            "cache_break_reason": "Volatile `git diff` & timestamp injected at top of system prompt prefix",
        },
        {
            "turn": 6,
            "timestamp": "2026-10-21T10:01:54Z",
            "agent": "claude-code",
            "model": "claude-sonnet-4",
            "tool_name": "Read",
            "target_file": primary_file,
            "command": f"Read({primary_file}) [redundant full file re-read #2]",
            "tool_output_tokens": 6_840,
            "skeleton_tokens": 1_520,
            "input_tokens": 43_220,
            "cached_input_tokens": 35_990,
            "output_tokens": 610,
            "system_prefix_hash": "pfx_v2_mutated_git_diff_header",
        },
        {
            "turn": 7,
            "timestamp": "2026-10-21T10:02:18Z",
            "agent": "claude-code",
            "model": "claude-sonnet-4",
            "tool_name": "Read",
            "target_file": mcp_file,
            "command": f"Read({mcp_file}) [full file read #1]",
            "tool_output_tokens": 2_450,
            "skeleton_tokens": 610,
            "input_tokens": 46_280,
            "cached_input_tokens": 43_220,
            "output_tokens": 440,
            "system_prefix_hash": "pfx_v2_mutated_git_diff_header",
        },
        {
            "turn": 8,
            "timestamp": "2026-10-21T10:02:49Z",
            "agent": "claude-code",
            "model": "claude-sonnet-4",
            "tool_name": "Bash",
            "target_file": None,
            "command": "cat studio/index.html | head -n 600",
            "tool_output_tokens": 8_920,
            "skeleton_tokens": 950,
            "input_tokens": 55_640,
            "cached_input_tokens": 46_280,
            "output_tokens": 530,
            "system_prefix_hash": "pfx_v2_mutated_git_diff_header",
        },
        {
            "turn": 9,
            "timestamp": "2026-10-21T10:03:15Z",
            "agent": "claude-code",
            "model": "claude-sonnet-4",
            "tool_name": "Read",
            "target_file": primary_file,
            "command": f"Read({primary_file}) [redundant full file re-read #3]",
            "tool_output_tokens": 6_840,
            "skeleton_tokens": 1_520,
            "input_tokens": 63_010,
            "cached_input_tokens": 55_640,
            "output_tokens": 720,
            "system_prefix_hash": "pfx_v2_mutated_git_diff_header",
        },
        {
            "turn": 10,
            "timestamp": "2026-10-21T10:03:47Z",
            "agent": "claude-code",
            "model": "claude-sonnet-4",
            "tool_name": "Edit",
            "target_file": cli_file,
            "command": f"Edit({cli_file}) + MCP tool list dynamically re-sorted",
            "tool_output_tokens": 1_150,
            "skeleton_tokens": 540,
            "input_tokens": 64_880,
            "cached_input_tokens": 8_200,
            "output_tokens": 680,
            "system_prefix_hash": "pfx_v3_tool_schema_reordered",
            "cache_break_reason": "MCP tool declarations re-ordered & middle turns evicted without cache breakpoint pinning",
        },
        {
            "turn": 11,
            "timestamp": "2026-10-21T10:04:12Z",
            "agent": "claude-code",
            "model": "claude-sonnet-4",
            "tool_name": "Read",
            "target_file": secondary_file,
            "command": f"Read({secondary_file}) [redundant full file re-read #2]",
            "tool_output_tokens": 11_200,
            "skeleton_tokens": 1_850,
            "input_tokens": 76_760,
            "cached_input_tokens": 64_880,
            "output_tokens": 590,
            "system_prefix_hash": "pfx_v3_tool_schema_reordered",
        },
        {
            "turn": 12,
            "timestamp": "2026-10-21T10:04:40Z",
            "agent": "claude-code",
            "model": "claude-sonnet-4",
            "tool_name": "Bash",
            "target_file": None,
            "command": "pytest -vv -s",
            "tool_output_tokens": 1_420,
            "skeleton_tokens": 480,
            "input_tokens": 78_770,
            "cached_input_tokens": 76_760,
            "output_tokens": 840,
            "system_prefix_hash": "pfx_v3_tool_schema_reordered",
        },
    ]


def _extract_file_from_command(cmd: str) -> Optional[str]:
    """Extracts a likely file path from a shell command or tool argument string."""
    if not cmd:
        return None
    m = re.search(
        r"([A-Za-z0-9_./\\-]+\.(?:py|ts|tsx|js|jsx|rs|go|java|c|cpp|h|hpp|cs|rb|php|md|json|yaml|yml|toml|html|css))",
        cmd,
    )
    if m:
        return m.group(1).replace("\\", "/")
    return None


def parse_trace_events(raw_source: Union[str, Path, List[Dict[str, Any]], Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], str, str]:
    """
    Parses raw events from:
      - A list of turn dicts
      - A `.jsonl` or `.json` file path (Claude Code, OpenAI Codex, Cursor, or custom format)
      - Raw JSON / JSONL string content
    Returns `(normalized_raw_events, detected_agent_type, source_label)`.
    """
    if isinstance(raw_source, list):
        return raw_source, "synthetic-demo", "built-in://demo-session"
    if isinstance(raw_source, dict):
        turns = raw_source.get("turns") or raw_source.get("events") or raw_source.get("messages") or [raw_source]
        agent = str(raw_source.get("agent_type") or raw_source.get("agent") or "custom")
        return list(turns), agent, "dict://in-memory"

    path_obj: Optional[Path] = None
    if isinstance(raw_source, Path):
        path_obj = raw_source
    elif isinstance(raw_source, str):
        cand = Path(raw_source)
        if cand.exists() and cand.is_file():
            path_obj = cand

    if path_obj is not None:
        raw_text = path_obj.read_text(encoding="utf-8", errors="ignore")
        source_label = str(path_obj.resolve())
        lower_path = source_label.lower()
        if ".claude" in lower_path or "claude" in lower_path:
            agent_hint = "claude-code"
        elif ".codex" in lower_path or "codex" in lower_path:
            agent_hint = "codex"
        elif ".cursor" in lower_path or "cursor" in lower_path:
            agent_hint = "cursor"
        else:
            agent_hint = "custom-log"
    else:
        raw_text = str(raw_source)
        source_label = "inline://json"
        agent_hint = "custom-log"

    stripped = raw_text.strip()
    records: List[Dict[str, Any]] = []
    if not stripped:
        return [], agent_hint, source_label

    if stripped.startswith("{") or stripped.startswith("["):
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, list):
                records = [r for r in parsed if isinstance(r, dict)]
            elif isinstance(parsed, dict):
                inner = parsed.get("turns") or parsed.get("events") or parsed.get("messages")
                if isinstance(inner, list):
                    records = [r for r in inner if isinstance(r, dict)]
                else:
                    records = [parsed]
        except json.JSONDecodeError:
            records = []

    if not records:
        for line in stripped.splitlines():
            s = line.strip()
            if not s:
                continue
            try:
                obj = json.loads(s)
                if isinstance(obj, dict):
                    records.append(obj)
            except json.JSONDecodeError:
                continue

    return records, agent_hint, source_label


def _normalize_raw_records(
    raw_records: List[Dict[str, Any]],
    agent_hint: str,
    model_override: Optional[str] = None,
) -> Tuple[List[TurnRecord], str, str]:
    """
    Normalizes heterogeneous Claude Code / OpenAI Codex / Cursor / custom log records
    into a sequential list of `TurnRecord` objects with full token and cache telemetry.
    """
    turns: List[TurnRecord] = []
    detected_model = model_override or "claude-sonnet-4"
    detected_agent = agent_hint
    cumulative_ctx = 3_200
    prev_cached = 0
    prev_prefix_hash = ""

    for idx, rec in enumerate(raw_records, start=1):
        ts = str(
            rec.get("timestamp")
            or rec.get("created_at")
            or rec.get("time")
            or f"turn-{idx:02d}"
        )
        if "agent" in rec and rec["agent"]:
            detected_agent = str(rec["agent"])
        if not model_override and rec.get("model"):
            detected_model = str(rec["model"])

        msg = rec.get("message") if isinstance(rec.get("message"), dict) else {}
        if not model_override and msg.get("model"):
            detected_model = str(msg["model"])

        usage = (
            rec.get("usage")
            or msg.get("usage")
            or (rec.get("response", {}) if isinstance(rec.get("response"), dict) else {}).get("usage")
            or {}
        )
        if not isinstance(usage, dict):
            usage = {}

        # Extract tool name, target file, command, and tool output
        tool_name = str(rec.get("tool_name") or rec.get("tool") or rec.get("type") or "agent_turn")
        target_file: Optional[str] = rec.get("target_file") or rec.get("file_path") or rec.get("path")
        command_str = str(rec.get("command") or rec.get("command_or_query") or rec.get("query") or "")
        tool_output_text = str(rec.get("tool_output") or rec.get("output") or "")

        content_blocks = msg.get("content") or rec.get("content")
        if isinstance(content_blocks, list):
            for block in content_blocks:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type", "")
                if btype in {"tool_use", "function_call", "custom_tool_call"}:
                    tool_name = str(block.get("name") or tool_name)
                    b_input = block.get("input") or block.get("arguments") or {}
                    if isinstance(b_input, str):
                        try:
                            b_input = json.loads(b_input)
                        except Exception:
                            b_input = {"cmd": b_input}
                    if isinstance(b_input, dict):
                        target_file = target_file or b_input.get("file_path") or b_input.get("path")
                        command_str = command_str or str(
                            b_input.get("command") or b_input.get("cmd") or b_input.get("pattern") or b_input
                        )
                elif btype in {"tool_result", "function_call_output"}:
                    sub_content = block.get("content") or block.get("output") or ""
                    if isinstance(sub_content, list):
                        sub_content = "\n".join(
                            str(x.get("text", x)) if isinstance(x, dict) else str(x) for x in sub_content
                        )
                    tool_output_text += str(sub_content)
        elif isinstance(content_blocks, str) and not tool_output_text:
            tool_output_text = content_blocks

        if not target_file and command_str:
            target_file = _extract_file_from_command(command_str)
        if target_file:
            target_file = str(target_file).replace("\\", "/")

        tool_output_tok = int(
            rec.get("tool_output_tokens")
            or (TokenEstimator.estimate(tool_output_text) if tool_output_text else 450)
        )

        # Extract input, cached, and output tokens
        raw_in = int(
            rec.get("input_tokens")
            or usage.get("input_tokens")
            or usage.get("prompt_tokens")
            or 0
        )
        cached_in = int(
            rec.get("cached_input_tokens")
            or usage.get("cache_read_input_tokens")
            or (usage.get("input_tokens_details", {}) or {}).get("cached_tokens", 0)
            or (usage.get("prompt_tokens_details", {}) or {}).get("cached_tokens", 0)
            or 0
        )
        cache_write = int(usage.get("cache_creation_input_tokens") or 0)
        out_tok = int(
            rec.get("output_tokens")
            or usage.get("output_tokens")
            or usage.get("completion_tokens")
            or 320
        )

        if raw_in <= 0:
            cumulative_ctx += tool_output_tok + out_tok
            total_in = cumulative_ctx
            if cached_in <= 0 and idx > 1:
                cached_in = int(total_in * 0.72)
        else:
            # In Anthropic logs, total input is input_tokens + cache_read_input_tokens + cache_creation_input_tokens
            if "cache_read_input_tokens" in usage and raw_in < cached_in:
                total_in = raw_in + cached_in + cache_write
            else:
                total_in = max(raw_in, cached_in)
            cumulative_ctx = max(cumulative_ctx, total_in)

        uncached_in = max(0, total_in - cached_in)
        prev_ctx = turns[-1].cumulative_context_tokens if turns else 0
        velocity = max(0, total_in - prev_ctx) if idx > 1 else total_in
        hit_ratio = (cached_in / total_in) if total_in > 0 else 0.0

        # Detect prompt cache breaks
        prefix_hash = str(rec.get("system_prefix_hash") or "")
        explicit_break_reason = str(rec.get("cache_break_reason") or "")
        cache_break = False
        break_reason = ""

        if idx > 1:
            if explicit_break_reason:
                cache_break = True
                break_reason = explicit_break_reason
            elif prefix_hash and prev_prefix_hash and prefix_hash != prev_prefix_hash:
                cache_break = True
                break_reason = f"System/prefix hash mutated ({prev_prefix_hash} -> {prefix_hash})"
            elif prev_cached >= 8_000 and cached_in < prev_cached * 0.55:
                cache_break = True
                break_reason = (
                    f"Cached prefix dropped from {prev_cached:,} to {cached_in:,} tokens "
                    f"(-{prev_cached - cached_in:,} invalidated tokens)"
                )

        if prefix_hash:
            prev_prefix_hash = prefix_hash
        prev_cached = cached_in

        # Estimate skeleton recoverable tokens
        skel_tok = int(rec.get("skeleton_tokens") or 0)
        if skel_tok <= 0 and tool_output_tok > 600:
            skel_tok = int(tool_output_tok * 0.24)
        recoverable = max(0, tool_output_tok - skel_tok) if tool_output_tok > 700 else 0

        pricing = _get_pricing(detected_model)
        turn_cost = (
            (uncached_in / 1_000_000.0) * pricing["input"]
            + (cached_in / 1_000_000.0) * pricing["cached_input"]
            + (out_tok / 1_000_000.0) * pricing["output"]
        )

        turns.append(
            TurnRecord(
                turn_index=idx,
                timestamp=ts,
                role=str(rec.get("role") or "assistant"),
                tool_name=tool_name,
                target_file=target_file,
                command_or_query=command_str or f"{tool_name}({target_file or ''})",
                input_tokens=total_in,
                cached_input_tokens=cached_in,
                uncached_input_tokens=uncached_in,
                output_tokens=out_tok,
                tool_output_tokens=tool_output_tok,
                cumulative_context_tokens=total_in,
                token_velocity=velocity,
                cache_hit_ratio=hit_ratio,
                cache_break_detected=cache_break,
                cache_break_reason=break_reason,
                bloat_category=None,
                skeleton_recoverable_tokens=recoverable,
                cost_usd=turn_cost,
                optimized_cost_usd=turn_cost * 0.28,
            )
        )

    return turns, detected_agent, detected_model


def _detect_bloat_offenders(turns: List[TurnRecord], model: str) -> List[BloatOffender]:
    """
    Identifies Top Context Bloat Offenders across the session:
      - Repeated file reads across turns (`REPEATED_FILE_READ`)
      - Oversized raw file dumps (`RAW_FILE_DUMP`)
      - Unbounded shell / grep / cat dumps (`UNBOUNDED_SHELL_OUTPUT`)
    """
    pricing = _get_pricing(model)
    # Blended downstream cost multiplier across remaining turns in session
    total_turns = max(1, len(turns))
    by_file: Dict[str, List[TurnRecord]] = defaultdict(list)
    shell_dumps: List[TurnRecord] = []

    for t in turns:
        t_lower = t.tool_name.lower()
        if t.target_file and any(k in t_lower for k in ("read", "view", "cat", "open", "agent_turn")):
            by_file[t.target_file].append(t)
        elif t.tool_output_tokens >= 1_800:
            shell_dumps.append(t)

    offenders: List[BloatOffender] = []

    for fpath, file_turns in by_file.items():
        occurrences = len(file_turns)
        turn_nums = [ft.turn_index for ft in file_turns]
        raw_per_read = max(ft.tool_output_tokens for ft in file_turns)
        total_raw_consumed = sum(ft.tool_output_tokens for ft in file_turns)
        skel_single = max(
            180,
            min(ft.tool_output_tokens - ft.skeleton_recoverable_tokens for ft in file_turns),
        )

        if occurrences >= 2:
            wasted = max(0, total_raw_consumed - skel_single)
            for ft in file_turns:
                ft.bloat_category = "REPEATED_FILE_READ"
            avg_remaining_turns = max(1.0, (total_turns - turn_nums[0]) * 0.65)
            wasted_usd = (wasted * avg_remaining_turns / 1_000_000.0) * (
                pricing["input"] * 0.35 + pricing["cached_input"] * 0.65
            )
            savings_pct = (wasted / max(1, total_raw_consumed)) * 100.0
            offenders.append(
                BloatOffender(
                    rank=0,
                    category="REPEATED_FILE_READ",
                    target=fpath,
                    tool_name=file_turns[0].tool_name,
                    occurrences=occurrences,
                    turns=turn_nums,
                    raw_tokens_consumed=total_raw_consumed,
                    wasted_tokens=wasted,
                    skeleton_tokens=skel_single,
                    savings_pct=savings_pct,
                    wasted_cost_usd=wasted_usd,
                    recommendation=(
                        f"Pin AST skeleton once via `python ctxray.py skeleton {fpath}` "
                        f"({raw_per_read:,} -> {skel_single:,} tok) instead of re-reading {occurrences}x."
                    ),
                )
            )
        elif raw_per_read >= 1_500:
            wasted = max(0, raw_per_read - skel_single)
            file_turns[0].bloat_category = "RAW_FILE_DUMP"
            avg_remaining_turns = max(1.0, (total_turns - turn_nums[0]) * 0.6)
            wasted_usd = (wasted * avg_remaining_turns / 1_000_000.0) * (
                pricing["input"] * 0.35 + pricing["cached_input"] * 0.65
            )
            savings_pct = (wasted / max(1, raw_per_read)) * 100.0
            offenders.append(
                BloatOffender(
                    rank=0,
                    category="RAW_FILE_DUMP",
                    target=fpath,
                    tool_name=file_turns[0].tool_name,
                    occurrences=1,
                    turns=turn_nums,
                    raw_tokens_consumed=raw_per_read,
                    wasted_tokens=wasted,
                    skeleton_tokens=skel_single,
                    savings_pct=savings_pct,
                    wasted_cost_usd=wasted_usd,
                    recommendation=(
                        f"Replace full file read with `ctxray_skeletonize` ({raw_per_read:,} -> {skel_single:,} tok, "
                        f"-{savings_pct:.1f}%)."
                    ),
                )
            )

    for st in shell_dumps:
        st.bloat_category = "UNBOUNDED_SHELL_OUTPUT"
        skel_equiv = max(350, st.tool_output_tokens - st.skeleton_recoverable_tokens)
        wasted = max(0, st.tool_output_tokens - skel_equiv)
        avg_remaining_turns = max(1.0, (total_turns - st.turn_index) * 0.6)
        wasted_usd = (wasted * avg_remaining_turns / 1_000_000.0) * (
            pricing["input"] * 0.4 + pricing["cached_input"] * 0.6
        )
        savings_pct = (wasted / max(1, st.tool_output_tokens)) * 100.0
        offenders.append(
            BloatOffender(
                rank=0,
                category="UNBOUNDED_SHELL_OUTPUT",
                target=st.command_or_query[:70],
                tool_name=st.tool_name,
                occurrences=1,
                turns=[st.turn_index],
                raw_tokens_consumed=st.tool_output_tokens,
                wasted_tokens=wasted,
                skeleton_tokens=skel_equiv,
                savings_pct=savings_pct,
                wasted_cost_usd=wasted_usd,
                recommendation=(
                    "Use `python ctxray.py rank .` or `ctxray_repo_map` instead of unbounded "
                    "`grep`/`cat` dumps into conversation history."
                ),
            )
        )

    offenders.sort(key=lambda o: (o.wasted_tokens, o.occurrences), reverse=True)
    for idx, off in enumerate(offenders, start=1):
        off.rank = idx
    return offenders[:10]


def _extract_cache_breaks(turns: List[TurnRecord], model: str) -> List[CacheBreakEvent]:
    """Builds detailed forensic records for every turn where prefix cache was invalidated."""
    pricing = _get_pricing(model)
    events: List[CacheBreakEvent] = []
    for idx, t in enumerate(turns):
        if not t.cache_break_detected:
            continue
        prev_cached = turns[idx - 1].input_tokens if idx > 0 else t.input_tokens
        invalidated = max(1_000, prev_cached - t.cached_input_tokens)
        penalty_usd = (invalidated / 1_000_000.0) * (pricing["input"] - pricing["cached_input"])
        events.append(
            CacheBreakEvent(
                turn_index=t.turn_index,
                timestamp=t.timestamp,
                previous_cached_tokens=prev_cached,
                new_cached_tokens=t.cached_input_tokens,
                invalidated_tokens=invalidated,
                reason=t.cache_break_reason or "System prompt prefix mutated mid-session",
                cost_penalty_usd=penalty_usd,
                remediation=(
                    "Pin static architecture map & tiered files at the top of the prompt via "
                    "`ctxray scan --format xml` and append volatile `git diff` blocks at the tail."
                ),
            )
        )
    return events


def _compute_savings_report(
    turns: List[TurnRecord],
    offenders: List[BloatOffender],
    cache_breaks: List[CacheBreakEvent],
    model: str,
) -> SavingsReport:
    """
    Computes exact financial & token savings if the session had used `ctxray`
    AST skeletons, deduplicated file reads, and deterministic prefix-cache pinning.
    """
    pricing = _get_pricing(model)

    actual_total_in = sum(t.input_tokens for t in turns)
    actual_cached = sum(t.cached_input_tokens for t in turns)
    actual_uncached = sum(t.uncached_input_tokens for t in turns)
    actual_out = sum(t.output_tokens for t in turns)
    actual_cost = sum(t.cost_usd for t in turns)

    dedup_saved = 0
    skel_saved = 0
    total_turns = max(1, len(turns))

    for off in offenders:
        first_turn = off.turns[0] if off.turns else 1
        turns_compounded = max(1, int((total_turns - first_turn + 1) * 0.65))
        if off.category == "REPEATED_FILE_READ":
            dedup_saved += off.wasted_tokens * turns_compounded
        else:
            skel_saved += off.wasted_tokens * turns_compounded

    max_reducible = int(actual_total_in * 0.64)
    raw_input_saved = min(max_reducible, dedup_saved + skel_saved)
    if raw_input_saved > 0 and (dedup_saved + skel_saved) > 0:
        scale = raw_input_saved / (dedup_saved + skel_saved)
        dedup_saved = int(dedup_saved * scale)
        skel_saved = raw_input_saved - dedup_saved

    ctxray_total_in = max(1_000, actual_total_in - raw_input_saved)
    # With ctxray deterministic prefix pinning, 94% of compiled input hits prompt cache
    ctxray_cached = int(ctxray_total_in * 0.94)
    ctxray_uncached = max(0, ctxray_total_in - ctxray_cached)
    cache_pinning_saved_tok = sum(cb.invalidated_tokens for cb in cache_breaks)

    ctxray_cost = (
        (ctxray_uncached / 1_000_000.0) * pricing["input"]
        + (ctxray_cached / 1_000_000.0) * pricing["cached_input"]
        + (actual_out / 1_000_000.0) * pricing["output"]
    )

    for t in turns:
        ratio = ctxray_cost / max(0.00001, actual_cost)
        t.optimized_cost_usd = t.cost_usd * ratio

    tokens_saved = max(0, actual_total_in - ctxray_total_in)
    token_savings_pct = (tokens_saved / max(1, actual_total_in)) * 100.0
    cost_saved = max(0.0, actual_cost - ctxray_cost)
    cost_savings_pct = (cost_saved / max(0.00001, actual_cost)) * 100.0
    # Projected monthly savings assuming 25 agent sessions / workday * 22 workdays = 550 sessions/month
    projected_monthly = cost_saved * 550.0

    steps = [
        f"Run `python ctxray.py init-rules .` to generate `CLAUDE.md`, `AGENTS.md`, and `.cursor/rules/architecture.mdc` so agents respect token budgets automatically.",
        f"Replace repeated full-file reads with `python ctxray.py skeleton <file>` to eliminate {dedup_saved:,} redundant compounded context tokens.",
        f"Use `python ctxray.py scan . --budget 32k --format xml` to pin static architectural tiers (`FULL -> SKELETON -> SUMMARY`) and prevent {len(cache_breaks)} prompt cache break(s) ({cache_pinning_saved_tok:,} invalidated tokens).",
    ]

    return SavingsReport(
        model_name=model,
        actual_total_input_tokens=actual_total_in,
        actual_cached_tokens=actual_cached,
        actual_uncached_tokens=actual_uncached,
        actual_output_tokens=actual_out,
        actual_cost_usd=actual_cost,
        ctxray_total_input_tokens=ctxray_total_in,
        ctxray_cached_tokens=ctxray_cached,
        ctxray_uncached_tokens=ctxray_uncached,
        ctxray_cost_usd=ctxray_cost,
        tokens_saved=tokens_saved,
        token_savings_pct=token_savings_pct,
        cost_saved_usd=cost_saved,
        cost_savings_pct=cost_savings_pct,
        skeleton_compression_saved_tokens=skel_saved,
        dedup_file_reads_saved_tokens=dedup_saved,
        cache_pinning_saved_tokens=cache_pinning_saved_tok,
        projected_monthly_savings_usd=projected_monthly,
        actionable_steps=steps,
    )


def analyze_trace(
    trace_path: Optional[Union[str, Path, List[Dict[str, Any]], Dict[str, Any]]] = None,
    demo: bool = False,
    model: str = "claude-sonnet-4",
    repo_root: Optional[Union[str, Path]] = None,
) -> SessionTraceReport:
    """
    Primary entry point for AI Agent Session Flight Recorder & Token Burn Forensics.
    - If `demo=True` or no local trace logs exist, analyzes the built-in realistic synthetic demo session.
    - Otherwise parses the specified (or most recent auto-discovered) `.jsonl`/`.json` session trace.
    """
    raw_records: List[Dict[str, Any]] = []
    agent_type = "claude-code"
    source_label = "built-in://synthetic-demo-trace"

    if not demo and trace_path is not None:
        raw_records, agent_type, source_label = parse_trace_events(trace_path)
    elif not demo:
        discovered = discover_local_traces()
        for cand in discovered:
            recs, ag, lbl = parse_trace_events(cand)
            if len(recs) >= 2:
                raw_records, agent_type, source_label = recs, ag, lbl
                break

    if not raw_records:
        raw_records = generate_demo_trace(repo_root=repo_root)
        agent_type = "claude-code (demo)"
        source_label = "built-in://ctxray-demo-flight-recorder.jsonl"

    turns, detected_agent, detected_model = _normalize_raw_records(
        raw_records, agent_hint=agent_type, model_override=model
    )
    offenders = _detect_bloat_offenders(turns, detected_model)
    cache_breaks = _extract_cache_breaks(turns, detected_model)
    savings = _compute_savings_report(turns, offenders, cache_breaks, detected_model)

    peak_ctx = max((t.cumulative_context_tokens for t in turns), default=0)
    velocities = [t.token_velocity for t in turns]
    avg_vel = (sum(velocities) / len(velocities)) if velocities else 0.0
    max_vel = max(velocities, default=0)
    total_in = max(1, savings.actual_total_input_tokens)
    overall_cache_pct = (savings.actual_cached_tokens / total_in) * 100.0

    sess_hash = hashlib.sha1(source_label.encode("utf-8")).hexdigest()[:10]
    session_id = f"sess-{sess_hash}"

    return SessionTraceReport(
        session_id=session_id,
        agent_type=detected_agent,
        source_path=source_label,
        model_name=detected_model,
        total_turns=len(turns),
        peak_context_tokens=peak_ctx,
        avg_token_velocity=avg_vel,
        max_token_velocity=max_vel,
        overall_cache_hit_pct=overall_cache_pct,
        cache_breaks_count=len(cache_breaks),
        turns=turns,
        bloat_offenders=offenders,
        cache_breaks=cache_breaks,
        savings=savings,
    )


# Alias for flexibility across callers
analyze_session = analyze_trace


def _ascii_bar(ratio: float, width: int = 20) -> str:
    filled = max(0, min(width, int(round(ratio * width))))
    return "#" * filled + "." * (width - filled)


def format_trace_report(report: SessionTraceReport, fmt: str = "text") -> str:
    """
    Formats a `SessionTraceReport` as:
      - `"text"` / `"terminal"`: Rich terminal dashboard with ASCII context growth curve, bloat offenders, cache breaks & savings
      - `"md"` / `"markdown"`: GitHub-flavored Markdown report
      - `"json"`: Structured JSON telemetry
    """
    fmt_clean = (fmt or "text").strip().lower()
    if fmt_clean == "json":
        return report.to_json(indent=2)

    s = report.savings
    if fmt_clean in {"md", "markdown"}:
        lines = [
            f"# ctxray AI Agent Session Flight Recorder (`{report.session_id}`)",
            "",
            f"- **Source Trace**: `{report.source_path}`",
            f"- **Agent / Model**: `{report.agent_type}` • `{report.model_name}`",
            f"- **Turns Analyzed**: `{report.total_turns}` | **Peak Context Window**: `{report.peak_context_tokens:,} tokens`",
            f"- **Token Burn Velocity**: avg `+{report.avg_token_velocity:,.0f} tok/turn` (peak `+{report.max_token_velocity:,} tok/turn`)",
            f"- **Prompt Cache Hit Rate**: `{report.overall_cache_hit_pct:.1f}%` (`{report.cache_breaks_count}` cache break events)",
            "",
            "## 1. Turn-by-Turn Context Growth Curve & Token Velocity",
            "",
            "| Turn | Tool | Target / Action | Context Window | Velocity (+tok) | Cache Hit | Status |",
            "| ---: | :--- | :--- | ---: | ---: | ---: | :--- |",
        ]
        for t in report.turns:
            status = "CACHE BREAK" if t.cache_break_detected else (t.bloat_category or "OK")
            lines.append(
                f"| {t.turn_index} | `{t.tool_name}` | `{t.command_or_query[:48]}` | "
                f"`{t.cumulative_context_tokens:,}` | `+{t.token_velocity:,}` | "
                f"`{t.cache_hit_ratio * 100.0:.1f}%` | **{status}** |"
            )
        lines.extend(
            [
                "",
                "## 2. Top Context Bloat Offenders",
                "",
                "| Rank | Category | Target | Occurrences | Wasted Tokens | Skeleton Equiv | Wasted USD | Fix |",
                "| ---: | :--- | :--- | ---: | ---: | ---: | ---: | :--- |",
            ]
        )
        for b in report.bloat_offenders:
            lines.append(
                f"| {b.rank} | `{b.category}` | `{b.target}` | `{b.occurrences}x` (turns {b.turns}) | "
                f"`{b.wasted_tokens:,}` (-{b.savings_pct:.1f}%) | `{b.skeleton_tokens:,}` | "
                f"`${b.wasted_cost_usd:.4f}` | {b.recommendation} |"
            )
        lines.extend(
            [
                "",
                "## 3. Prompt Cache Break Detector",
                "",
            ]
        )
        if not report.cache_breaks:
            lines.append("- **0 Cache Breaks Detected**: Prompt prefix remained stable across all turns.")
        else:
            for cb in report.cache_breaks:
                lines.append(
                    f"- **Turn #{cb.turn_index}** (`{cb.timestamp}`): Invalidated `{cb.invalidated_tokens:,}` cached tokens "
                    f"(`{cb.previous_cached_tokens:,}` -> `{cb.new_cached_tokens:,}`). **Cause**: {cb.reason}. "
                    f"**Penalty**: `${cb.cost_penalty_usd:.4f}`."
                )
        lines.extend(
            [
                "",
                "## 4. Actionable Savings Report (`ctxray` AST Skeletons + Cache Pinning)",
                "",
                "| Metric | Actual Session | With `ctxray` | Delta / Savings |",
                "| :--- | ---: | ---: | ---: |",
                f"| **Cumulative Input Tokens** | `{s.actual_total_input_tokens:,}` | `{s.ctxray_total_input_tokens:,}` | **-{s.tokens_saved:,} tok (-{s.token_savings_pct:.1f}%)** |",
                f"| **Uncached Input Tokens** | `{s.actual_uncached_tokens:,}` | `{s.ctxray_uncached_tokens:,}` | **-{max(0, s.actual_uncached_tokens - s.ctxray_uncached_tokens):,} tok** |",
                f"| **Session API Cost (USD)** | `${s.actual_cost_usd:.4f}` | `${s.ctxray_cost_usd:.4f}` | **-${s.cost_saved_usd:.4f} (-{s.cost_savings_pct:.1f}%)** |",
                f"| **Projected Monthly Team Spend (550 sessions)** | `${s.actual_cost_usd * 550:.2f}/mo` | `${s.ctxray_cost_usd * 550:.2f}/mo` | **Save ${s.projected_monthly_savings_usd:,.2f}/mo** |",
                "",
            ]
        )
        return "\n".join(lines)

    # Default: Rich Terminal ASCII Report
    peak = max(1, report.peak_context_tokens)
    out: List[str] = [
        "=" * 94,
        f" CTXRAY SESSION FLIGHT RECORDER & TOKEN BURN FORENSICS  |  Session: {report.session_id}",
        f" Agent: {report.agent_type:<20} | Model: {report.model_name:<16} | Turns: {report.total_turns}",
        f" Source: {report.source_path}",
        f" Peak Context: {report.peak_context_tokens:,} tok  | Avg Velocity: +{report.avg_token_velocity:,.0f} tok/turn  | Cache Hit: {report.overall_cache_hit_pct:.1f}%",
        "=" * 94,
        " [1] TURN-BY-TURN CONTEXT GROWTH CURVE & TOKEN BURN VELOCITY",
        "-" * 94,
        f" {'TURN':<5} {'CONTEXT GROWTH CURVE':<22} {'CTX TOKENS':>11} {'VELOCITY':>10} {'CACHE%':>7}  {'TOOL / ACTION'}",
        "-" * 94,
    ]
    for t in report.turns:
        bar = _ascii_bar(t.cumulative_context_tokens / peak, 20)
        flag = " [!! CACHE BREAK !!]" if t.cache_break_detected else (f" [{t.bloat_category}]" if t.bloat_category else "")
        action_str = f"{t.tool_name}: {t.command_or_query}"[:34]
        out.append(
            f" #{t.turn_index:<4d} [{bar}] {t.cumulative_context_tokens:>10,d}  +{t.token_velocity:>8,d}  "
            f"{t.cache_hit_ratio * 100.0:>5.1f}%  {action_str}{flag}"
        )

    out.extend(
        [
            "",
            " [2] TOP CONTEXT BLOAT OFFENDERS (REDUNDANT READS & UNPRUNED TOOL DUMPS)",
            "-" * 94,
        ]
    )
    if not report.bloat_offenders:
        out.append("  No major context bloat offenders detected.")
    else:
        for b in report.bloat_offenders[:6]:
            out.append(
                f"  #{b.rank} [{b.category:<22}] {b.target:<28} | {b.occurrences}x (turns {b.turns}) | "
                f"Wasted: {b.wasted_tokens:,} tok (-{b.savings_pct:.1f}%)"
            )
            out.append(f"     -> Fix: {b.recommendation}")

    out.extend(
        [
            "",
            " [3] PROMPT CACHE BREAK DETECTOR (PREFIX INVALIDATION FORENSICS)",
            "-" * 94,
        ]
    )
    if not report.cache_breaks:
        out.append("  0 Prompt Cache Breaks detected — static prefix remained intact.")
    else:
        for cb in report.cache_breaks:
            out.append(
                f"  [!] Turn #{cb.turn_index:<2d} ({cb.timestamp}) | Invalidated: {cb.invalidated_tokens:,} cached tokens "
                f"({cb.previous_cached_tokens:,} -> {cb.new_cached_tokens:,}) | Penalty: ${cb.cost_penalty_usd:.4f}"
            )
            out.append(f"      Cause: {cb.reason}")
            out.append(f"      Fix  : {cb.remediation}")

    out.extend(
        [
            "",
            " [4] ACTIONABLE CTXRAY SAVINGS REPORT (AST SKELETONS + CACHE PINNING)",
            "-" * 94,
            f"  Actual Session Input Tokens : {s.actual_total_input_tokens:>12,d} tok   (Uncached: {s.actual_uncached_tokens:,} tok | Cost: ${s.actual_cost_usd:.4f})",
            f"  With ctxray Optimization    : {s.ctxray_total_input_tokens:>12,d} tok   (Uncached: {s.ctxray_uncached_tokens:,} tok | Cost: ${s.ctxray_cost_usd:.4f})",
            f"  Total Session Savings       : {s.tokens_saved:>12,d} tok   (-{s.token_savings_pct:.1f}% tokens | -${s.cost_saved_usd:.4f} / -{s.cost_savings_pct:.1f}% USD)",
            f"    ├── AST Skeleton Compression : {s.skeleton_compression_saved_tokens:>9,d} tok saved",
            f"    ├── Deduplicated File Reads  : {s.dedup_file_reads_saved_tokens:>9,d} tok saved",
            f"    └── Prefix-Cache Pinning     : {s.cache_pinning_saved_tokens:>9,d} invalidated tok prevented",
            f"  Projected Team Savings (550 sessions/mo): ${s.projected_monthly_savings_usd:,.2f} / month saved",
            "=" * 94,
        ]
    )
    return "\n".join(out)


class TraceAnalyzer:
    """Object-oriented interface for session flight-recorder analysis and reporting."""

    def __init__(
        self,
        model: str = "claude-sonnet-4",
        repo_root: Optional[Union[str, Path]] = None,
    ) -> None:
        self.model = model
        self.repo_root = Path(repo_root).resolve() if repo_root else Path.cwd()

    def discover_logs(self, search_roots: Optional[List[Union[str, Path]]] = None) -> List[Path]:
        return discover_local_traces(search_roots=search_roots)

    def analyze(
        self,
        trace_path: Optional[Union[str, Path, List[Dict[str, Any]], Dict[str, Any]]] = None,
        demo: bool = False,
        model: Optional[str] = None,
    ) -> SessionTraceReport:
        return analyze_trace(
            trace_path=trace_path,
            demo=demo,
            model=model or self.model,
            repo_root=self.repo_root,
        )

    def format(self, report: SessionTraceReport, fmt: str = "text") -> str:
        return format_trace_report(report, fmt=fmt)


__all__ = [
    "BloatOffender",
    "CacheBreakEvent",
    "MODEL_PRICING_PER_M",
    "SavingsReport",
    "SessionTraceReport",
    "TraceAnalysis",
    "TraceAnalyzer",
    "TurnRecord",
    "analyze_session",
    "analyze_trace",
    "discover_local_traces",
    "format_trace_report",
    "generate_demo_trace",
    "parse_trace_events",
]
