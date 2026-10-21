"""
ctxray — Visual Context Compiler, Dependency PageRank & AST Skeletonizer for AI Engineering.
Zero-dependency CLI, Python SDK, MCP Server & Interactive X-Ray Studio.
"""

__version__ = "1.0.0"
__author__ = "ctxray contributors"

from .engine import (
    ContextCompiler,
    FileNode,
    PolyglotSkeletonizer,
    RepoAnalysis,
    SecretGuard,
    TokenEstimator,
)
from .exporters import PayloadExporter
from .graph import ArchitecturalForensicsEngine, run_forensics_report
from .parsers import DeepPolyglotExtractor, extract_file_symbols, extract_repository_symbols
from .rules_generator import RulesGenerator, write_all_rules
from .trace_analyzer import TraceAnalyzer, analyze_trace, format_trace_report

__all__ = [
    "__version__",
    "ContextCompiler",
    "FileNode",
    "PolyglotSkeletonizer",
    "RepoAnalysis",
    "SecretGuard",
    "TokenEstimator",
    "PayloadExporter",
    "ArchitecturalForensicsEngine",
    "run_forensics_report",
    "DeepPolyglotExtractor",
    "extract_file_symbols",
    "extract_repository_symbols",
    "RulesGenerator",
    "write_all_rules",
    "TraceAnalyzer",
    "analyze_trace",
    "format_trace_report",
]
