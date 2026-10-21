from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


@dataclass
class ExtractedSymbol:
    """Represents a rich code symbol (function, method, class, hook, component, trait, macro, etc.)."""
    name: str
    kind: str
    signature: str
    line_start: int
    line_end: int = 0
    exported: bool = True
    is_async: bool = False
    docstring: str = ""
    decorators: List[str] = field(default_factory=list)
    bases: List[str] = field(default_factory=list)
    parameters: List[str] = field(default_factory=list)
    return_type: str = ""
    receiver: str = ""
    parent: str = ""
    raises: List[str] = field(default_factory=list)
    calls: List[str] = field(default_factory=list)
    complexity: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "signature": self.signature,
            "line_start": self.line_start,
            "line_end": self.line_end or self.line_start,
            "exported": self.exported,
            "is_async": self.is_async,
            "docstring": self.docstring,
            "decorators": self.decorators,
            "bases": self.bases,
            "parameters": self.parameters,
            "return_type": self.return_type,
            "receiver": self.receiver,
            "parent": self.parent,
            "raises": self.raises,
            "calls": self.calls,
            "complexity": self.complexity,
            "metadata": self.metadata,
        }


@dataclass
class ExtractedRoute:
    """Represents an HTTP, WebSocket, GraphQL, or gRPC route/endpoint handler."""
    method: str
    path: str
    handler_name: str
    framework: str
    line: int
    file_path: str = ""
    response_model: str = ""
    status_code: Optional[int] = None
    middlewares: List[str] = field(default_factory=list)
    summary: str = ""
    def to_dict(self) -> Dict[str, Any]:
        return {
            "method": self.method,
            "path": self.path,
            "handler_name": self.handler_name,
            "framework": self.framework,
            "line": self.line,
            "file_path": self.file_path,
            "response_model": self.response_model,
            "status_code": self.status_code,
            "middlewares": self.middlewares,
            "summary": self.summary,
        }


@dataclass
class ExtractedSchema:
    """Represents a data model, schema, interface, type alias, struct, enum, table, or protobuf message."""
    name: str
    schema_kind: str
    line_start: int
    line_end: int = 0
    fields: List[Dict[str, Any]] = field(default_factory=list)
    bases: List[str] = field(default_factory=list)
    exported: bool = True
    docstring: str = ""
    validators: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "schema_kind": self.schema_kind,
            "line_start": self.line_start,
            "line_end": self.line_end or self.line_start,
            "fields": self.fields,
            "bases": self.bases,
            "exported": self.exported,
            "docstring": self.docstring,
            "validators": self.validators,
            "metadata": self.metadata,
        }


@dataclass
class CallEdge:
    """Represents a directed invocation from a caller symbol to a callee symbol."""
    caller: str
    callee: str
    line: int
    file_path: str = ""
    call_kind: str = "direct"
    def to_dict(self) -> Dict[str, Any]:
        return {
            "caller": self.caller,
            "callee": self.callee,
            "line": self.line,
            "file_path": self.file_path,
            "call_kind": self.call_kind,
        }


@dataclass
class DeepFileExtraction:
    """Aggregated structural extraction result for a single source file."""
    rel_path: str
    language: str
    ext: str
    symbols: List[ExtractedSymbol] = field(default_factory=list)
    routes: List[ExtractedRoute] = field(default_factory=list)
    schemas: List[ExtractedSchema] = field(default_factory=list)
    call_edges: List[CallEdge] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    exports: List[str] = field(default_factory=list)
    raised_exceptions: List[str] = field(default_factory=list)
    complexity_score: int = 1
    def to_dict(self) -> Dict[str, Any]:
        return {
            "rel_path": self.rel_path,
            "language": self.language,
            "ext": self.ext,
            "complexity_score": self.complexity_score,
            "imports": self.imports,
            "exports": self.exports,
            "raised_exceptions": self.raised_exceptions,
            "counts": {
                "symbols": len(self.symbols),
                "routes": len(self.routes),
                "schemas": len(self.schemas),
                "call_edges": len(self.call_edges),
            },
            "symbols": [s.to_dict() for s in self.symbols],
            "routes": [r.to_dict() for r in self.routes],
            "schemas": [sc.to_dict() for sc in self.schemas],
            "call_edges": [ce.to_dict() for ce in self.call_edges],
        }


def _extract_balanced_block(
    text: str, open_pos: int, open_ch: str = "{", close_ch: str = "}"
) -> Tuple[str, int]:
    """
    Given text and an opening delimiter position, returns the balanced substring inside
    the delimiters and the index of the closing delimiter.
    Ignores delimiters inside single/double/backtick strings and line/block comments.
    """
    idx = text.find(open_ch, open_pos)
    if idx == -1:
        return "", -1
    depth = 0
    n = len(text)
    i = idx
    in_str: Optional[str] = None
    in_line_comment = False
    in_block_comment = False
    bt = chr(96)
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue
        if in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue
        if in_str is not None:
            if ch == "\\":
                i += 2
                continue
            if ch == in_str:
                in_str = None
            i += 1
            continue
        if ch == "/" and nxt == "/":
            in_line_comment = True
            i += 2
            continue
        if ch == "/" and nxt == "*":
            in_block_comment = True
            i += 2
            continue
        if ch in ("'", '"', bt):
            in_str = ch
            i += 1
            continue
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return text[idx + 1 : i], i
        i += 1
    return text[idx + 1 :], n - 1


def _line_number_at(text: str, char_index: int) -> int:
    if char_index <= 0:
        return 1
    return text.count("\n", 0, char_index) + 1


# =====================================================================
# 1. PYTHON AST DEEP EXTRACTOR
# =====================================================================


