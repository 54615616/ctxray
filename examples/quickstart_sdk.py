#!/usr/bin/env python3
"""ctxray Python SDK Quickstart: Programmatic compilation, skeletonization & secret redaction."""

from pathlib import Path
from ctxray import ContextCompiler, PolyglotSkeletonizer, SecretGuard


def build_agent_context(repo_dir: str | Path, budget_tokens: int = 16_000) -> str:
    # 1. Pre-flight secret & high-entropy token redaction via SecretGuard
    raw_config = 'STRIPE_LIVE_SECRET = "sk_test_demo_sample_000000000000"'
    sanitized_config, redacted_count = SecretGuard.redact(raw_config)
    print(f"[SecretGuard] Redacted {redacted_count} secret(s): {sanitized_config}")

    # 2. Direct AST/lexical skeletonization for dependency-neighborhood modules
    sample_module = (
        "class RateLimiterMiddleware:\n"
        '    """Token-bucket rate limiter protecting payment endpoints."""\n'
        "    def allow_request(self, tenant_id: str, cost: float = 1.0) -> bool:\n"
        "        bucket = self._load_bucket(tenant_id)\n"
        "        if bucket.remaining < cost:\n"
        "            return False\n"
        "        return bucket.consume(cost)\n"
    )
    skeleton = PolyglotSkeletonizer.skeletonize(sample_module, ext=".py")
    print(f"[PolyglotSkeletonizer] Tier-2 AST Skeleton:\n{skeleton}\n")

    # 3. Full PageRank + budget-aware repository compilation for an AI agent turn
    compiler = ContextCompiler(root_path=repo_dir, budget_tokens=budget_tokens)
    analysis = compiler.scan_and_compile()
    blast = compiler.blast_radius(analysis.files[0].rel_path) if analysis.files else {}

    print(
        f"[ContextCompiler] Repo={analysis.repo_name} | Files={analysis.total_files} | "
        f"Tokens: {analysis.raw_total_tokens:,} -> {analysis.compiled_total_tokens:,} "
        f"(-{analysis.savings_pct}%) | CacheHitEst={analysis.estimated_cache_hit_pct}% | "
        f"TopNodeImpact={blast.get('risk_level', 'LOW')}"
    )

    # 4. Emit prefix-stable XML bundle (Block 1: Map -> Block 2: Tiered Files -> Block 3: Diff)
    return compiler.format_bundle(analysis, fmt="xml")


if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parents[1]
    xml_bundle = build_agent_context(repo_root, budget_tokens=12_000)
    print(xml_bundle[:420] + "\n... [ctxray XML bundle ready for prefix-cached LLM call]")
