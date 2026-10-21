"""
ctxray.parsers — Deep Polyglot Structural, Symbol, Route, Schema & Call-Graph Extractors.

Provides rich AST and structural extraction across:
- Python (FastAPI/Flask routes, Pydantic BaseModel schemas, dataclasses, Protocols, async defs, raised exceptions)
- TypeScript / JavaScript / React (export interface/type, Zod schemas, Next.js GET/POST route handlers, React hooks/components, class methods)
- Go (struct/interface definitions with struct tags, receiver methods, exported functions, HTTP handlers)
- Rust (pub struct, pub enum, pub trait, impl ... for ..., pub fn, macro_rules!, Actix/Axum routes)
- SQL / GraphQL / Protobuf (CREATE TABLE, type Query/Mutation, service/message RPC definitions)
"""

from .deep_extractors import (
    CallEdge,
    DeclarativeSchemaExtractor,
    DeepFileExtraction,
    DeepPolyglotExtractor,
    ExtractedRoute,
    ExtractedSchema,
    ExtractedSymbol,
    GoDeepExtractor,
    PythonDeepExtractor,
    RustDeepExtractor,
    TypeScriptDeepExtractor,
    build_cross_file_call_graph,
    extract_file_symbols,
    extract_repository_symbols,
)

__all__ = [
    "CallEdge",
    "DeclarativeSchemaExtractor",
    "DeepFileExtraction",
    "DeepPolyglotExtractor",
    "ExtractedRoute",
    "ExtractedSchema",
    "ExtractedSymbol",
    "GoDeepExtractor",
    "PythonDeepExtractor",
    "RustDeepExtractor",
    "TypeScriptDeepExtractor",
    "build_cross_file_call_graph",
    "extract_file_symbols",
    "extract_repository_symbols",
]