class PythonDeepExtractor:
    """
    AST-driven deep extractor for Python source files:
    - FastAPI / Flask / Starlette / Litestar / APIRouter route decorators (@app.get, @router.post, @bp.route)
    - Pydantic BaseModel / BaseSettings schemas, @dataclass, typing.Protocol, TypedDict, Enum
    - Functions & async defs with full type annotations, default values, decorators, docstrings
    - Raised exception classes (raise ValueError, raise HTTPException)
    - Intra-file & qualified function/method call-graph edges and McCabe cyclomatic complexity
    """
    HTTP_METHODS: Set[str] = {
        "get",
        "post",
        "put",
        "delete",
        "patch",
        "options",
        "head",
        "trace",
        "websocket",
        "route",
        "api_route",
    }
    @classmethod
    def extract(cls, content: str, rel_path: str = "<memory>.py") -> DeepFileExtraction:
        result = DeepFileExtraction(rel_path=rel_path, language="python", ext=".py")
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return cls._fallback_regex_extract(content, rel_path, result)
        lines = content.splitlines()
        dunder_all = cls._extract_dunder_all(tree)
        for node in tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    result.imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                dots = "." * (node.level or 0)
                for alias in node.names:
                    result.imports.append(f"{dots}{mod}.{alias.name}".strip("."))
        all_exceptions: Set[str] = set()
        total_complexity = 1
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                sym, routes, calls, exc, comp = cls._extract_function(
                    node, lines, rel_path, parent_class="", dunder_all=dunder_all
                )
                result.symbols.append(sym)
                result.routes.extend(routes)
                result.call_edges.extend(calls)
                all_exceptions.update(exc)
                total_complexity += comp - 1
                if sym.exported:
                    result.exports.append(sym.name)
            elif isinstance(node, ast.ClassDef):
                cls_sym, schema, methods, routes, calls, exc, comp = cls._extract_class(
                    node, lines, rel_path, dunder_all=dunder_all
                )
                result.symbols.append(cls_sym)
                if schema is not None:
                    result.schemas.append(schema)
                result.symbols.extend(methods)
                result.routes.extend(routes)
                result.call_edges.extend(calls)
                all_exceptions.update(exc)
                total_complexity += comp - 1
                if cls_sym.exported:
                    result.exports.append(cls_sym.name)
        result.raised_exceptions = sorted(all_exceptions)
        result.complexity_score = max(1, total_complexity)
        return result
    @classmethod
    def _extract_dunder_all(cls, tree: ast.Module) -> Optional[Set[str]]:
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "__all__":
                        if isinstance(node.value, (ast.List, ast.Tuple, ast.Set)):
                            items: Set[str] = set()
                            for elt in node.value.elts:
                                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                    items.add(elt.value)
                            return items
        return None
    @staticmethod
    def _unparse(node: Optional[ast.AST]) -> str:
        if node is None:
            return ""
        try:
            return ast.unparse(node)
        except Exception:
            return ""
    @classmethod
    def _format_signature(cls, node: ast.FunctionDef | ast.AsyncFunctionDef) -> Tuple[str, List[str], str]:
        prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
        params: List[str] = []
        args = node.args
        posonly = getattr(args, "posonlyargs", [])
        regular = list(posonly) + list(args.args)
        defaults_offset = len(regular) - len(args.defaults)
        for idx, arg in enumerate(regular):
            part = arg.arg
            if arg.annotation:
                part += f": {cls._unparse(arg.annotation)}"
            if idx >= defaults_offset:
                def_node = args.defaults[idx - defaults_offset]
                part += f" = {cls._unparse(def_node)}"
            params.append(part)
            if posonly and idx == len(posonly) - 1:
                params.append("/")
        if args.vararg:
            var_part = f"*{args.vararg.arg}"
            if args.vararg.annotation:
                var_part += f": {cls._unparse(args.vararg.annotation)}"
            params.append(var_part)
        elif args.kwonlyargs:
            params.append("*")
        for kwarg, kwdef in zip(args.kwonlyargs, args.kw_defaults):
            part = kwarg.arg
            if kwarg.annotation:
                part += f": {cls._unparse(kwarg.annotation)}"
            if kwdef is not None:
                part += f" = {cls._unparse(kwdef)}"
            params.append(part)
        if args.kwarg:
            kw_part = f"**{args.kwarg.arg}"
            if args.kwarg.annotation:
                kw_part += f": {cls._unparse(args.kwarg.annotation)}"
            params.append(kw_part)
        ret_str = cls._unparse(node.returns) if node.returns else ""
        ret_suffix = f" -> {ret_str}" if ret_str else ""
        sig = f"{prefix} {node.name}({', '.join(params)}){ret_suffix}"
        return sig, params, ret_str
    @classmethod
    def _extract_routes_from_decorators(
        cls,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        rel_path: str,
        doc: str,
    ) -> List[ExtractedRoute]:
        routes: List[ExtractedRoute] = []
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call):
                continue
            func_expr = cls._unparse(dec.func)
            parts = func_expr.split(".")
            if len(parts) < 2:
                continue
            owner, method_lower = parts[0], parts[-1].lower()
            if method_lower not in cls.HTTP_METHODS:
                continue
            route_path = "/"
            if dec.args and isinstance(dec.args[0], ast.Constant) and isinstance(dec.args[0].value, str):
                route_path = dec.args[0].value
            http_methods: List[str] = [method_lower.upper()]
            response_model = ""
            status_code: Optional[int] = None
            middlewares: List[str] = []
            for kw in dec.keywords:
                if kw.arg == "path" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                    route_path = kw.value.value
                elif kw.arg == "methods" and isinstance(kw.value, (ast.List, ast.Tuple, ast.Set)):
                    extracted_m = [
                        elt.value.upper()
                        for elt in kw.value.elts
                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                    ]
                    if extracted_m:
                        http_methods = extracted_m
                elif kw.arg == "response_model":
                    response_model = cls._unparse(kw.value)
                elif kw.arg == "status_code" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, int):
                    status_code = kw.value.value
                elif kw.arg in {"dependencies", "middleware"}:
                    middlewares.append(cls._unparse(kw.value))
            framework = (
                "FastAPI"
                if any(k.arg in {"response_model", "dependencies", "tags", "operation_id"} for k in dec.keywords)
                or owner in {"router", "api_router"}
                or method_lower in {"get", "post", "put", "delete", "patch", "websocket"}
                else "Flask"
            )
            for m_name in http_methods:
                routes.append(
                    ExtractedRoute(
                        method="WS" if m_name == "WEBSOCKET" else m_name,
                        path=route_path,
                        handler_name=node.name,
                        framework=framework,
                        line=dec.lineno,
                        file_path=rel_path,
                        response_model=response_model,
                        status_code=status_code,
                        middlewares=middlewares,
                        summary=(doc.splitlines()[0].strip() if doc else ""),
                    )
                )
        return routes
    @classmethod
    def _analyze_body(
        cls,
        node: ast.AST,
        caller_qualname: str,
        rel_path: str,
    ) -> Tuple[List[str], List[CallEdge], List[str], int]:
        calls_list: List[str] = []
        call_edges: List[CallEdge] = []
        raises_set: Set[str] = set()
        complexity = 1
        for child in ast.walk(node):
            if isinstance(
                child,
                (
                    ast.If,
                    ast.For,
                    ast.AsyncFor,
                    ast.While,
                    ast.ExceptHandler,
                    ast.With,
                    ast.AsyncWith,
                    ast.IfExp,
                    ast.ListComp,
                    ast.SetComp,
                    ast.DictComp,
                    ast.GeneratorExp,
                ),
            ):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                complexity += max(1, len(child.values) - 1)
            elif isinstance(child, ast.Raise):
                if child.exc is not None:
                    if isinstance(child.exc, ast.Call):
                        exc_name = cls._unparse(child.exc.func)
                    elif isinstance(child.exc, ast.Name):
                        exc_name = child.exc.id
                    else:
                        exc_name = cls._unparse(child.exc)
                    if exc_name:
                        raises_set.add(exc_name)
            elif isinstance(child, ast.Call):
                callee = cls._unparse(child.func)
                if callee and len(callee) <= 80:
                    clean_callee = callee.split("(")[0]
                    if clean_callee not in calls_list:
                        calls_list.append(clean_callee)
                    call_edges.append(
                        CallEdge(
                            caller=caller_qualname,
                            callee=clean_callee,
                            line=getattr(child, "lineno", 1),
                            file_path=rel_path,
                            call_kind="method" if "." in clean_callee else "function",
                        )
                    )
        return calls_list, call_edges, sorted(raises_set), complexity
    @classmethod
    def _extract_function(
        cls,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        lines: List[str],
        rel_path: str,
        parent_class: str = "",
        dunder_all: Optional[Set[str]] = None,
    ) -> Tuple[ExtractedSymbol, List[ExtractedRoute], List[CallEdge], List[str], int]:
        sig, params, ret_str = cls._format_signature(node)
        doc = ast.get_docstring(node) or ""
        decs = [f"@{cls._unparse(d)}" for d in node.decorator_list]
        qualname = f"{parent_class}.{node.name}" if parent_class else node.name
        calls_list, call_edges, raises_list, comp = cls._analyze_body(node, qualname, rel_path)
        routes = cls._extract_routes_from_decorators(node, rel_path, doc)
        exported = (
            (node.name in dunder_all)
            if (dunder_all is not None and not parent_class)
            else (not node.name.startswith("_") or node.name in {"__init__", "__call__"})
        )
        kind = "method" if parent_class else ("async_function" if isinstance(node, ast.AsyncFunctionDef) else "function")
        sym = ExtractedSymbol(
            name=node.name,
            kind=kind,
            signature=sig,
            line_start=node.lineno,
            line_end=getattr(node, "end_lineno", node.lineno) or node.lineno,
            exported=exported,
            is_async=isinstance(node, ast.AsyncFunctionDef),
            docstring=doc.splitlines()[0].strip() if doc else "",
            decorators=decs,
            parameters=params,
            return_type=ret_str,
            parent=parent_class,
            raises=raises_list,
            calls=calls_list[:25],
            complexity=comp,
        )
        return sym, routes, call_edges, raises_list, comp
    @classmethod
    def _extract_class(
        cls,
        node: ast.ClassDef,
        lines: List[str],
        rel_path: str,
        dunder_all: Optional[Set[str]] = None,
    ) -> Tuple[
        ExtractedSymbol,
        Optional[ExtractedSchema],
        List[ExtractedSymbol],
        List[ExtractedRoute],
        List[CallEdge],
        List[str],
        int,
    ]:
        bases = [cls._unparse(b) for b in node.bases if cls._unparse(b)]
        decs = [f"@{cls._unparse(d)}" for d in node.decorator_list]
        doc = ast.get_docstring(node) or ""
        exported = (node.name in dunder_all) if dunder_all is not None else (not node.name.startswith("_"))
        base_short_names = {b.split("[")[0].split(".")[-1] for b in bases}
        dec_names = {d.lstrip("@").split("(")[0].split(".")[-1] for d in decs}
        schema_kind: Optional[str] = None
        if base_short_names & {"BaseModel", "RootModel", "BaseSettings", "SQLModel", "Schema"}:
            schema_kind = "pydantic"
        elif "dataclass" in dec_names:
            schema_kind = "dataclass"
        elif base_short_names & {"Protocol"}:
            schema_kind = "protocol"
        elif base_short_names & {"TypedDict"}:
            schema_kind = "typeddict"
        elif base_short_names & {"Enum", "IntEnum", "StrEnum", "Flag"}:
            schema_kind = "enum"
        fields_info: List[Dict[str, Any]] = []
        validators: List[str] = []
        methods: List[ExtractedSymbol] = []
        routes: List[ExtractedRoute] = []
        call_edges: List[CallEdge] = []
        all_exc: Set[str] = set()
        total_comp = 1
        for stmt in node.body:
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                f_name = stmt.target.id
                f_type = cls._unparse(stmt.annotation)
                f_default = cls._unparse(stmt.value) if stmt.value is not None else None
                fields_info.append(
                    {
                        "name": f_name,
                        "type": f_type,
                        "default": f_default,
                        "required": f_default is None and "Optional" not in f_type and "| None" not in f_type,
                        "line": stmt.lineno,
                    }
                )
            elif isinstance(stmt, ast.Assign) and schema_kind == "enum":
                for target in stmt.targets:
                    if isinstance(target, ast.Name) and not target.id.startswith("_"):
                        fields_info.append(
                            {
                                "name": target.id,
                                "type": "EnumMember",
                                "default": cls._unparse(stmt.value),
                                "required": True,
                                "line": stmt.lineno,
                            }
                        )
            elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                m_sym, m_routes, m_calls, m_exc, m_comp = cls._extract_function(
                    stmt, lines, rel_path, parent_class=node.name, dunder_all=dunder_all
                )
                methods.append(m_sym)
                routes.extend(m_routes)
                call_edges.extend(m_calls)
                all_exc.update(m_exc)
                total_comp += m_comp - 1
                for d in m_sym.decorators:
                    if any(v in d for v in ("validator", "field_validator", "model_validator", "root_validator")):
                        validators.append(stmt.name)
        base_sig = f"({', '.join(bases)})" if bases else ""
        sig = f"class {node.name}{base_sig}"
        cls_kind = schema_kind if schema_kind in {"pydantic", "dataclass", "protocol"} else "class"
        cls_sym = ExtractedSymbol(
            name=node.name,
            kind=cls_kind,
            signature=sig,
            line_start=node.lineno,
            line_end=getattr(node, "end_lineno", node.lineno) or node.lineno,
            exported=exported,
            docstring=doc.splitlines()[0].strip() if doc else "",
            decorators=decs,
            bases=bases,
            raises=sorted(all_exc),
            complexity=total_comp,
            metadata={"field_count": len(fields_info), "method_count": len(methods)},
        )
        schema_obj: Optional[ExtractedSchema] = None
        if schema_kind is not None or (fields_info and len(fields_info) >= 2):
            schema_obj = ExtractedSchema(
                name=node.name,
                schema_kind=schema_kind or "class_schema",
                line_start=node.lineno,
                line_end=getattr(node, "end_lineno", node.lineno) or node.lineno,
                fields=fields_info,
                bases=bases,
                exported=exported,
                docstring=doc.splitlines()[0].strip() if doc else "",
                validators=validators,
            )
        return cls_sym, schema_obj, methods, routes, call_edges, sorted(all_exc), total_comp
    @classmethod
    def _fallback_regex_extract(
        cls, content: str, rel_path: str, result: DeepFileExtraction
    ) -> DeepFileExtraction:
        fn_re = re.compile(
            r"^\s*(async\s+)?def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)(?:\s*->\s*([^:]+))?:",
            re.MULTILINE,
        )
        cls_re = re.compile(r"^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)(?:\(([^)]*)\))?:", re.MULTILINE)
        for m in cls_re.finditer(content):
            name = m.group(1)
            bases = [b.strip() for b in (m.group(2) or "").split(",") if b.strip()]
            line = _line_number_at(content, m.start())
            result.symbols.append(
                ExtractedSymbol(
                    name=name,
                    kind="class",
                    signature=m.group(0).strip().rstrip(":"),
                    line_start=line,
                    bases=bases,
                )
            )
        for m in fn_re.finditer(content):
            is_async = bool(m.group(1))
            name = m.group(2)
            line = _line_number_at(content, m.start())
            result.symbols.append(
                ExtractedSymbol(
                    name=name,
                    kind="async_function" if is_async else "function",
                    signature=m.group(0).strip().rstrip(":"),
                    line_start=line,
                    is_async=is_async,
                    return_type=(m.group(4) or "").strip(),
                )
            )
        return result


