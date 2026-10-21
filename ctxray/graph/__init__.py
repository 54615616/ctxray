"""
ctxray.graph — Advanced Architectural Graph & Git Forensics Engine.

Provides:
- Tarjan's Strongly Connected Components (SCC) circular dependency detector (detect_cycles)
- Architectural Layer Classifier & Upward Layer Violation Detector (classify_layers, detect_layer_violations)
- Git Churn, Temporal Co-Change Coupling & Risk Gravity Hotspot Analyzer (analyze_git_hotspots)
- Color-Coded Mermaid Architecture Flowchart Compiler (compile_mermaid_graph)
- Unified ArchitecturalForensicsEngine & run_forensics_report
"""

from .forensics import (
    LAYER_DEFINITIONS,
    ArchitecturalForensicsEngine,
    CoChangePair,
    CycleReport,
    FileHotspot,
    ForensicsReport,
    LayerClassification,
    LayerViolation,
    analyze_git_hotspots,
    classify_layers,
    compile_mermaid_graph,
    detect_cycles,
    detect_layer_violations,
    run_forensics_report,
)

__all__ = [
    "LAYER_DEFINITIONS",
    "ArchitecturalForensicsEngine",
    "CoChangePair",
    "CycleReport",
    "FileHotspot",
    "ForensicsReport",
    "LayerClassification",
    "LayerViolation",
    "analyze_git_hotspots",
    "classify_layers",
    "compile_mermaid_graph",
    "detect_cycles",
    "detect_layer_violations",
    "run_forensics_report",
]
