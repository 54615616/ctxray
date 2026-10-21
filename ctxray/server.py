from __future__ import annotations

import argparse
import json
import mimetypes
import socket
import sys
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import __version__
from .engine import ContextCompiler, PolyglotSkeletonizer, RepoAnalysis, SecretGuard, TokenEstimator
from .graph import run_forensics_report


def parse_budget_param(val: Optional[str], default: int = 32_000) -> int:
    """Parse a budget query parameter such as '32000', '32k', or '128k'."""
    if not val:
        return default
    s = str(val).strip().lower().replace(",", "")
    try:
        if s.endswith("k"):
            return max(1_000, int(float(s[:-1]) * 1_000))
        if s.endswith("m"):
            return max(1_000, int(float(s[:-1]) * 1_000_000))
        return max(1_000, int(float(s)))
    except ValueError:
        return default


def find_free_port(start_port: int = 8420, host: str = "127.0.0.1", max_tries: int = 100) -> int:
    """Find the first available local TCP port starting at start_port (default: 8420)."""
    for port in range(start_port, start_port + max_tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, port))
                return port
            except OSError:
                continue
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


class CtxRayStudioHTTPServer(ThreadingHTTPServer):
    """ThreadingHTTPServer carrying live repository root and Studio paths."""

    allow_reuse_address = True
    daemon_threads = True

    def __init__(
        self,
        server_address: Tuple[str, int],
        RequestHandlerClass: type[BaseHTTPRequestHandler],
        root_path: Path,
        default_budget: int = 32_000,
    ) -> None:
        super().__init__(server_address, RequestHandlerClass)
        self.root_path: Path = root_path.resolve()
        self.default_budget: int = max(1_000, default_budget)
        self.package_root: Path = Path(__file__).resolve().parent.parent
        self.studio_dir: Path = self.package_root / "studio"
        self.assets_dir: Path = self.package_root / "assets"
        self.cache_lock: threading.Lock = threading.Lock()
        self.cache_ttl: float = 5.0
        self._analysis_cache: Dict[int, Tuple[float, RepoAnalysis, Dict[str, Any]]] = {}

    def get_cached_analysis(self, budget: int) -> Tuple[RepoAnalysis, Dict[str, Any]]:
        now = time.monotonic()
        with self.cache_lock:
            cached = self._analysis_cache.get(budget)
            if cached is not None and (now - cached[0]) < self.cache_ttl:
                return cached[1], cached[2]

        compiler = ContextCompiler(self.root_path, budget_tokens=budget)
        analysis = compiler.scan_and_compile()
        payload = analysis.to_dict()
        payload["status"] = "ok"
        payload["live"] = True
        payload["git_diff_summary"] = analysis.git_diff_summary

        by_rel = {f.rel_path: f for f in analysis.files}
        files_list = payload.get("files", [])
        if isinstance(files_list, list):
            for item in files_list:
                if isinstance(item, dict):
                    rel_p = str(item.get("rel_path", ""))
                    item["path"] = rel_p
                    fnode = by_rel.get(rel_p)
                    if fnode is not None:
                        item["raw_preview"] = fnode.raw_content[:1200]
                        item["summary_preview"] = fnode.summary_content[:600]

        with self.cache_lock:
            self._analysis_cache[budget] = (time.monotonic(), analysis, payload)
        return analysis, payload