# =====================================================================
# 2. TYPESCRIPT / JAVASCRIPT / REACT DEEP EXTRACTOR
# =====================================================================


class TypeScriptDeepExtractor:
    """
    Deep structural extractor for TypeScript, JavaScript, JSX, and TSX files:
    - export interface / interface & export type definitions with parsed property signatures
    - Zod schemas (z.object({...}), z.enum([...]), z.union(...))
    - Next.js App Router (export async function GET/POST/PUT/DELETE/PATCH) & Express/Fastify/Hono routes
    - React custom hooks (useXyz) and functional/class components with hook usage metadata
    - ES6 classes, methods, arrow functions, thrown errors, and call-graph edges
    """
    NEXTJS_HTTP_METHODS: Set[str] = {"GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"}
    INTERFACE_RE = re.compile(
        r"(?m)^[ \t]*(export\s+)?interface\s+([A-Za-z_$][A-Za-z0-9_$]*)(?:<[^>]+>)?(?:\s+extends\s+([^{]+))?\s*\{"
    )
    TYPE_ALIAS_RE = re.compile(
        r"(?m)^[ \t]*(export\s+)?type\s+([A-Za-z_$][A-Za-z0-9_$]*)(?:<[^>]+>)?\s*=\s*([^;\n]+(?:\{[\s\S]*?\})?)"
    )
    ZOD_SCHEMA_RE = re.compile(
        r"(?m)^[ \t]*(export\s+)?(?:const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*z\.(object|enum|union|discriminatedUnion|array|record|string|number)\s*\("
    )
    FUNC_DECL_RE = re.compile(
        r"(?m)^[ \t]*(export\s+)?(default\s+)?(async\s+)?function\s+([A-Za-z_$][A-Za-z0-9_$]*)(?:<[^>]*>)?\s*\(([^)]*)\)(?:\s*:\s*([^{\n]+))?\s*\{"
    )
    ARROW_FUNC_RE = re.compile(
        r"(?m)^[ \t]*(export\s+)?(?:const|let)\s+([A-Za-z_$][A-Za-z0-9_$]*)(?:\s*:\s*([^=]+))?\s*=\s*(async\s+)?(?:<[^>]*>)?\s*\(([^)]*)\)(?:\s*:\s*([^=>\n]+))?\s*=>\s*"
    )
    CLASS_DECL_RE = re.compile(
        r"(?m)^[ \t]*(export\s+)?(default\s+)?(abstract\s+)?class\s+([A-Za-z_$][A-Za-z0-9_$]*)(?:<[^>]+>)?(?:\s+extends\s+([A-Za-z0-9_$.<>]+))?(?:\s+implements\s+([^{]+))?\s*\{"
    )
    EXPRESS_ROUTE_RE = re.compile(
        r"\b(?:app|router|server|fastify|hono)\.(get|post|put|delete|patch|options|all)\s*\(\s*['\"\x60]([^'\"\x60]+)['\"\x60]\s*,\s*([A-Za-z0-9_$.]+|async\s*\(|\(|function)"
    )
    IMPORT_RE = re.compile(
        r"""(?m)^\s*(?:import|export)\s+(?:type\s+)?(?:[^'"]*?\s+from\s+)?['"]([^'"]+)['"]|require\(\s*['"]([^'"]+)['"]\s*\)"""
    )
    THROW_RE = re.compile(r"\bthrow\s+(?:new\s+)?([A-Za-z_$][A-Za-z0-9_$.]*)")
    @classmethod
    def extract(cls, content: str, rel_path: str = "index.ts") -> DeepFileExtraction:
        ext = Path(rel_path).suffix.lower() or ".ts"
        lang = (
            "tsx"
            if ext == ".tsx"
            else "jsx"
            if ext == ".jsx"
            else "javascript"
            if ext in {".js", ".mjs", ".cjs"}
            else "typescript"
        )
        result = DeepFileExtraction(rel_path=rel_path, language=lang, ext=ext)
        for m in cls.IMPORT_RE.finditer(content):
            spec = m.group(1) or m.group(2)
            if spec and spec not in result.imports:
                result.imports.append(spec)
        for m in cls.THROW_RE.finditer(content):
            exc = m.group(1)
            if exc not in result.raised_exceptions:
                result.raised_exceptions.append(exc)
        # 1. Extract TypeScript Interfaces
        for m in cls.INTERFACE_RE.finditer(content):
            exported = bool(m.group(1))
            name = m.group(2)
            extends_raw = (m.group(3) or "").strip()
            bases = [b.strip() for b in extends_raw.split(",") if b.strip()]
            line_start = _line_number_at(content, m.start())
            body, close_idx = _extract_balanced_block(content, m.end() - 1, "{", "}")
            line_end = _line_number_at(content, close_idx) if close_idx != -1 else line_start
            fields = cls._parse_ts_fields(body, line_start)
            ext_clause = f" extends {', '.join(bases)}" if bases else ""
            sig = f"{'export ' if exported else ''}interface {name}{ext_clause}"
            result.schemas.append(
                ExtractedSchema(
                    name=name,
                    schema_kind="ts_interface",
                    line_start=line_start,
                    line_end=line_end,
                    fields=fields,
                    bases=bases,
                    exported=exported,
                )
            )
            result.symbols.append(
                ExtractedSymbol(
                    name=name,
                    kind="interface",
                    signature=sig,
                    line_start=line_start,
                    line_end=line_end,
                    exported=exported,
                    bases=bases,
                    metadata={"field_count": len(fields)},
                )
            )
            if exported:
                result.exports.append(name)
        # 2. Extract TypeScript Type Aliases
        for m in cls.TYPE_ALIAS_RE.finditer(content):
            exported = bool(m.group(1))
            name = m.group(2)
            rhs = m.group(3).strip()
            line_start = _line_number_at(content, m.start())
            fields: List[Dict[str, Any]] = []
            line_end = line_start
            if "{" in rhs:
                brace_pos = content.find("{", m.start())
                if brace_pos != -1:
                    body, close_idx = _extract_balanced_block(content, brace_pos, "{", "}")
                    line_end = _line_number_at(content, close_idx) if close_idx != -1 else line_start
                    fields = cls._parse_ts_fields(body, line_start)
            short_rhs = re.sub(r"\s+", " ", rhs)[:90]
            sig = f"{'export ' if exported else ''}type {name} = {short_rhs}"
            result.schemas.append(
                ExtractedSchema(
                    name=name,
                    schema_kind="ts_type",
                    line_start=line_start,
                    line_end=line_end,
                    fields=fields,
                    exported=exported,
                    metadata={"definition": short_rhs},
                )
            )
            result.symbols.append(
                ExtractedSymbol(
                    name=name,
                    kind="type_alias",
                    signature=sig,
                    line_start=line_start,
                    line_end=line_end,
                    exported=exported,
                )
            )
            if exported:
                result.exports.append(name)
        # 3. Extract Zod Schemas
        for m in cls.ZOD_SCHEMA_RE.finditer(content):
            exported = bool(m.group(1))
            name = m.group(2)
            zod_kind = m.group(3)
            line_start = _line_number_at(content, m.start())
            paren_body, close_idx = _extract_balanced_block(content, m.end() - 1, "(", ")")
            line_end = _line_number_at(content, close_idx) if close_idx != -1 else line_start
            fields = cls._parse_zod_fields(paren_body, line_start)
            result.schemas.append(
                ExtractedSchema(
                    name=name,
                    schema_kind="zod_schema",
                    line_start=line_start,
                    line_end=line_end,
                    fields=fields,
                    exported=exported,
                    metadata={"zod_combinator": f"z.{zod_kind}"},
                )
            )
            result.symbols.append(
                ExtractedSymbol(
                    name=name,
                    kind="zod_schema",
                    signature=f"{'export ' if exported else ''}const {name} = z.{zod_kind}(...)",
                    line_start=line_start,
                    line_end=line_end,
                    exported=exported,
                    metadata={"field_count": len(fields)},
                )
            )
            if exported and name not in result.exports:
                result.exports.append(name)
        # 4. Extract Functions, Next.js Route Handlers, React Hooks & Components
        seen_funcs: Set[Tuple[str, int]] = set()
        for m in cls.FUNC_DECL_RE.finditer(content):
            exported = bool(m.group(1) or m.group(2))
            is_async = bool(m.group(3))
            name = m.group(4)
            params_raw = m.group(5).strip()
            ret_type = (m.group(6) or "").strip()
            line_start = _line_number_at(content, m.start())
            seen_funcs.add((name, line_start))
            body, close_idx = _extract_balanced_block(content, m.end() - 1, "{", "}")
            line_end = _line_number_at(content, close_idx) if close_idx != -1 else line_start
            cls._register_ts_callable(
                result=result,
                name=name,
                exported=exported,
                is_async=is_async,
                params_raw=params_raw,
                ret_type=ret_type,
                body=body,
                line_start=line_start,
                line_end=line_end,
                rel_path=rel_path,
            )
        for m in cls.ARROW_FUNC_RE.finditer(content):
            exported = bool(m.group(1))
            name = m.group(2)
            var_type = (m.group(3) or "").strip()
            is_async = bool(m.group(4))
            params_raw = m.group(5).strip()
            ret_type = (m.group(6) or var_type).strip()
            line_start = _line_number_at(content, m.start())
            if (name, line_start) in seen_funcs:
                continue
            after_arrow = content[m.end() : m.end() + 20].lstrip()
            if after_arrow.startswith("{"):
                brace_pos = content.find("{", m.end())
                body, close_idx = _extract_balanced_block(content, brace_pos, "{", "}")
                line_end = _line_number_at(content, close_idx) if close_idx != -1 else line_start
            else:
                nl_pos = content.find("\n", m.end())
                body = content[m.end() : nl_pos if nl_pos != -1 else len(content)]
                line_end = _line_number_at(content, nl_pos if nl_pos != -1 else len(content))
            cls._register_ts_callable(
                result=result,
                name=name,
                exported=exported,
                is_async=is_async,
                params_raw=params_raw,
                ret_type=ret_type,
                body=body,
                line_start=line_start,
                line_end=line_end,
                rel_path=rel_path,
            )
        # 5. Extract Classes & Class Methods
        for m in cls.CLASS_DECL_RE.finditer(content):
            exported = bool(m.group(1) or m.group(2))
            name = m.group(4)
            ext_cls = (m.group(5) or "").strip()
            impl_raw = (m.group(6) or "").strip()
            bases = [b.strip() for b in ([ext_cls] if ext_cls else []) + impl_raw.split(",") if b.strip()]
            line_start = _line_number_at(content, m.start())
            body, close_idx = _extract_balanced_block(content, m.end() - 1, "{", "}")
            line_end = _line_number_at(content, close_idx) if close_idx != -1 else line_start
            is_react_comp = any("Component" in b or "PureComponent" in b for b in bases)
            sig = f"{'export ' if exported else ''}class {name}" + (f" extends {ext_cls}" if ext_cls else "")
            result.symbols.append(
                ExtractedSymbol(
                    name=name,
                    kind="react_component" if is_react_comp else "class",
                    signature=sig,
                    line_start=line_start,
                    line_end=line_end,
                    exported=exported,
                    bases=bases,
                )
            )
            if exported and name not in result.exports:
                result.exports.append(name)
            method_re = re.compile(
                r"(?m)^[ \t]*(?:(public|private|protected|static|readonly|override)\s+)*(async\s+)?(get\s+|set\s+)?([A-Za-z_$][A-Za-z0-9_$]*)\s*(?:<[^>]*>)?\s*\(([^)]*)\)(?:\s*:\s*([^{\n]+))?\s*\{"
            )
            for mm in method_re.finditer(body):
                m_name = mm.group(4)
                if m_name in {"if", "for", "while", "switch", "catch"}:
                    continue
                m_async = bool(mm.group(2))
                m_params = mm.group(5).strip()
                m_ret = (mm.group(6) or "").strip()
                m_line = line_start + _line_number_at(body, mm.start()) - 1
                m_body, m_close = _extract_balanced_block(body, mm.end() - 1, "{", "}")
                m_end_line = line_start + _line_number_at(body, m_close) - 1 if m_close != -1 else m_line
                calls, edges = cls._extract_ts_calls(m_body, f"{name}.{m_name}", rel_path, m_line)
                result.call_edges.extend(edges)
                result.symbols.append(
                    ExtractedSymbol(
                        name=m_name,
                        kind="method",
                        signature=f"{'async ' if m_async else ''}{m_name}({m_params}){': ' + m_ret if m_ret else ''}",
                        line_start=m_line,
                        line_end=m_end_line,
                        exported=mm.group(1) != "private",
                        is_async=m_async,
                        parent=name,
                        parameters=[p.strip() for p in m_params.split(",") if p.strip()],
                        return_type=m_ret,
                        calls=calls[:20],
                    )
                )
        # 6. Express / Fastify / Hono route registrations
        for m in cls.EXPRESS_ROUTE_RE.finditer(content):
            http_method = m.group(1).upper()
            route_path = m.group(2)
            handler_raw = m.group(3).strip()
            handler_name = handler_raw if not handler_raw.endswith("(") else f"anonymous_{http_method.lower()}"
            line = _line_number_at(content, m.start())
            result.routes.append(
                ExtractedRoute(
                    method=http_method,
                    path=route_path,
                    handler_name=handler_name,
                    framework="Express/Fastify/Hono",
                    line=line,
                    file_path=rel_path,
                )
            )
        result.complexity_score = max(
            1,
            1
            + len(
                re.findall(
                    r"\b(?:if|else\s+if|for|while|case|catch)\b|\?\?|&&|\|\|",
                    content,
                )
            ),
        )
        return result
    @classmethod
    def _register_ts_callable(
        cls,
        result: DeepFileExtraction,
        name: str,
        exported: bool,
        is_async: bool,
        params_raw: str,
        ret_type: str,
        body: str,
        line_start: int,
        line_end: int,
        rel_path: str,
    ) -> None:
        calls, edges = cls._extract_ts_calls(body, name, rel_path, line_start)
        result.call_edges.extend(edges)
        hooks_used = sorted({c for c in calls if re.match(r"^use[A-Z0-9_]", c.split(".")[-1])})
        is_nextjs_route = exported and name in cls.NEXTJS_HTTP_METHODS
        is_hook = bool(re.match(r"^use[A-Z0-9_]", name))
        is_component = bool(
            re.match(r"^[A-Z][A-Za-z0-9_]*$", name)
            and not is_nextjs_route
            and (
                "<" in body
                or "jsx" in body.lower()
                or "ReactElement" in ret_type
                or "JSX.Element" in ret_type
                or "ReactNode" in ret_type
                or "FC" in ret_type
            )
        )
        kind = (
            "route_handler"
            if is_nextjs_route
            else "react_hook"
            if is_hook
            else "react_component"
            if is_component
            else "async_function"
            if is_async
            else "function"
        )
        sig = f"{'export ' if exported else ''}{'async ' if is_async else ''}function {name}({params_raw}){': ' + ret_type if ret_type else ''}"
        result.symbols.append(
            ExtractedSymbol(
                name=name,
                kind=kind,
                signature=sig,
                line_start=line_start,
                line_end=line_end,
                exported=exported,
                is_async=is_async,
                parameters=[p.strip() for p in params_raw.split(",") if p.strip()],
                return_type=ret_type,
                calls=calls[:25],
                metadata={"hooks_used": hooks_used} if hooks_used else {},
            )
        )
        if exported and name not in result.exports:
            result.exports.append(name)
        if is_nextjs_route:
            inferred_path = cls._infer_nextjs_route_path(rel_path)
            result.routes.append(
                ExtractedRoute(
                    method=name,
                    path=inferred_path,
                    handler_name=name,
                    framework="Next.js App Router",
                    line=line_start,
                    file_path=rel_path,
                    response_model=ret_type,
                )
            )
    @staticmethod
    def _infer_nextjs_route_path(rel_path: str) -> str:
        norm = rel_path.replace("\\", "/")
        for marker in ("src/app/", "app/", "src/pages/api/", "pages/api/"):
            if marker in norm:
                sub = norm.split(marker, 1)[1]
                sub = re.sub(r"/(route|page|index)\.(ts|tsx|js|jsx|mjs)$", "", sub)
                sub = re.sub(r"\.(ts|tsx|js|jsx|mjs)$", "", sub)
                prefix = "/api/" if "pages/api/" in marker else "/"
                return (prefix + sub.lstrip("/")).rstrip("/") or "/"
        return "/" + Path(rel_path).parent.as_posix().strip(".")
    @staticmethod
    def _parse_ts_fields(body: str, base_line: int) -> List[Dict[str, Any]]:
        fields: List[Dict[str, Any]] = []
        field_re = re.compile(r"(?m)^[ \t]*(readonly\s+)?([A-Za-z_$][A-Za-z0-9_$]*)(\?)?\s*:\s*([^;,\n]+)")
        for m in field_re.finditer(body):
            fields.append(
                {
                    "name": m.group(2),
                    "type": m.group(4).strip(),
                    "required": m.group(3) != "?",
                    "readonly": bool(m.group(1)),
                    "line": base_line + _line_number_at(body, m.start()) - 1,
                }
            )
        return fields
    @staticmethod
    def _parse_zod_fields(body: str, base_line: int) -> List[Dict[str, Any]]:
        fields: List[Dict[str, Any]] = []
        prop_re = re.compile(
            r"(?m)^[ \t]*([A-Za-z_$][A-Za-z0-9_$]*)\s*:\s*(z\.[A-Za-z0-9_.()\[\]'\"\s]+?)(?:,\s*$|\n|$)"
        )
        for m in prop_re.finditer(body):
            z_expr = re.sub(r"\s+", " ", m.group(2).strip()).rstrip(",")
            fields.append(
                {
                    "name": m.group(1),
                    "type": z_expr[:80],
                    "required": ".optional()" not in z_expr and ".nullable()" not in z_expr,
                    "line": base_line + _line_number_at(body, m.start()) - 1,
                }
            )
        return fields
    @staticmethod
    def _extract_ts_calls(
        body: str, caller: str, rel_path: str, base_line: int
    ) -> Tuple[List[str], List[CallEdge]]:
        call_re = re.compile(r"\b([A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z_$][A-Za-z0-9_$]*)*)\s*\(")
        ignored = {
            "if",
            "for",
            "while",
            "switch",
            "catch",
            "return",
            "function",
            "typeof",
            "instanceof",
            "new",
            "import",
            "require",
            "super",
        }
        calls: List[str] = []
        edges: List[CallEdge] = []
        for m in call_re.finditer(body):
            callee = m.group(1)
            if callee in ignored or callee.startswith("console."):
                continue
            line = base_line + _line_number_at(body, m.start()) - 1
            if callee not in calls:
                calls.append(callee)
            edges.append(
                CallEdge(
                    caller=caller,
                    callee=callee,
                    line=line,
                    file_path=rel_path,
                    call_kind="method" if "." in callee else "function",
                )
            )
        return calls, edges


