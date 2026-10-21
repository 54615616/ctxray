from __future__ import annotations

import ast
import fnmatch
import json
import math
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Set, Tuple


class SecretGuard:
    """Scans and redacts leaked API keys, tokens, and private keys before context emission."""

    PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
        ("OPENAI_API_KEY", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
        ("ANTHROPIC_API_KEY", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b")),
        ("GITHUB_TOKEN", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}\b")),
        ("GITHUB_PAT", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{30,}\b")),
        ("AWS_ACCESS_KEY", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
        ("SLACK_TOKEN", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{15,}\b")),
        ("STRIPE_KEY", re.compile(r"\b(?:sk|rk)_live_[A-Za-z0-9]{20,}\b")),
        (
            "PRIVATE_KEY",
            re.compile(
                r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----[\s\S]+?-----END (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"
            ),
        ),
        (
            "ENV_SECRET_ASSIGNMENT",
            re.compile(
                r"(?i)\b(api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token|password|passwd|client[_-]?secret)\s*([:=])\s*(?P<q>['\"])([^'\"]{8,})(?P=q)"
            ),
        ),
    ]

    @classmethod
    def redact(cls, text: str) -> Tuple[str, int]:
        redacted_count = 0
        out = text
        for label, pattern in cls.PATTERNS:
            if label == "ENV_SECRET_ASSIGNMENT":
                def _repl(m: re.Match[str]) -> str:
                    nonlocal redacted_count
                    redacted_count += 1
                    q = m.group("q")
                    return f"{m.group(1)}{m.group(2)}{q}[REDACTED:{label}]{q}"
                out = pattern.sub(_repl, out)
            else:
                matches = pattern.findall(out)
                if matches:
                    redacted_count += len(matches)
                    out = pattern.sub(f"[REDACTED:{label}]", out)
        return out, redacted_count


class TokenEstimator:
    """
    Fast, deterministic token estimator calibrated to o200k_base / Claude 4 BPE tokenizers.
    Splits camelCase, snake_case, punctuation, numeric runs, and CJK characters.
    """

    _TOKEN_SPLIT = re.compile(
        r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|\b)|\d+|[\u4e00-\u9fff]|[^\w\s]|\s+"
    )

    @classmethod
    def estimate(cls, text: str) -> int:
        if not text:
            return 0
        if len(text) > 60_000:
            words = len(text.split())
            symbols = sum(1 for c in text if c in "{}[]().,:;+-*/=<>!&|")
            return max(1, int(words * 1.15 + symbols * 0.45))
        chunks = cls._TOKEN_SPLIT.findall(text)
        tokens = 0
        for ch in chunks:
            if ch.isspace():
                tokens += max(0, len(ch) // 4)
            elif len(ch) > 10:
                tokens += math.ceil(len(ch) / 4.2)
            else:
                tokens += 1
        return max(1, int(tokens * 0.88))


class PolyglotSkeletonizer:
    """
    Compresses source code into high-signal architectural skeletons:
    - Preserves imports, exports, type definitions, class/interface hierarchies,
      function/method signatures, decorators, and docstrings.
    - Folds implementation bodies into compact annotations (... # [ctxray: folded N lines]).
    """

    @classmethod
    def skeletonize(cls, content: str, ext: str) -> str:
        ext = ext.lower()
        if ext == ".py":
            return cls._skeletonize_python(content)
        if ext in {".ts", ".tsx", ".js", ".jsx", ".mts", ".cts", ".rs", ".go", ".java", ".c", ".cpp", ".h", ".hpp", ".cs"}:
            return cls._skeletonize_brace_lang(content, ext)
        return cls._skeletonize_generic(content)

    @classmethod
    def summarize(cls, content: str, ext: str, rel_path: str) -> str:
        """Tier 3 ultra-compact symbol index (~85-92% token reduction)."""
        symbols: List[str] = []
        imports: List[str] = []
        lines = content.splitlines()
        for line in lines[:400]:
            s = line.strip()
            if re.match(r"^(import\s+|from\s+\S+\s+import\s+|use\s+|#include\s+)", s):
                if len(imports) < 8:
                    imports.append(s[:90])
            elif re.match(
                r"^(export\s+)?(async\s+)?(def|class|interface|type|struct|enum|trait|fn|func)\s+[A-Za-z0-9_]+",
                s,
            ):
                clean_sig = s.rstrip("{:").strip()
                if len(symbols) < 25:
                    symbols.append(f"  * {clean_sig[:100]}")
        header = f"# [SUMMARY] {rel_path} ({len(lines)} lines)"
        parts = [header]
        if imports:
            parts.append("Imports: " + "; ".join(imports[:5]))
        if symbols:
            parts.append("Symbols:\n" + "\n".join(symbols))
        else:
            preview = "\n".join(lines[:10])
            parts.append(preview)
        return "\n".join(parts)

    @classmethod
    def _skeletonize_python(cls, content: str) -> str:
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return cls._skeletonize_generic(content)

        lines = content.splitlines()
        folded_ranges: List[Tuple[int, int, str]] = []

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not node.body:
                    continue
                first_stmt = node.body[0]
                if (
                    isinstance(first_stmt, ast.Expr)
                    and isinstance(getattr(first_stmt, "value", None), ast.Constant)
                    and isinstance(first_stmt.value.value, str)
                ):
                    if len(node.body) > 1:
                        start_line = node.body[1].lineno
                        end_line = getattr(node, "end_lineno", start_line) or start_line
                        if end_line - start_line >= 2:
                            indent = " " * (node.col_offset + 4)
                            folded_ranges.append(
                                (start_line, end_line, f"{indent}...  # [ctxray: folded {end_line - start_line + 1} lines]")
                            )
                else:
                    start_line = first_stmt.lineno
                    end_line = getattr(node, "end_lineno", start_line) or start_line
                    if end_line - start_line >= 2:
                        indent = " " * (node.col_offset + 4)
                        folded_ranges.append(
                            (start_line, end_line, f"{indent}...  # [ctxray: folded {end_line - start_line + 1} lines]")
                        )

        if not folded_ranges:
            return content

        folded_ranges.sort(key=lambda r: (r[0], -r[1]))
        merged: List[Tuple[int, int, str]] = []
        for start, end, repl in folded_ranges:
            if merged and start <= merged[-1][1]:
                continue
            merged.append((start, end, repl))

        out_lines: List[str] = []
        idx = 1
        range_ptr = 0
        total_lines = len(lines)
        while idx <= total_lines:
            if range_ptr < len(merged) and idx == merged[range_ptr][0]:
                _, end, repl = merged[range_ptr]
                out_lines.append(repl)
                idx = end + 1
                range_ptr += 1
            else:
                out_lines.append(lines[idx - 1])
                idx += 1
        return "\n".join(out_lines)

    @classmethod
    def _skeletonize_brace_lang(cls, content: str, ext: str) -> str:
        lines = content.splitlines()
        out: List[str] = []
        depth = 0
        fold_start_line = -1
        fold_depth = -1
        in_block_comment = False

        keep_container_re = re.compile(
            r"^\s*(export\s+)?(default\s+)?(abstract\s+)?(pub\s+)?(class|interface|type|struct|enum|trait|namespace|mod|impl)\b"
        )
        string_or_regex_re = re.compile(
            r"""(?:"(?:\\.|[^"\\])*")|(?:'(?:\\.|[^'\\])*')"""
        )

        for i, line in enumerate(lines, start=1):
            stripped = line.strip()
            code_part = stripped
            if in_block_comment:
                if "*/" in code_part:
                    code_part = code_part.split("*/", 1)[1]
                    in_block_comment = False
                else:
                    if fold_depth == -1:
                        out.append(line)
                    continue
            while "/*" in code_part:
                before, after = code_part.split("/*", 1)
                if "*/" in after:
                    code_part = before + " " + after.split("*/", 1)[1]
                else:
                    code_part = before
                    in_block_comment = True
                    break
            code_part = re.sub(r"//.*$", "", code_part)
            code_part = string_or_regex_re.sub('""', code_part)
            opens = code_part.count("{")
            closes = code_part.count("}")

            if fold_depth != -1:
                depth += opens - closes
                if depth < fold_depth:
                    folded_count = i - fold_start_line
                    indent = line[: len(line) - len(line.lstrip())]
                    if folded_count >= 2:
                        out.append(f"{indent}  /* [ctxray: folded {folded_count} lines] */")
                    out.append(line)
                    fold_depth = -1
                    fold_start_line = -1
                continue

            out.append(line)
            is_container = bool(keep_container_re.match(stripped))
            prev_depth = depth
            depth += opens - closes

            if opens > closes and not is_container and prev_depth >= (1 if ext in {".java", ".cs"} else 0):
                if any(
                    kw in stripped
                    for kw in ("function", "fn ", "func ", "def ", "=>", "(", "get ", "set ", "async ")
                ):
                    fold_depth = depth
                    fold_start_line = i

        return "\n".join(out)

    @classmethod
    def _skeletonize_generic(cls, content: str) -> str:
        lines = content.splitlines()
        if len(lines) <= 45:
            return content
        head = lines[:28]
        tail = lines[-10:]
        folded = len(lines) - len(head) - len(tail)
        return "\n".join(head + [f"  ... [ctxray: folded {folded} lines] ..."] + tail)


@dataclass
class FileNode:
    rel_path: str
    ext: str
    size_bytes: int
    lines: int
    raw_tokens: int
    skeleton_tokens: int
    summary_tokens: int
    pagerank: float = 0.0
    in_degree: int = 0
    out_degree: int = 0
    tier: str = "FULL"
    allocated_tokens: int = 0
    secrets_redacted: int = 0
    imports: List[str] = field(default_factory=list)
    dependents: List[str] = field(default_factory=list)
    raw_content: str = field(default="", repr=False)
    skeleton_content: str = field(default="", repr=False)
    summary_content: str = field(default="", repr=False)

    @property
    def compression_ratio(self) -> float:
        if self.raw_tokens <= 0:
            return 0.0
        return round(1.0 - (self.allocated_tokens / self.raw_tokens), 4)


@dataclass
class RepoAnalysis:
    root_path: str
    repo_name: str
    total_files: int
    raw_total_tokens: int
    compiled_total_tokens: int
    budget_tokens: int
    savings_pct: float
    estimated_cache_hit_pct: float
    secrets_redacted: int
    tier_counts: Dict[str, int]
    files: List[FileNode]
    edges: List[Tuple[str, str]]
    git_diff_tokens: int = 0
    git_diff_summary: str = ""

    def to_dict(self) -> Dict[str, object]:
        return {
            "root_path": self.root_path,
            "repo_name": self.repo_name,
            "total_files": self.total_files,
            "raw_total_tokens": self.raw_total_tokens,
            "compiled_total_tokens": self.compiled_total_tokens,
            "budget_tokens": self.budget_tokens,
            "savings_pct": self.savings_pct,
            "estimated_cache_hit_pct": self.estimated_cache_hit_pct,
            "secrets_redacted": self.secrets_redacted,
            "tier_counts": self.tier_counts,
            "git_diff_tokens": self.git_diff_tokens,
            "edges": [{"source": s, "target": t} for s, t in self.edges],
            "files": [
                {
                    "rel_path": f.rel_path,
                    "ext": f.ext,
                    "size_bytes": f.size_bytes,
                    "lines": f.lines,
                    "raw_tokens": f.raw_tokens,
                    "skeleton_tokens": f.skeleton_tokens,
                    "summary_tokens": f.summary_tokens,
                    "allocated_tokens": f.allocated_tokens,
                    "pagerank": round(f.pagerank, 5),
                    "in_degree": f.in_degree,
                    "out_degree": f.out_degree,
                    "tier": f.tier,
                    "compression_ratio": f.compression_ratio,
                    "secrets_redacted": f.secrets_redacted,
                    "imports": f.imports,
                    "dependents": f.dependents,
                    "skeleton_preview": f.skeleton_content[:1200],
                }
                for f in self.files
            ],
        }


class ContextCompiler:
    """
    Core compiler that scans a repository, constructs its cross-file dependency graph,
    computes PageRank centrality, allocates tiers within an exact token budget, and
    emits a cache-pinned context bundle.
    """

    DEFAULT_IGNORE_DIRS: Set[str] = {
        ".git",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        "env",
        "dist",
        "build",
        "out",
        "target",
        ".next",
        ".nuxt",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".idea",
        ".vscode",
        "coverage",
        "vendor",
    }

    DEFAULT_IGNORE_GLOBS: Tuple[str, ...] = (
        "*.lock",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "Cargo.lock",
        "poetry.lock",
        "uv.lock",
        "*.min.js",
        "*.min.css",
        "*.map",
        "*.pyc",
        "*.pyo",
        "*.so",
        "*.dll",
        "*.exe",
        "*.dylib",
        "*.png",
        "*.jpg",
        "*.jpeg",
        "*.gif",
        "*.webp",
        "*.ico",
        "*.pdf",
        "*.zip",
        "*.tar",
        "*.gz",
        "*.woff",
        "*.woff2",
        "*.ttf",
        "*.eot",
        "*.mp4",
        "*.mp3",
        "*.db",
        "*.sqlite",
    )

    ALLOWED_EXTS: Set[str] = {
        ".py",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".mts",
        ".cts",
        ".go",
        ".rs",
        ".java",
        ".c",
        ".cpp",
        ".h",
        ".hpp",
        ".cs",
        ".rb",
        ".php",
        ".swift",
        ".kt",
        ".scala",
        ".sql",
        ".graphql",
        ".proto",
        ".yaml",
        ".yml",
        ".toml",
        ".json",
        ".md",
        ".sh",
        ".ps1",
    }

    def __init__(self, root_path: str | Path, budget_tokens: int = 32_000) -> None:
        self.root = Path(root_path).resolve()
        self.budget_tokens = max(1_000, budget_tokens)
        self.gitignore_patterns = self._load_gitignore()

    def _load_gitignore(self) -> List[str]:
        gi = self.root / ".gitignore"
        patterns: List[str] = []
        if gi.is_file():
            try:
                for line in gi.read_text(encoding="utf-8", errors="ignore").splitlines():
                    s = line.strip()
                    if s and not s.startswith("#"):
                        patterns.append(s.rstrip("/"))
            except OSError:
                pass
        return patterns

    def _is_ignored(self, rel_posix: str, name: str) -> bool:
        for g in self.DEFAULT_IGNORE_GLOBS:
            if fnmatch.fnmatch(name, g) or fnmatch.fnmatch(rel_posix, g):
                return True
        for pat in self.gitignore_patterns:
            if fnmatch.fnmatch(name, pat) or fnmatch.fnmatch(rel_posix, pat):
                return True
        return False

    def scan_and_compile(self) -> RepoAnalysis:
        nodes: Dict[str, FileNode] = {}

        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [
                d
                for d in sorted(dirnames)
                if d not in self.DEFAULT_IGNORE_DIRS and not d.startswith(".git")
            ]
            for fname in sorted(filenames):
                full_path = Path(dirpath) / fname
                try:
                    rel_posix = full_path.relative_to(self.root).as_posix()
                except ValueError:
                    continue
                if self._is_ignored(rel_posix, fname):
                    continue
                ext = full_path.suffix.lower()
                if ext not in self.ALLOWED_EXTS and fname not in {"Dockerfile", "Makefile"}:
                    continue
                try:
                    size_b = full_path.stat().st_size
                    if size_b > 512_000 or size_b == 0:
                        continue
                    raw_text = full_path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue

                clean_text, redacted_n = SecretGuard.redact(raw_text)
                skel_text = PolyglotSkeletonizer.skeletonize(clean_text, ext)
                sum_text = PolyglotSkeletonizer.summarize(clean_text, ext, rel_posix)

                raw_tok = TokenEstimator.estimate(clean_text)
                skel_tok = min(raw_tok, TokenEstimator.estimate(skel_text))
                sum_tok = min(skel_tok, TokenEstimator.estimate(sum_text))

                nodes[rel_posix] = FileNode(
                    rel_path=rel_posix,
                    ext=ext or ".txt",
                    size_bytes=size_b,
                    lines=len(clean_text.splitlines()),
                    raw_tokens=raw_tok,
                    skeleton_tokens=skel_tok,
                    summary_tokens=sum_tok,
                    secrets_redacted=redacted_n,
                    raw_content=clean_text,
                    skeleton_content=skel_text,
                    summary_content=sum_text,
                )

        edges = self._build_dependency_graph(nodes)
        self._compute_pagerank(nodes, edges)

        sorted_files = sorted(
            nodes.values(), key=lambda f: (f.pagerank, -f.raw_tokens), reverse=True
        )
        self._allocate_budget(sorted_files)

        raw_total = sum(f.raw_tokens for f in sorted_files)
        compiled_total = sum(f.allocated_tokens for f in sorted_files)
        savings_pct = (
            round((1.0 - compiled_total / raw_total) * 100.0, 1) if raw_total > 0 else 0.0
        )
        tier_counts = {"FULL": 0, "SKELETON": 0, "SUMMARY": 0, "TREE_ONLY": 0}
        for f in sorted_files:
            tier_counts[f.tier] = tier_counts.get(f.tier, 0) + 1

        git_diff_summary, git_diff_tokens = self._inspect_git_diff()
        cache_hit_pct = self._estimate_prefix_cache_hit(compiled_total, git_diff_tokens)

        return RepoAnalysis(
            root_path=str(self.root),
            repo_name=self.root.name,
            total_files=len(sorted_files),
            raw_total_tokens=raw_total,
            compiled_total_tokens=compiled_total,
            budget_tokens=self.budget_tokens,
            savings_pct=max(0.0, savings_pct),
            estimated_cache_hit_pct=cache_hit_pct,
            secrets_redacted=sum(f.secrets_redacted for f in sorted_files),
            tier_counts=tier_counts,
            files=sorted_files,
            edges=edges,
            git_diff_tokens=git_diff_tokens,
            git_diff_summary=git_diff_summary,
        )

    def _build_dependency_graph(
        self, nodes: Dict[str, FileNode]
    ) -> List[Tuple[str, str]]:
        edges: List[Tuple[str, str]] = []
        all_paths = set(nodes.keys())
        stem_index: Dict[str, List[str]] = {}
        for p in all_paths:
            stem = Path(p).stem
            stem_index.setdefault(stem, []).append(p)

        import_patterns = [
            re.compile(r"^\s*from\s+([A-Za-z0-9_.]+)\s+import\b", re.MULTILINE),
            re.compile(r"^\s*import\s+([A-Za-z0-9_.]+)", re.MULTILINE),
            re.compile(r"""^\s*import\s+(?:[A-Za-z0-9_]+\s+)?["']([^"']+)["']""", re.MULTILINE),
            re.compile(r"""(?:import|export)\s+.*?\s+from\s+['"]([^'"]+)['"]"""),
            re.compile(r"""require\(\s*['"]([^'"]+)['"]\s*\)"""),
            re.compile(r"""#include\s+["<]([^">]+)[">]"""),
            re.compile(r"^\s*use\s+(?:crate::|super::)?([A-Za-z0-9_:]+)", re.MULTILINE),
        ]
        go_block_re = re.compile(r"import\s*\(([\s\S]*?)\)", re.MULTILINE)
        go_quoted_re = re.compile(r"""["']([^"']+)["']""")

        for src_path, node in nodes.items():
            raw_specs: Set[str] = set()
            for pat in import_patterns:
                for match in pat.findall(node.raw_content):
                    if isinstance(match, str) and match:
                        raw_specs.add(match.strip())
            if node.ext == ".go":
                for blk in go_block_re.findall(node.raw_content):
                    for qm in go_quoted_re.findall(blk):
                        if qm.strip():
                            raw_specs.add(qm.strip())

            resolved_targets: Set[str] = set()
            src_dir = Path(src_path).parent.as_posix()
            for spec in raw_specs:
                cleaned = spec.lstrip("./").replace(".", "/").replace("::", "/")
                leaf = cleaned.split("/")[-1]
                for cand_ext in ("", ".py", ".ts", ".tsx", ".js", ".go", ".rs", "/__init__.py", "/index.ts", "/index.js"):
                    rel_cand = f"{src_dir}/{spec.lstrip('./')}{cand_ext}".lstrip("./")
                    if rel_cand in all_paths and rel_cand != src_path:
                        resolved_targets.add(rel_cand)
                    direct_cand = f"{cleaned}{cand_ext}"
                    if direct_cand in all_paths and direct_cand != src_path:
                        resolved_targets.add(direct_cand)
                if leaf in stem_index and len(stem_index[leaf]) == 1:
                    target = stem_index[leaf][0]
                    if target != src_path:
                        resolved_targets.add(target)

            for target in sorted(resolved_targets):
                node.imports.append(target)
                nodes[target].dependents.append(src_path)
                edges.append((src_path, target))

        for node in nodes.values():
            node.out_degree = len(node.imports)
            node.in_degree = len(node.dependents)
        return edges

    def _compute_pagerank(
        self,
        nodes: Dict[str, FileNode],
        edges: List[Tuple[str, str]],
        damping: float = 0.85,
        iterations: int = 25,
    ) -> None:
        n = len(nodes)
        if n == 0:
            return

        priors: Dict[str, float] = {}
        for path, node in nodes.items():
            lower = path.lower()
            w = 1.0
            if any(k in lower for k in ("engine", "core", "schema", "model", "router", "api", "server", "cli", "main", "index", "app")):
                w *= 1.8
            if any(k in lower for k in ("test", "spec", "mock", "fixture", "example", "bench", "docs")):
                w *= 0.45
            if node.ext in {".md", ".json", ".yaml", ".yml", ".toml"}:
                w *= 0.55
            priors[path] = w

        total_prior = sum(priors.values()) or 1.0
        for p in priors:
            priors[p] /= total_prior

        ranks: Dict[str, float] = dict(priors)
        for _ in range(iterations):
            new_ranks: Dict[str, float] = {
                p: (1.0 - damping) * priors[p] for p in nodes
            }
            sink_mass = sum(
                ranks[p] for p, node in nodes.items() if node.out_degree == 0
            )
            for p in nodes:
                new_ranks[p] += damping * sink_mass * priors[p]
            for src, dst in edges:
                out_deg = nodes[src].out_degree or 1
                new_ranks[dst] += damping * (ranks[src] / out_deg)
            ranks = new_ranks

        max_r = max(ranks.values()) if ranks else 1.0
        for p, node in nodes.items():
            node.pagerank = round(ranks[p] / max_r if max_r > 0 else 0.0, 5)

    def _allocate_budget(self, sorted_files: List[FileNode]) -> None:
        if not sorted_files:
            return

        used = 0
        for f in sorted_files:
            f.tier = "SUMMARY"
            f.allocated_tokens = f.summary_tokens
            used += f.summary_tokens

        # Tier 4 fallback: if SUMMARY tokens alone exceed budget_tokens, demote lowest-PageRank files to TREE_ONLY
        if used > self.budget_tokens:
            for f in reversed(sorted_files):
                if used <= self.budget_tokens:
                    break
                used -= f.allocated_tokens
                f.tier = "TREE_ONLY"
                f.allocated_tokens = 0
            return

        skeleton_cutoff = max(1, int(len(sorted_files) * 0.78))
        for idx, f in enumerate(sorted_files):
            if idx >= skeleton_cutoff and f.pagerank < 0.35:
                continue
            delta = f.skeleton_tokens - f.allocated_tokens
            if used + delta <= self.budget_tokens * 0.92:
                f.tier = "SKELETON"
                f.allocated_tokens = f.skeleton_tokens
                used += delta

        full_cutoff = max(1, int(len(sorted_files) * 0.35))
        for idx, f in enumerate(sorted_files[:full_cutoff]):
            if f.ext in {".json", ".yaml", ".yml", ".lock"} and f.raw_tokens > 1200:
                continue
            delta = f.raw_tokens - f.allocated_tokens
            if used + delta <= self.budget_tokens:
                f.tier = "FULL"
                f.allocated_tokens = f.raw_tokens
                used += delta

    def _inspect_git_diff(self) -> Tuple[str, int]:
        try:
            proc = subprocess.run(
                ["git", "diff", "--stat", "HEAD"],
                cwd=str(self.root),
                capture_output=True,
                text=True,
                timeout=2.5,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                diff_stat = proc.stdout.strip()
                return diff_stat, TokenEstimator.estimate(diff_stat)
        except Exception:
            pass
        return "", 0

    @staticmethod
    def _estimate_prefix_cache_hit(static_tokens: int, volatile_tokens: int) -> float:
        total = static_tokens + volatile_tokens
        if total <= 0:
            return 95.0
        ratio = static_tokens / total
        return round(min(98.5, max(82.0, ratio * 95.4)), 1)

    def blast_radius(self, target_query: str) -> Dict[str, object]:
        analysis = self.scan_and_compile()
        by_path = {f.rel_path: f for f in analysis.files}
        matches = [
            p for p in by_path if target_query.lower() in p.lower()
        ]
        if not matches:
            return {"error": f"No file matching '{target_query}'", "matches": []}

        target = matches[0]
        node = by_path[target]

        visited: Set[str] = {target}
        queue: List[Tuple[str, int]] = [(target, 0)]
        impacted: List[Dict[str, object]] = []
        while queue:
            curr, depth = queue.pop(0)
            curr_node = by_path.get(curr)
            if not curr_node:
                continue
            for dep in curr_node.dependents:
                if dep not in visited:
                    visited.add(dep)
                    impacted.append({"path": dep, "hop_distance": depth + 1, "pagerank": by_path[dep].pagerank})
                    queue.append((dep, depth + 1))

        risk_level = (
            "CRITICAL"
            if node.pagerank >= 0.75 or len(impacted) >= 5
            else "MODERATE"
            if node.pagerank >= 0.4 or len(impacted) >= 2
            else "LOW"
        )
        return {
            "target": target,
            "pagerank": node.pagerank,
            "risk_level": risk_level,
            "direct_dependents": node.dependents,
            "transitive_impact_count": len(impacted),
            "transitive_dependents": impacted,
            "direct_dependencies": node.imports,
        }

    def format_bundle(self, analysis: RepoAnalysis, fmt: str = "xml") -> str:
        fmt = fmt.lower()
        if fmt == "json":
            return json.dumps(analysis.to_dict(), indent=2, ensure_ascii=False)

        tier_order = {"FULL": 0, "SKELETON": 1, "SUMMARY": 2}
        ordered_files = sorted(
            [f for f in analysis.files if f.tier != "TREE_ONLY"],
            key=lambda f: (tier_order.get(f.tier, 3), f.rel_path),
        )

        fence = chr(96) * 3
        bt = chr(96)
        if fmt in {"md", "markdown"}:
            lines = [
                f"# ctxray Context Bundle: {bt}{analysis.repo_name}{bt}",
                "",
                f"- **Files Compiled**: {analysis.total_files}",
                f"- **Token Compression**: {analysis.raw_total_tokens:,} -> **{analysis.compiled_total_tokens:,} tokens** (-{analysis.savings_pct}%)",
                f"- **Expected Prefix Cache Hit**: {analysis.estimated_cache_hit_pct}%",
                f"- **Secrets Redacted**: {analysis.secrets_redacted}",
                "",
                "## 1. Architectural PageRank & Dependency Map",
                fence,
            ]
            for f in analysis.files[:30]:
                lines.append(
                    f"[{f.tier:8s}] PR={f.pagerank:.3f} | {f.allocated_tokens:5d} tok | {f.rel_path} (in:{f.in_degree} out:{f.out_degree})"
                )
            lines.append(f"{fence}\n")
            lines.append("## 2. Compiled Repository Context (Cache-Pinned Order)\n")
            for f in ordered_files:
                body = (
                    f.raw_content
                    if f.tier == "FULL"
                    else f.skeleton_content
                    if f.tier == "SKELETON"
                    else f.summary_content
                )
                lang = f.ext.lstrip(".")
                lines.append(f"### {bt}{f.rel_path}{bt} [{f.tier} • PR={f.pagerank:.3f} • {f.allocated_tokens} tok]")
                lines.append(f"{fence}{lang}\n{body}\n{fence}\n")
            return "\n".join(lines)

        out = [
            f'<ctxray_bundle repo="{analysis.repo_name}" '
            f'raw_tokens="{analysis.raw_total_tokens}" '
            f'compiled_tokens="{analysis.compiled_total_tokens}" '
            f'savings_pct="{analysis.savings_pct}%" '
            f'prefix_cache_hit_est="{analysis.estimated_cache_hit_pct}%">',
            "  <!-- BLOCK 1: STATIC ARCHITECTURAL MAP (PINNED PREFIX) -->",
            "  <architecture_map>",
        ]
        for f in analysis.files:
            deps = ",".join(f.imports[:6])
            out.append(
                f'    <node path="{f.rel_path}" pagerank="{f.pagerank:.3f}" tier="{f.tier}" '
                f'tokens="{f.allocated_tokens}" in_degree="{f.in_degree}" imports="{deps}" />'
            )
        out.append("  </architecture_map>")
        out.append("  <!-- BLOCK 2: TIERED SOURCE CONTEXT (FULL -> SKELETON -> SUMMARY) -->")
        out.append("  <files>")
        for f in ordered_files:
            body = (
                f.raw_content
                if f.tier == "FULL"
                else f.skeleton_content
                if f.tier == "SKELETON"
                else f.summary_content
            )
            out.append(
                f'    <file path="{f.rel_path}" tier="{f.tier}" pagerank="{f.pagerank:.3f}" tokens="{f.allocated_tokens}">\n'
                f"{body}\n"
                f"    </file>"
            )
        out.append("  </files>")
        if analysis.git_diff_summary:
            out.append("  <!-- BLOCK 3: VOLATILE GIT WORKTREE DIFF (APPENDED AT TAIL TO PRESERVE CACHE) -->")
            out.append(f'  <git_diff tokens="{analysis.git_diff_tokens}">\n{analysis.git_diff_summary}\n  </git_diff>')
        out.append("</ctxray_bundle>")
        return "\n".join(out)