class CtxRayHTTPRequestHandler(BaseHTTPRequestHandler):
    """Zero-dependency HTTP request handler for ctxray Visual X-Ray Studio & live API."""

    server: CtxRayStudioHTTPServer

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Accept")
        self.send_header("Cache-Control", "no-store")

    def _send_json(self, payload: Dict[str, Any], status: int = 200) -> None:
        raw = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(raw)

    def _send_text(self, content: str, content_type: str = "text/plain; charset=utf-8", status: int = 200) -> None:
        raw = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(raw)

    def _send_bytes(self, raw: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(raw)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        route = parsed.path or "/"
        query = urllib.parse.parse_qs(parsed.query)

        try:
            if route in {"/", "/index.html", "/studio", "/studio/"}:
                self._handle_studio_index()
            elif route.startswith("/assets/"):
                self._handle_assets(route)
            elif route == "/api/analyze":
                self._handle_api_analyze(query)
            elif route == "/api/blast":
                self._handle_api_blast(query)
            elif route == "/api/skeleton":
                self._handle_api_skeleton(query)
            elif route == "/api/bundle":
                self._handle_api_bundle(query)
            elif route == "/api/forensics":
                self._handle_api_forensics(query)
            elif route == "/api/health":
                self._send_json(
                    {
                        "status": "ok",
                        "version": __version__,
                        "root_path": str(self.server.root_path),
                        "repo_name": self.server.root_path.name,
                        "default_budget": self.server.default_budget,
                    }
                )
            else:
                self._send_json({"error": f"Route not found: {route}"}, status=404)
        except Exception as exc:
            self._send_json({"error": str(exc), "route": route}, status=500)

    def _handle_studio_index(self) -> None:
        studio_html = self.server.studio_dir / "index.html"
        if not studio_html.is_file():
            alt_html = self.server.root_path / "studio" / "index.html"
            if alt_html.is_file():
                studio_html = alt_html
        if not studio_html.is_file():
            self._send_json({"error": f"studio/index.html not found at {studio_html}"}, status=404)
            return
        html = studio_html.read_text(encoding="utf-8", errors="ignore")
        self._send_text(html, content_type="text/html; charset=utf-8", status=200)

    def _handle_assets(self, route: str) -> None:
        rel_asset = urllib.parse.unquote(route[len("/assets/") :]).lstrip("/")
        if not rel_asset or ".." in Path(rel_asset).parts:
            self._send_json({"error": "Invalid asset path"}, status=400)
            return

        candidates = [
            (self.server.assets_dir / rel_asset).resolve(),
            (self.server.root_path / "assets" / rel_asset).resolve(),
        ]
        for candidate in candidates:
            if candidate.is_file():
                if (
                    str(candidate).startswith(str(self.server.assets_dir.resolve()))
                    or str(candidate).startswith(str((self.server.root_path / "assets").resolve()))
                ):
                    mime, _ = mimetypes.guess_type(str(candidate))
                    if candidate.suffix.lower() == ".svg":
                        mime = "image/svg+xml; charset=utf-8"
                    self._send_bytes(candidate.read_bytes(), content_type=mime or "application/octet-stream")
                    return
        self._send_json({"error": f"Asset not found: {rel_asset}"}, status=404)

    def _handle_api_analyze(self, query: Dict[str, List[str]]) -> None:
        budget_raw = query.get("budget", [None])[0]
        budget = parse_budget_param(budget_raw, default=self.server.default_budget)
        _, payload = self.server.get_cached_analysis(budget)
        self._send_json(payload)

    def _handle_api_forensics(self, query: Dict[str, List[str]]) -> None:
        budget_raw = query.get("budget", [None])[0]
        budget = parse_budget_param(budget_raw, default=self.server.default_budget)
        analysis, _ = self.server.get_cached_analysis(budget)
        report = run_forensics_report(self.server.root_path, analysis)
        self._send_json(report.to_dict())

    def _handle_api_blast(self, query: Dict[str, List[str]]) -> None:
        target = (
            query.get("target", [None])[0]
            or query.get("file", [None])[0]
            or query.get("path", [None])[0]
            or ""
        ).strip()
        budget_raw = query.get("budget", [None])[0]
        budget = parse_budget_param(budget_raw, default=self.server.default_budget)

        compiler = ContextCompiler(self.server.root_path, budget_tokens=budget)
        if not target:
            analysis = compiler.scan_and_compile()
            if analysis.files:
                target = analysis.files[0].rel_path
            else:
                self._send_json({"error": "Missing 'target' parameter and repository is empty"}, status=400)
                return

        report = compiler.blast_radius(target)
        status_code = 404 if "error" in report else 200
        report["status"] = "error" if "error" in report else "ok"
        self._send_json(report, status=status_code)

    def _resolve_repo_file(self, file_query: str) -> Optional[Tuple[Path, str]]:
        root = self.server.root_path.resolve()
        cleaned = file_query.strip().replace("\\", "/").lstrip("/")
        if not cleaned:
            return None

        direct = (root / cleaned).resolve()
        try:
            rel_posix = direct.relative_to(root).as_posix()
            if direct.is_file():
                return direct, rel_posix
        except ValueError:
            pass

        compiler = ContextCompiler(root, budget_tokens=self.server.default_budget)
        analysis = compiler.scan_and_compile()
        lower_q = cleaned.lower()
        for fnode in analysis.files:
            if fnode.rel_path.lower() == lower_q or lower_q in fnode.rel_path.lower():
                cand = (root / fnode.rel_path).resolve()
                if cand.is_file():
                    return cand, fnode.rel_path
        return None

    def _handle_api_skeleton(self, query: Dict[str, List[str]]) -> None:
        file_param = (
            query.get("file", [None])[0]
            or query.get("path", [None])[0]
            or query.get("target", [None])[0]
            or ""
        ).strip()
        if not file_param:
            self._send_json({"error": "Missing required query parameter: 'file'"}, status=400)
            return

        resolved = self._resolve_repo_file(file_param)
        if resolved is None:
            self._send_json({"error": f"File not found in repository: {file_param}"}, status=404)
            return

        full_path, rel_posix = resolved
        raw_text = full_path.read_text(encoding="utf-8", errors="ignore")
        clean_text, redacted_count = SecretGuard.redact(raw_text)
        ext = full_path.suffix.lower()
        skel_text = PolyglotSkeletonizer.skeletonize(clean_text, ext)
        sum_text = PolyglotSkeletonizer.summarize(clean_text, ext, rel_posix)

        raw_tok = TokenEstimator.estimate(clean_text)
        skel_tok = min(raw_tok, TokenEstimator.estimate(skel_text))
        sum_tok = min(skel_tok, TokenEstimator.estimate(sum_text))
        savings_pct = round((1.0 - skel_tok / max(1, raw_tok)) * 100.0, 1)

        raw_lines = len(clean_text.splitlines())
        skel_lines = len(skel_text.splitlines())

        self._send_json(
            {
                "status": "ok",
                "file": rel_posix,
                "rel_path": rel_posix,
                "ext": ext or ".txt",
                "lines": raw_lines,
                "skeleton_lines": skel_lines,
                "folded_lines": max(0, raw_lines - skel_lines),
                "raw_tokens": raw_tok,
                "skeleton_tokens": skel_tok,
                "summary_tokens": sum_tok,
                "savings_pct": savings_pct,
                "secrets_redacted": redacted_count,
                "raw": clean_text,
                "raw_content": clean_text,
                "skeleton": skel_text,
                "skeleton_content": skel_text,
                "summary": sum_text,
                "summary_content": sum_text,
            }
        )

    def _handle_api_bundle(self, query: Dict[str, List[str]]) -> None:
        budget_raw = query.get("budget", [None])[0]
        budget = parse_budget_param(budget_raw, default=self.server.default_budget)
        fmt = (query.get("format", ["xml"])[0] or "xml").strip().lower()
        if fmt not in {"xml", "md", "markdown", "json"}:
            fmt = "xml"
        raw_flag = (query.get("raw", ["0"])[0] or "0").strip().lower() in {"1", "true", "yes"}

        compiler = ContextCompiler(self.server.root_path, budget_tokens=budget)
        analysis = compiler.scan_and_compile()
        bundle_text = compiler.format_bundle(analysis, fmt=fmt)

        if raw_flag:
            ctype = "application/xml; charset=utf-8" if fmt == "xml" else "text/markdown; charset=utf-8"
            self._send_text(bundle_text, content_type=ctype)
            return

        self._send_json(
            {
                "status": "ok",
                "repo_name": analysis.repo_name,
                "root_path": analysis.root_path,
                "format": fmt,
                "budget_tokens": analysis.budget_tokens,
                "total_files": analysis.total_files,
                "raw_total_tokens": analysis.raw_total_tokens,
                "compiled_total_tokens": analysis.compiled_total_tokens,
                "savings_pct": analysis.savings_pct,
                "estimated_cache_hit_pct": analysis.estimated_cache_hit_pct,
                "secrets_redacted": analysis.secrets_redacted,
                "bundle": bundle_text,
                "content": bundle_text,
            }
        )


class CtxRayStudioServer:
    """High-level wrapper for starting, inspecting, or background-running the local X-Ray server."""

    def __init__(
        self,
        root_path: str | Path = ".",
        port: int = 8420,
        host: str = "127.0.0.1",
        default_budget: int = 32_000,
    ) -> None:
        self.root_path = Path(root_path).resolve()
        self.host = host
        self.default_budget = max(1_000, default_budget)
        self.port = find_free_port(start_port=port, host=host)
        self.httpd = CtxRayStudioHTTPServer(
            (self.host, self.port),
            CtxRayHTTPRequestHandler,
            root_path=self.root_path,
            default_budget=self.default_budget,
        )
        self._thread: Optional[threading.Thread] = None

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def print_banner(self) -> None:
        border = "=" * 74
        print(border)
        print(f"  CTXRAY LIVE X-RAY STUDIO SERVER  v{__version__}")
        print(border)
        print(f"  Repository   : {self.root_path}")
        print(f"  Token Budget : {self.default_budget:,} tokens")
        print(f"  Studio URL   : {self.url}")
        print(f"  Live API     : {self.url}/api/analyze?budget={self.default_budget}")
        print(f"  Blast API    : {self.url}/api/blast?target=<file>")
        print(f"  Skeleton API : {self.url}/api/skeleton?file=<file>")
        print(f"  Bundle API   : {self.url}/api/bundle?budget={self.default_budget}&format=xml")
        print(border)
        print("  Press Ctrl+C to stop the server.")

    def start_background(self) -> str:
        self._thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self._thread.start()
        return self.url

    def serve_forever(self, open_browser: bool = True) -> None:
        self.print_banner()
        if open_browser:
            try:
                webbrowser.open(self.url)
            except Exception:
                pass
        try:
            self.httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[ctxray] Shutting down Live X-Ray Studio server...")
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        try:
            self.httpd.shutdown()
        except Exception:
            pass
        try:
            self.httpd.server_close()
        except Exception:
            pass

    def __enter__(self) -> "CtxRayStudioServer":
        self.start_background()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.shutdown()


def create_studio_server(
    root_path: str | Path = ".",
    port: int = 8420,
    host: str = "127.0.0.1",
    default_budget: int = 32_000,
) -> Tuple[CtxRayStudioHTTPServer, int]:
    """Create and bind a CtxRayStudioHTTPServer on the first free port starting at port."""
    srv = CtxRayStudioServer(
        root_path=root_path, port=port, host=host, default_budget=default_budget
    )
    return srv.httpd, srv.port


def run_studio_server(
    root_path: str | Path = ".",
    port: int = 8420,
    host: str = "127.0.0.1",
    open_browser: bool = True,
    default_budget: int = 32_000,
) -> int:
    """Start the blocking local Live X-Ray Studio HTTP server."""
    srv = CtxRayStudioServer(
        root_path=root_path,
        port=port,
        host=host,
        default_budget=default_budget,
    )
    srv.serve_forever(open_browser=open_browser)
    return 0


serve_studio = run_studio_server
start_server = run_studio_server


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ctxray-studio",
        description="ctxray Live Visual X-Ray Studio HTTP Server",
    )
    parser.add_argument("path", nargs="?", default=".", help="Repository path to inspect (default: .)")
    parser.add_argument("-p", "--port", type=int, default=8420, help="Starting port (default: 8420)")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("-b", "--budget", default="32k", help="Default token budget (default: 32k)")
    parser.add_argument("--no-open", action="store_true", help="Do not open browser automatically")
    args = parser.parse_args(argv)

    budget = parse_budget_param(args.budget, default=32_000)
    return run_studio_server(
        root_path=args.path,
        port=args.port,
        host=args.host,
        open_browser=not args.no_open,
        default_budget=budget,
    )


if __name__ == "__main__":
    raise SystemExit(main())