# =====================================================================
# 3. GO DEEP EXTRACTOR
# =====================================================================


class GoDeepExtractor:
    """
    Deep structural extractor for Go (.go) source files:
    - type Name struct { ... } with field types and struct tags
    - type Name interface { ... } with method specifications
    - Receiver methods func (s *Server) Method(...) ...
    - Package-level exported/unexported functions
    - Standard library http.HandleFunc, Gin/Echo/Chi route registrations
    """
    STRUCT_RE = re.compile(r"(?m)^[ \t]*type\s+([A-Za-z_][A-Za-z0-9_]*)(?:\[[^\]]+\])?\s+struct\s*\{")
    INTERFACE_RE = re.compile(r"(?m)^[ \t]*type\s+([A-Za-z_][A-Za-z0-9_]*)(?:\[[^\]]+\])?\s+interface\s*\{")
    FUNC_RE = re.compile(
        r"(?m)^[ \t]*func\s+(?:\(\s*([A-Za-z0-9_*\s\[\]]+)\s*\)\s+)?([A-Za-z_][A-Za-z0-9_]*)(?:\[[^\]]+\])?\s*\(([^)]*)\)\s*([^{\n]*?)\s*\{"
    )
    GO_ROUTE_RE = re.compile(
        r'\b(?:mux|r|router|e|group|http)\.(HandleFunc|Handle|GET|POST|PUT|DELETE|PATCH|Get|Post|Put|Delete)\s*\(\s*"([^"]+)"\s*,\s*([A-Za-z0-9_.]+)'
    )
    @classmethod
    def extract(cls, content: str, rel_path: str = "main.go") -> DeepFileExtraction:
        result = DeepFileExtraction(rel_path=rel_path, language="go", ext=".go")
        bt = chr(96)
        # Imports
        single_imp = re.findall(r'(?m)^\s*import\s+(?:[A-Za-z0-9_]+\s+)?"([^"]+)"', content)
        result.imports.extend(single_imp)
        for blk in re.finditer(r"(?m)^\s*import\s*\(([\s\S]*?)\)", content):
            for imp in re.findall(r'"([^"]+)"', blk.group(1)):
                if imp not in result.imports:
                    result.imports.append(imp)
        # Structs
        for m in cls.STRUCT_RE.finditer(content):
            name = m.group(1)
            exported = name[0].isupper()
            line_start = _line_number_at(content, m.start())
            body, close_idx = _extract_balanced_block(content, m.end() - 1, "{", "}")
            line_end = _line_number_at(content, close_idx) if close_idx != -1 else line_start
            fields: List[Dict[str, Any]] = []
            bases: List[str] = []
            for idx, raw_line in enumerate(body.splitlines(), start=1):
                s = re.sub(r"//.*$", "", raw_line).strip()
                if not s:
                    continue
                tag_str = ""
                if bt in s:
                    parts_bt = s.split(bt)
                    if len(parts_bt) >= 3:
                        tag_str = parts_bt[1]
                        s = parts_bt[0].strip()
                parts = s.split()
                if len(parts) == 1:
                    bases.append(parts[0].lstrip("*"))
                elif len(parts) >= 2:
                    f_names = [n.strip() for n in parts[0].split(",") if n.strip()]
                    f_type = " ".join(parts[1:])
                    for fn in f_names:
                        fields.append(
                            {
                                "name": fn,
                                "type": f_type,
                                "tag": tag_str,
                                "exported": fn[0].isupper(),
                                "line": line_start + idx - 1,
                            }
                        )
            result.schemas.append(
                ExtractedSchema(
                    name=name,
                    schema_kind="go_struct",
                    line_start=line_start,
                    line_end=line_end,
                    fields=fields,
                    bases=bases,
                    exported=exported,
                )
            )
            result.symbols.append(
                ExtractedSymbol(
                    name=name,
                    kind="struct",
                    signature=f"type {name} struct",
                    line_start=line_start,
                    line_end=line_end,
                    exported=exported,
                    bases=bases,
                    metadata={"field_count": len(fields)},
                )
            )
            if exported:
                result.exports.append(name)
        # Interfaces
        for m in cls.INTERFACE_RE.finditer(content):
            name = m.group(1)
            exported = name[0].isupper()
            line_start = _line_number_at(content, m.start())
            body, close_idx = _extract_balanced_block(content, m.end() - 1, "{", "}")
            line_end = _line_number_at(content, close_idx) if close_idx != -1 else line_start
            methods_spec: List[Dict[str, Any]] = []
            bases: List[str] = []
            for idx, raw_line in enumerate(body.splitlines(), start=1):
                s = re.sub(r"//.*$", "", raw_line).strip()
                if not s:
                    continue
                if "(" in s:
                    m_name = s.split("(", 1)[0].strip()
                    methods_spec.append({"name": m_name, "type": s, "line": line_start + idx - 1})
                else:
                    bases.append(s)
            result.schemas.append(
                ExtractedSchema(
                    name=name,
                    schema_kind="go_interface",
                    line_start=line_start,
                    line_end=line_end,
                    fields=methods_spec,
                    bases=bases,
                    exported=exported,
                )
            )
            result.symbols.append(
                ExtractedSymbol(
                    name=name,
                    kind="interface",
                    signature=f"type {name} interface",
                    line_start=line_start,
                    line_end=line_end,
                    exported=exported,
                    bases=bases,
                )
            )
            if exported:
                result.exports.append(name)
        # Functions & Receiver Methods
        for m in cls.FUNC_RE.finditer(content):
            recv_raw = (m.group(1) or "").strip()
            name = m.group(2)
            params_raw = m.group(3).strip()
            ret_raw = (m.group(4) or "").strip()
            exported = name[0].isupper()
            line_start = _line_number_at(content, m.start())
            body, close_idx = _extract_balanced_block(content, m.end() - 1, "{", "}")
            line_end = _line_number_at(content, close_idx) if close_idx != -1 else line_start
            recv_type = ""
            if recv_raw:
                recv_parts = recv_raw.split()
                recv_type = recv_parts[-1].lstrip("*")
            caller_qual = f"{recv_type}.{name}" if recv_type else name
            calls, edges = TypeScriptDeepExtractor._extract_ts_calls(body, caller_qual, rel_path, line_start)
            result.call_edges.extend(edges)
            recv_prefix = f"({recv_raw}) " if recv_raw else ""
            ret_suffix = f" {ret_raw}" if ret_raw else ""
            sig = f"func {recv_prefix}{name}({params_raw}){ret_suffix}"
            result.symbols.append(
                ExtractedSymbol(
                    name=name,
                    kind="receiver_method" if recv_raw else "function",
                    signature=sig,
                    line_start=line_start,
                    line_end=line_end,
                    exported=exported,
                    receiver=recv_raw,
                    parent=recv_type,
                    parameters=[p.strip() for p in params_raw.split(",") if p.strip()],
                    return_type=ret_raw,
                    calls=calls[:25],
                )
            )
            if exported and not recv_raw:
                result.exports.append(name)
        # Routes
        for m in cls.GO_ROUTE_RE.finditer(content):
            verb = m.group(1).upper()
            method = "ANY" if verb in {"HANDLEFUNC", "HANDLE"} else verb
            path_str = m.group(2)
            handler = m.group(3)
            line = _line_number_at(content, m.start())
            result.routes.append(
                ExtractedRoute(
                    method=method,
                    path=path_str,
                    handler_name=handler,
                    framework="Go net/http / Router",
                    line=line,
                    file_path=rel_path,
                )
            )
        return result


# =====================================================================
# 4. RUST DEEP EXTRACTOR
# =====================================================================


class RustDeepExtractor:
    """
    Deep structural extractor for Rust (.rs) source files:
    - pub struct / struct with derive attributes and typed fields
    - pub enum / enum with variants
    - pub trait / trait definitions
    - impl Trait for Type and inherent impl Type blocks with methods
    - pub async fn / pub fn / fn and macro_rules!
    - Actix-web / Axum / Rocket route attributes (#[get("/...")], .route("/...", ...))
    """
    STRUCT_RE = re.compile(
        r"(?m)(?:^[ \t]*#\[derive\(([^)]*)\)\]\s*\n)?^[ \t]*(pub(?:\([^)]+\))?\s+)?struct\s+([A-Za-z_][A-Za-z0-9_]*)(?:<[^>]+>)?\s*(?:\{|;|\()"
    )
    ENUM_RE = re.compile(
        r"(?m)(?:^[ \t]*#\[derive\(([^)]*)\)\]\s*\n)?^[ \t]*(pub(?:\([^)]+\))?\s+)?enum\s+([A-Za-z_][A-Za-z0-9_]*)(?:<[^>]+>)?\s*\{"
    )
    TRAIT_RE = re.compile(
        r"(?m)^[ \t]*(pub(?:\([^)]+\))?\s+)?(unsafe\s+)?trait\s+([A-Za-z_][A-Za-z0-9_]*)(?:<[^>]+>)?(?:\s*:\s*([^{]+))?\s*\{"
    )
    IMPL_RE = re.compile(
        r"(?m)^[ \t]*(?:unsafe\s+)?impl(?:<[^>]+>)?\s+(?:([A-Za-z0-9_:<>]+)\s+for\s+)?([A-Za-z0-9_:<>]+)(?:\s+where[^{]+)?\s*\{"
    )
    FN_RE = re.compile(
        r"(?m)^[ \t]*(pub(?:\([^)]+\))?\s+)?(const\s+)?(async\s+)?(unsafe\s+)?fn\s+([A-Za-z_][A-Za-z0-9_]*)(?:<[^>]+>)?\s*\(([^)]*)\)(?:\s*->\s*([^{\n]+))?\s*(?:where[^{]+)?\{"
    )
    MACRO_RE = re.compile(r"(?m)^[ \t]*macro_rules!\s+([A-Za-z_][A-Za-z0-9_]*)")
    RUST_ATTR_ROUTE_RE = re.compile(
        r'(?m)#\[(get|post|put|delete|patch|head|options)\(\s*"([^"]+)"[^\]]*\)\]\s*(?:\n\s*)*(?:pub\s+)?(?:async\s+)?fn\s+([A-Za-z_][A-Za-z0-9_]*)'
    )
    @classmethod
    def extract(cls, content: str, rel_path: str = "lib.rs") -> DeepFileExtraction:
        result = DeepFileExtraction(rel_path=rel_path, language="rust", ext=".rs")
        for m in re.finditer(r"(?m)^\s*(?:pub\s+)?use\s+([^;]+);", content):
            result.imports.append(m.group(1).strip())
        # Structs
        for m in cls.STRUCT_RE.finditer(content):
            derives = [d.strip() for d in (m.group(1) or "").split(",") if d.strip()]
            exported = bool(m.group(2))
            name = m.group(3)
            line_start = _line_number_at(content, m.start())
            fields: List[Dict[str, Any]] = []
            line_end = line_start
            if content[m.end() - 1] == "{":
                body, close_idx = _extract_balanced_block(content, m.end() - 1, "{", "}")
                line_end = _line_number_at(content, close_idx) if close_idx != -1 else line_start
                for f_match in re.finditer(
                    r"(?m)^[ \t]*(pub(?:\([^)]+\))?\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*:\s*([^,\n]+)",
                    body,
                ):
                    fields.append(
                        {
                            "name": f_match.group(2),
                            "type": f_match.group(3).strip(),
                            "exported": bool(f_match.group(1)),
                            "line": line_start + _line_number_at(body, f_match.start()) - 1,
                        }
                    )
            sig = f"{'pub ' if exported else ''}struct {name}"
            result.schemas.append(
                ExtractedSchema(
                    name=name,
                    schema_kind="rust_struct",
                    line_start=line_start,
                    line_end=line_end,
                    fields=fields,
                    bases=derives,
                    exported=exported,
                )
            )
            result.symbols.append(
                ExtractedSymbol(
                    name=name,
                    kind="struct",
                    signature=sig,
                    line_start=line_start,
                    line_end=line_end,
                    exported=exported,
                    decorators=[f"#[derive({', '.join(derives)})]"] if derives else [],
                    metadata={"field_count": len(fields)},
                )
            )
            if exported:
                result.exports.append(name)
        # Enums
        for m in cls.ENUM_RE.finditer(content):
            derives = [d.strip() for d in (m.group(1) or "").split(",") if d.strip()]
            exported = bool(m.group(2))
            name = m.group(3)
            line_start = _line_number_at(content, m.start())
            body, close_idx = _extract_balanced_block(content, m.end() - 1, "{", "}")
            line_end = _line_number_at(content, close_idx) if close_idx != -1 else line_start
            variants: List[Dict[str, Any]] = []
            for v_match in re.finditer(
                r"(?m)^[ \t]*([A-Z][A-Za-z0-9_]*)(?:\s*\(([^)]*)\)|\s*\{([^}]*)\})?", body
            ):
                variants.append(
                    {
                        "name": v_match.group(1),
                        "type": (v_match.group(2) or v_match.group(3) or "Unit").strip(),
                        "line": line_start + _line_number_at(body, v_match.start()) - 1,
                    }
                )
            result.schemas.append(
                ExtractedSchema(
                    name=name,
                    schema_kind="rust_enum",
                    line_start=line_start,
                    line_end=line_end,
                    fields=variants,
                    bases=derives,
                    exported=exported,
                )
            )
            result.symbols.append(
                ExtractedSymbol(
                    name=name,
                    kind="enum",
                    signature=f"{'pub ' if exported else ''}enum {name}",
                    line_start=line_start,
                    line_end=line_end,
                    exported=exported,
                    decorators=[f"#[derive({', '.join(derives)})]"] if derives else [],
                )
            )
            if exported:
                result.exports.append(name)
        # Traits
        for m in cls.TRAIT_RE.finditer(content):
            exported = bool(m.group(1))
            name = m.group(3)
            supertraits = [s.strip() for s in (m.group(4) or "").split("+") if s.strip()]
            line_start = _line_number_at(content, m.start())
            body, close_idx = _extract_balanced_block(content, m.end() - 1, "{", "}")
            line_end = _line_number_at(content, close_idx) if close_idx != -1 else line_start
            trait_methods = [
                {"name": fm.group(1), "type": fm.group(0).strip().rstrip("{;")}
                for fm in re.finditer(r"fn\s+([A-Za-z_][A-Za-z0-9_]*)\s*\([^)]*\)(?:\s*->\s*[^;{]+)?", body)
            ]
            result.schemas.append(
                ExtractedSchema(
                    name=name,
                    schema_kind="rust_trait",
                    line_start=line_start,
                    line_end=line_end,
                    fields=trait_methods,
                    bases=supertraits,
                    exported=exported,
                )
            )
            result.symbols.append(
                ExtractedSymbol(
                    name=name,
                    kind="trait",
                    signature=f"{'pub ' if exported else ''}trait {name}",
                    line_start=line_start,
                    line_end=line_end,
                    exported=exported,
                    bases=supertraits,
                )
            )
            if exported:
                result.exports.append(name)
        # Impl blocks
        impl_ranges: List[Tuple[int, int, str, str]] = []
        for m in cls.IMPL_RE.finditer(content):
            trait_name = (m.group(1) or "").strip()
            target_type = m.group(2).strip()
            _, close_idx = _extract_balanced_block(content, m.end() - 1, "{", "}")
            if close_idx != -1:
                impl_ranges.append((m.start(), close_idx, target_type, trait_name))
                line_start = _line_number_at(content, m.start())
                line_end = _line_number_at(content, close_idx)
                sig = f"impl {trait_name} for {target_type}" if trait_name else f"impl {target_type}"
                result.symbols.append(
                    ExtractedSymbol(
                        name=sig,
                        kind="impl_block",
                        signature=sig,
                        line_start=line_start,
                        line_end=line_end,
                        exported=True,
                        bases=[trait_name] if trait_name else [],
                        parent=target_type,
                    )
                )
        # Functions & impl methods
        for m in cls.FN_RE.finditer(content):
            exported = bool(m.group(1))
            is_async = bool(m.group(3))
            name = m.group(5)
            params_raw = m.group(6).strip()
            ret_type = (m.group(7) or "").strip()
            line_start = _line_number_at(content, m.start())
            body, close_idx = _extract_balanced_block(content, m.end() - 1, "{", "}")
            line_end = _line_number_at(content, close_idx) if close_idx != -1 else line_start
            parent_type = ""
            impl_trait = ""
            for r_start, r_end, t_type, tr_name in impl_ranges:
                if r_start <= m.start() <= r_end:
                    parent_type = t_type
                    impl_trait = tr_name
                    break
            caller = f"{parent_type}::{name}" if parent_type else name
            calls, edges = TypeScriptDeepExtractor._extract_ts_calls(body, caller, rel_path, line_start)
            result.call_edges.extend(edges)
            sig = f"{'pub ' if exported else ''}{'async ' if is_async else ''}fn {name}({params_raw}){' -> ' + ret_type if ret_type else ''}"
            result.symbols.append(
                ExtractedSymbol(
                    name=name,
                    kind="method" if parent_type else ("async_function" if is_async else "function"),
                    signature=sig,
                    line_start=line_start,
                    line_end=line_end,
                    exported=exported,
                    is_async=is_async,
                    parent=parent_type,
                    bases=[impl_trait] if impl_trait else [],
                    parameters=[p.strip() for p in params_raw.split(",") if p.strip()],
                    return_type=ret_type,
                    calls=calls[:25],
                )
            )
            if exported and not parent_type:
                result.exports.append(name)
        # Macros
        for m in cls.MACRO_RE.finditer(content):
            m_name = m.group(1)
            line = _line_number_at(content, m.start())
            result.symbols.append(
                ExtractedSymbol(
                    name=f"{m_name}!",
                    kind="macro",
                    signature=f"macro_rules! {m_name}",
                    line_start=line,
                    exported=True,
                )
            )
        # Actix / Rocket attribute routes
        for m in cls.RUST_ATTR_ROUTE_RE.finditer(content):
            result.routes.append(
                ExtractedRoute(
                    method=m.group(1).upper(),
                    path=m.group(2),
                    handler_name=m.group(3),
                    framework="Actix/Rocket",
                    line=_line_number_at(content, m.start()),
                    file_path=rel_path,
                )
            )
        return result


# =====================================================================
# 5. SQL / GRAPHQL / PROTOBUF DECLARATIVE SCHEMA EXTRACTOR
# =====================================================================


class DeclarativeSchemaExtractor:
    """
    Extracts structured schemas, tables, GraphQL operations, and gRPC services from:
    - SQL (.sql): CREATE TABLE, CREATE VIEW, CREATE INDEX, CREATE FUNCTION
    - GraphQL (.graphql, .gql): type Query, type Mutation, type Subscription, type, input, enum
    - Protobuf (.proto): message, enum, service { rpc ... }
    """
    SQL_TABLE_RE = re.compile(
        r"(?is)CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z0-9_.\"\[\]\x60]+)\s*\((.*?)\)\s*(?:;|WITH|ENGINE|TABLESPACE)"
    )
    GQL_BLOCK_RE = re.compile(
        r"(?m)^[ \t]*(type|input|interface|enum)\s+([A-Za-z_][A-Za-z0-9_]*)(?:\s+implements\s+([^{]+))?\s*\{"
    )
    PROTO_MSG_RE = re.compile(r"(?m)^[ \t]*(message|enum|service)\s+([A-Za-z_][A-Za-z0-9_]*)\s*\{")
    @classmethod
    def extract(cls, content: str, rel_path: str) -> DeepFileExtraction:
        ext = Path(rel_path).suffix.lower()
        if ext == ".sql":
            return cls._extract_sql(content, rel_path)
        if ext in {".graphql", ".gql"}:
            return cls._extract_graphql(content, rel_path)
        if ext == ".proto":
            return cls._extract_protobuf(content, rel_path)
        if re.search(r"(?i)\bCREATE\s+TABLE\b", content):
            return cls._extract_sql(content, rel_path)
        if re.search(r"(?m)^\s*syntax\s*=\s*[\"']proto", content):
            return cls._extract_protobuf(content, rel_path)
        return cls._extract_graphql(content, rel_path)
    @classmethod
    def _extract_sql(cls, content: str, rel_path: str) -> DeepFileExtraction:
        result = DeepFileExtraction(rel_path=rel_path, language="sql", ext=".sql")
        bt = chr(96)
        strip_chars = '"\'[]' + bt
        for m in cls.SQL_TABLE_RE.finditer(content):
            raw_table = m.group(1).strip(strip_chars)
            body = m.group(2)
            line_start = _line_number_at(content, m.start())
            line_end = _line_number_at(content, m.end())
            cols: List[Dict[str, Any]] = []
            fks: List[str] = []
            for idx, line in enumerate(body.splitlines(), start=1):
                clean = re.sub(r"--.*$", "", line).strip().rstrip(",")
                if not clean:
                    continue
                upper = clean.upper()
                if upper.startswith(("PRIMARY KEY", "FOREIGN KEY", "CONSTRAINT", "UNIQUE", "CHECK", "INDEX", "KEY")):
                    ref_m = re.search(r"(?i)REFERENCES\s+([A-Za-z0-9_.]+)", clean)
                    if ref_m:
                        fks.append(ref_m.group(1))
                    continue
                parts = clean.split()
                if len(parts) >= 2:
                    col_name = parts[0].strip(strip_chars)
                    col_type = parts[1]
                    ref_m = re.search(r"(?i)REFERENCES\s+([A-Za-z0-9_.]+)", clean)
                    if ref_m:
                        fks.append(ref_m.group(1))
                    cols.append(
                        {
                            "name": col_name,
                            "type": col_type,
                            "required": "NOT NULL" in upper or "PRIMARY KEY" in upper,
                            "primary_key": "PRIMARY KEY" in upper,
                            "line": line_start + idx - 1,
                        }
                    )
            result.schemas.append(
                ExtractedSchema(
                    name=raw_table,
                    schema_kind="sql_table",
                    line_start=line_start,
                    line_end=line_end,
                    fields=cols,
                    bases=fks,
                    exported=True,
                )
            )
            result.symbols.append(
                ExtractedSymbol(
                    name=raw_table,
                    kind="sql_table",
                    signature=f"CREATE TABLE {raw_table} ({len(cols)} columns)",
                    line_start=line_start,
                    line_end=line_end,
                    bases=fks,
                    metadata={"column_count": len(cols)},
                )
            )
            result.exports.append(raw_table)
        return result
    @classmethod
    def _extract_graphql(cls, content: str, rel_path: str) -> DeepFileExtraction:
        result = DeepFileExtraction(
            rel_path=rel_path, language="graphql", ext=Path(rel_path).suffix.lower() or ".graphql"
        )
        for m in cls.GQL_BLOCK_RE.finditer(content):
            kw = m.group(1)
            name = m.group(2)
            impl_raw = (m.group(3) or "").strip()
            bases = [b.strip() for b in impl_raw.split("&") if b.strip()]
            line_start = _line_number_at(content, m.start())
            body, close_idx = _extract_balanced_block(content, m.end() - 1, "{", "}")
            line_end = _line_number_at(content, close_idx) if close_idx != -1 else line_start
            fields: List[Dict[str, Any]] = []
            for idx, raw_line in enumerate(body.splitlines(), start=1):
                s = re.sub(r"#.*$", "", raw_line).strip()
                if not s:
                    continue
                if kw == "enum":
                    fields.append({"name": s, "type": "EnumValue", "required": True, "line": line_start + idx - 1})
                else:
                    fm = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)(?:\(([^)]*)\))?\s*:\s*(.+)$", s)
                    if fm:
                        f_name = fm.group(1)
                        f_args = (fm.group(2) or "").strip()
                        f_type = fm.group(3).strip()
                        fields.append(
                            {
                                "name": f_name,
                                "type": f_type,
                                "args": f_args,
                                "required": f_type.endswith("!"),
                                "line": line_start + idx - 1,
                            }
                        )
                        if name in {"Query", "Mutation", "Subscription"}:
                            result.routes.append(
                                ExtractedRoute(
                                    method=name.upper(),
                                    path=f"graphql://{name}.{f_name}",
                                    handler_name=f_name,
                                    framework="GraphQL",
                                    line=line_start + idx - 1,
                                    file_path=rel_path,
                                    response_model=f_type,
                                )
                            )
            result.schemas.append(
                ExtractedSchema(
                    name=name,
                    schema_kind=f"graphql_{kw}",
                    line_start=line_start,
                    line_end=line_end,
                    fields=fields,
                    bases=bases,
                    exported=True,
                )
            )
            result.symbols.append(
                ExtractedSymbol(
                    name=name,
                    kind=f"graphql_{kw}",
                    signature=f"{kw} {name}",
                    line_start=line_start,
                    line_end=line_end,
                    bases=bases,
                    metadata={"field_count": len(fields)},
                )
            )
            result.exports.append(name)
        return result
    @classmethod
    def _extract_protobuf(cls, content: str, rel_path: str) -> DeepFileExtraction:
        result = DeepFileExtraction(rel_path=rel_path, language="protobuf", ext=".proto")
        for imp in re.findall(r'(?m)^\s*import\s+"([^"]+)"\s*;', content):
            result.imports.append(imp)
        for m in cls.PROTO_MSG_RE.finditer(content):
            kw = m.group(1)
            name = m.group(2)
            line_start = _line_number_at(content, m.start())
            body, close_idx = _extract_balanced_block(content, m.end() - 1, "{", "}")
            line_end = _line_number_at(content, close_idx) if close_idx != -1 else line_start
            fields: List[Dict[str, Any]] = []
            if kw == "service":
                rpc_re = re.compile(
                    r"rpc\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(\s*(?:stream\s+)?([A-Za-z0-9_.]+)\s*\)\s*returns\s*\(\s*(?:stream\s+)?([A-Za-z0-9_.]+)\s*\)"
                )
                for rm in rpc_re.finditer(body):
                    rpc_name, req_t, resp_t = rm.group(1), rm.group(2), rm.group(3)
                    rpc_line = line_start + _line_number_at(body, rm.start()) - 1
                    fields.append({"name": rpc_name, "type": f"({req_t}) -> {resp_t}", "line": rpc_line})
                    result.routes.append(
                        ExtractedRoute(
                            method="GRPC",
                            path=f"/{name}/{rpc_name}",
                            handler_name=rpc_name,
                            framework="gRPC / Protobuf",
                            line=rpc_line,
                            file_path=rel_path,
                            response_model=resp_t,
                        )
                    )
            elif kw == "message":
                field_re = re.compile(
                    r"(?m)^[ \t]*(repeated\s+|optional\s+|required\s+)?([A-Za-z0-9_.<>]+)\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(\d+)"
                )
                for fm in field_re.finditer(body):
                    mod = (fm.group(1) or "").strip()
                    f_type = fm.group(2)
                    f_name = fm.group(3)
                    tag_num = int(fm.group(4))
                    fields.append(
                        {
                            "name": f_name,
                            "type": f"{mod} {f_type}".strip(),
                            "tag_number": tag_num,
                            "required": mod != "optional",
                            "line": line_start + _line_number_at(body, fm.start()) - 1,
                        }
                    )
            elif kw == "enum":
                for em in re.finditer(r"(?m)^[ \t]*([A-Z0-9_]+)\s*=\s*(\d+)", body):
                    fields.append({"name": em.group(1), "type": "EnumField", "tag_number": int(em.group(2))})
            result.schemas.append(
                ExtractedSchema(
                    name=name,
                    schema_kind=f"protobuf_{kw}",
                    line_start=line_start,
                    line_end=line_end,
                    fields=fields,
                    exported=True,
                )
            )
            result.symbols.append(
                ExtractedSymbol(
                    name=name,
                    kind=f"protobuf_{kw}",
                    signature=f"{kw} {name}",
                    line_start=line_start,
                    line_end=line_end,
                    metadata={"field_count": len(fields)},
                )
            )
            result.exports.append(name)
        return result


# =====================================================================
# 6. UNIFIED POLYGLOT FACADE & REPOSITORY AGGREGATORS
# =====================================================================


class DeepPolyglotExtractor:
    """
    Unified polyglot router that dispatches source files to the appropriate deep language extractor
    and builds repository-wide symbol tables, API route catalogs, schema registries, and call graphs.
    """
    PYTHON_EXTS = {".py", ".pyi"}
    TS_JS_EXTS = {".ts", ".tsx", ".js", ".jsx", ".mts", ".cts", ".mjs", ".cjs"}
    GO_EXTS = {".go"}
    RUST_EXTS = {".rs"}
    DECLARATIVE_EXTS = {".sql", ".graphql", ".gql", ".proto"}
    @classmethod
    def extract_file(cls, content: str, rel_path: str, ext: Optional[str] = None) -> DeepFileExtraction:
        resolved_ext = (ext or Path(rel_path).suffix).lower()
        if resolved_ext in cls.PYTHON_EXTS:
            return PythonDeepExtractor.extract(content, rel_path=rel_path)
        if resolved_ext in cls.TS_JS_EXTS:
            return TypeScriptDeepExtractor.extract(content, rel_path=rel_path)
        if resolved_ext in cls.GO_EXTS:
            return GoDeepExtractor.extract(content, rel_path=rel_path)
        if resolved_ext in cls.RUST_EXTS:
            return RustDeepExtractor.extract(content, rel_path=rel_path)
        if resolved_ext in cls.DECLARATIVE_EXTS:
            return DeclarativeSchemaExtractor.extract(content, rel_path=rel_path)
        return DeepFileExtraction(rel_path=rel_path, language="generic", ext=resolved_ext)
    @classmethod
    def extract_repository(cls, files: Any) -> Dict[str, Any]:
        """
        Accepts a repo root path (str | Path), a RepoAnalysis object, or an iterable of FileNode objects/dicts/tuples
        (rel_path, raw_content, ext) and returns a comprehensive polyglot architectural inventory.
        """
        if isinstance(files, (str, Path)):
            from ..engine import ContextCompiler
            files = ContextCompiler(files).scan_and_compile().files
        elif hasattr(files, "files") and isinstance(getattr(files, "files"), list):
            files = getattr(files, "files")

        per_file: Dict[str, DeepFileExtraction] = {}
        all_routes: List[Dict[str, Any]] = []
        all_schemas: List[Dict[str, Any]] = []
        all_symbols: List[Dict[str, Any]] = []
        for item in files:
            if hasattr(item, "rel_path") and hasattr(item, "raw_content"):
                rel_path = item.rel_path
                raw_content = item.raw_content
                ext = getattr(item, "ext", Path(rel_path).suffix)
            elif isinstance(item, dict):
                rel_path = str(item.get("rel_path", ""))
                raw_content = str(item.get("raw_content", ""))
                ext = str(item.get("ext", Path(rel_path).suffix))
            elif isinstance(item, tuple) and len(item) >= 2:
                rel_path = str(item[0])
                raw_content = str(item[1])
                ext = str(item[2]) if len(item) > 2 else Path(rel_path).suffix
            else:
                continue
            extraction = cls.extract_file(raw_content, rel_path=rel_path, ext=ext)
            per_file[rel_path] = extraction
            for r in extraction.routes:
                all_routes.append(r.to_dict())
            for sc in extraction.schemas:
                sc_dict = sc.to_dict()
                sc_dict["file_path"] = rel_path
                all_schemas.append(sc_dict)
            for sym in extraction.symbols:
                sym_dict = sym.to_dict()
                sym_dict["file_path"] = rel_path
                all_symbols.append(sym_dict)
        cross_calls = build_cross_file_call_graph(per_file)
        return {
            "total_files_extracted": len(per_file),
            "total_symbols": len(all_symbols),
            "total_routes": len(all_routes),
            "total_schemas": len(all_schemas),
            "total_cross_file_calls": len(cross_calls),
            "routes": all_routes,
            "schemas": all_schemas,
            "symbols": all_symbols,
            "cross_file_call_graph": cross_calls,
            "files": {p: ext_obj.to_dict() for p, ext_obj in per_file.items()},
        }


def extract_file_symbols(content: str, rel_path: str, ext: Optional[str] = None) -> DeepFileExtraction:
    """Convenience function to extract symbols, routes, schemas, and call edges from a single file."""
    return DeepPolyglotExtractor.extract_file(content=content, rel_path=rel_path, ext=ext)


def extract_repository_symbols(files: Iterable[Any]) -> Dict[str, Any]:
    """Convenience function to run deep polyglot extraction across an entire repository."""
    return DeepPolyglotExtractor.extract_repository(files)


def build_cross_file_call_graph(extractions: Dict[str, DeepFileExtraction]) -> List[Dict[str, Any]]:
    """
    Resolves intra-file and cross-file symbol calls by linking caller symbols in file A
    to exported symbols in file B (or same file).
    """
    symbol_index: Dict[str, List[Tuple[str, str]]] = {}
    for rel_path, ext_obj in extractions.items():
        for sym in ext_obj.symbols:
            symbol_index.setdefault(sym.name, []).append((rel_path, sym.kind))
    resolved_edges: List[Dict[str, Any]] = []
    seen: Set[Tuple[str, str, str, str]] = set()
    for src_path, ext_obj in extractions.items():
        for ce in ext_obj.call_edges:
            leaf_callee = ce.callee.split(".")[-1].split("::")[-1]
            targets = symbol_index.get(leaf_callee, [])
            for dst_path, dst_kind in targets:
                key = (src_path, ce.caller, dst_path, leaf_callee)
                if key in seen:
                    continue
                seen.add(key)
                resolved_edges.append(
                    {
                        "source_file": src_path,
                        "caller": ce.caller,
                        "target_file": dst_path,
                        "callee": leaf_callee,
                        "callee_kind": dst_kind,
                        "cross_file": src_path != dst_path,
                        "line": ce.line,
                    }
                )
    return resolved_edges
