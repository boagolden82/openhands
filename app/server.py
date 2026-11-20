"""HTTP 服务：标准库实现，零第三方依赖，便于 Windows 免安装运行。"""
from __future__ import annotations

import json
import mimetypes
import re
import threading
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable

from . import config
from .importer import import_csv, template_csv
from .metrics import DIM_KEYS, MetricError, MetricsEngine
from .ontology import Ontology, OntologyError
from .report import build_report
from .seed import seed
from .store import FactStore

mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("image/svg+xml", ".svg")

ROUTES: list[tuple[str, re.Pattern[str], Callable[..., Any]]] = []


def route(method: str, pattern: str):
    def wrapper(fn):
        ROUTES.append((method, re.compile(f"^{pattern}$"), fn))
        return fn
    return wrapper


class AppContext:
    def __init__(self) -> None:
        self.onto = Ontology.load(config.ontology_path())
        self.store = FactStore(config.db_path())
        self.engine = MetricsEngine(self.onto, self.store)
        if self.store.counts()["facts"] == 0:
            seed(self.onto, self.store)


CTX: AppContext | None = None


def context() -> AppContext:
    global CTX
    if CTX is None:
        CTX = AppContext()
    return CTX


# ------------------------------------------------------------------ 路由
@route("GET", r"/api/health")
def health(req) -> dict[str, Any]:
    ctx = context()
    return {"status": "ok", "version": ctx.onto.version, "name": ctx.onto.name,
            "counts": ctx.store.counts()}


@route("GET", r"/api/overview")
def overview(req) -> dict[str, Any]:
    ctx = context()
    granularity = req.query.get("granularity", "week")
    periods = int(req.query.get("periods", 12))
    result = ctx.engine.compute(granularity=granularity, periods=periods)
    visible = {k: v for k, v in result["metrics"].items() if not v["hidden"]}
    kpis = {k: v for k, v in visible.items() if v.get("primary") or v.get("indicator")}
    indicator = next((v for v in result["metrics"].values() if v["indicator"]), None)
    return {
        "window": result["window"],
        "indicator": indicator,
        "kpis": list(kpis.values()),
        "metrics": result["metrics"],
        "coverage": result["coverage"],
        "insights": ctx.engine.insights(granularity=granularity, periods=periods),
        "groups": ctx.engine.breakdown("rde_index", "projectGroup", granularity, periods)["items"],
        "compare": ctx.engine.compare(),
        "counts": ctx.store.counts(),
    }


@route("GET", r"/api/metrics")
def metrics_list(req) -> dict[str, Any]:
    ctx = context()
    return {
        "metrics": [
            {
                "id": m["id"], "code": m.get("code"), "label": m["label"],
                "unit": m.get("unit", ""),
                "type": m.get("type"), "layer": m.get("layer"),
                "description": m.get("description", ""), "formula": m.get("formula", ""),
                "owner": m.get("owner", ""), "target": m.get("target"),
                "direction": m.get("direction"), "hidden": bool(m.get("hidden")),
                "indicator": bool(m.get("indicator")), "deps": m.get("deps", []),
                "fact": m.get("fact"), "realtime": bool(m.get("realtime")),
            }
            for m in ctx.onto.metrics
        ],
        "dimensions": ctx.onto.dimensions,
    }


@route("GET", r"/api/metrics/(?P<mid>[\w\-]+)")
def metric_detail(req, mid: str) -> dict[str, Any]:
    ctx = context()
    granularity = req.query.get("granularity", "week")
    periods = int(req.query.get("periods", 12))
    filters = {k: v for k, v in req.query.items() if k in DIM_KEYS}
    result = ctx.engine.compute([mid], granularity=granularity, periods=periods, filters=filters)
    if mid not in result["metrics"]:
        raise KeyError(mid)
    metric = result["metrics"][mid]
    definition = ctx.onto.metric(mid) or {}
    metric["definition"] = definition
    metric["deps"] = ctx.onto.dependency_closure(mid)
    metric["dependents"] = ctx.onto.dependents(mid)
    metric["breakdown"] = {}
    for dim in ("projectGroup", "project", "phase"):
        data = ctx.engine.breakdown(mid, dim, granularity, periods)
        if data["items"]:
            metric["breakdown"][dim] = data["items"]
    metric["window"] = result["window"]
    return metric


@route("GET", r"/api/compare")
def compare(req) -> dict[str, Any]:
    ctx = context()
    base = None
    current = None
    if req.query.get("baseStart") and req.query.get("baseEnd"):
        base = (req.query["baseStart"], req.query["baseEnd"])
    if req.query.get("currentStart") and req.query.get("currentEnd"):
        current = (req.query["currentStart"], req.query["currentEnd"])
    filters = {k: v for k, v in req.query.items() if k in DIM_KEYS}
    return ctx.engine.compare(base=base, current=current, filters=filters)


@route("GET", r"/api/ontology")
def ontology_get(req) -> dict[str, Any]:
    return context().onto.to_dict()


@route("GET", r"/api/lineage")
def lineage(req) -> dict[str, Any]:
    return context().engine.lineage(req.query.get("metric"))


@route("GET", r"/api/quality")
def quality(req) -> dict[str, Any]:
    return context().engine.quality()


@route("GET", r"/api/facts")
def facts(req) -> dict[str, Any]:
    ctx = context()
    ftype = req.query.get("factType") or None
    limit = min(int(req.query.get("limit", 100)), 1000)
    offset = max(int(req.query.get("offset", 0)), 0)
    rows = ctx.store.facts(ftype, req.query.get("start"), req.query.get("end"))
    rows.sort(key=lambda r: r["occurred_at"], reverse=True)
    return {"total": len(rows), "rows": rows[offset: offset + limit],
            "factTypes": [
                {"id": f.id, "label": f.label, "subject": f.subject,
                 "timeField": f.time_field, "measures": list(f.measures),
                 "fields": list(f.fields), "description": f.description,
                 "count": ctx.store.counts()["byFactType"].get(f.id, 0)}
                for f in ctx.onto.fact_types.values()
            ]}


@route("GET", r"/api/import/template")
def import_template(req) -> tuple[bytes, str, str]:
    fact_type = req.query.get("factType", "")
    content = template_csv(context().onto, fact_type)
    return content.encode("utf-8-sig"), "text/csv; charset=utf-8", f"template-{fact_type}.csv"


@route("POST", r"/api/import")
def import_facts(req) -> dict[str, Any]:
    ctx = context()
    payload = req.json()
    import base64
    content = base64.b64decode(payload.get("content", ""))
    return import_csv(ctx.onto, ctx.store, content, payload.get("filename", "upload.csv"),
                      payload.get("factType") or None, bool(payload.get("dryRun")))


@route("GET", r"/api/import/logs")
def import_logs(req) -> dict[str, Any]:
    return {"logs": context().store.import_logs()}


@route("POST", r"/api/forecast")
def forecast(req) -> dict[str, Any]:
    payload = req.json()
    return context().engine.forecast(
        payload.get("metric", "mr_dev_done_count"),
        int(payload.get("periods", 12)),
        payload.get("remaining"),
        int(payload.get("simulations", 2000)),
    )


@route("GET", r"/api/report")
def report(req) -> tuple[bytes, str, str]:
    ctx = context()
    fmt = req.query.get("format", "html")
    granularity = req.query.get("granularity", "week")
    periods = int(req.query.get("periods", 12))
    content, mime, filename = build_report(ctx, fmt, granularity, periods)
    return content, mime, filename


@route("POST", r"/api/reseed")
def reseed(req) -> dict[str, Any]:
    ctx = context()
    info = seed(ctx.onto, ctx.store)
    return {"ok": True, **info}


@route("GET", r"/api/settings")
def settings_get(req) -> dict[str, Any]:
    ctx = context()
    return {
        "dataDir": str(config.data_root()),
        "dbPath": str(config.db_path()),
        "ontologyPath": str(config.ontology_path()),
        "ontologyVersion": ctx.onto.version,
        "seededAt": ctx.store.get_setting("seeded_at"),
        "counts": ctx.store.counts(),
    }


# ------------------------------------------------------------------ 请求/响应
class Handler(BaseHTTPRequestHandler):
    server_version = "RDE-Onto"
    protocol_version = "HTTP/1.1"

    class Request:
        def __init__(self, query: dict[str, str], body: bytes):
            self.query = query
            self.body = body

        def json(self) -> dict[str, Any]:
            return json.loads(self.body.decode("utf-8")) if self.body else {}

    def log_message(self, fmt: str, *args) -> None:  # 静默访问日志
        return

    def _send(self, status: int, payload: bytes, content_type: str,
              extra: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    def _json(self, status: int, data: Any) -> None:
        self._send(status, json.dumps(data, ensure_ascii=False, default=str).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _handle(self, method: str) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""

        if path.startswith("/api/"):
            for route_method, pattern, fn in ROUTES:
                match = pattern.match(path)
                if match and route_method == method:
                    try:
                        result = fn(Handler.Request(query, body), **match.groupdict())
                    except KeyError as exc:
                        self._json(HTTPStatus.NOT_FOUND, {"error": f"未找到：{exc}"})
                        return
                    except (OntologyError, MetricError, ValueError) as exc:
                        self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                        return
                    except Exception as exc:  # noqa: BLE001
                        self._json(HTTPStatus.INTERNAL_SERVER_ERROR,
                                   {"error": f"{type(exc).__name__}: {exc}"})
                        return
                    if isinstance(result, tuple):
                        payload, mime, filename = result
                        self._send(HTTPStatus.OK, payload, mime,
                                   {"Content-Disposition": f'attachment; filename="{filename}"'})
                    else:
                        self._json(HTTPStatus.OK, result)
                    return
            self._json(HTTPStatus.NOT_FOUND, {"error": f"未知接口：{method} {path}"})
            return
        self._static(path)

    def _static(self, path: str) -> None:
        root = config.web_root().resolve()
        rel = "index.html" if path == "/" else path.lstrip("/")
        target = (root / rel).resolve()
        if not str(target).startswith(str(root)) or not target.is_file():
            target = root / "index.html"
        if not target.is_file():
            self._send(HTTPStatus.NOT_FOUND, b"web assets missing", "text/plain; charset=utf-8")
            return
        mime = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if mime.startswith("text/") or mime in {"application/javascript", "application/json"}:
            mime += "; charset=utf-8"
        self._send(HTTPStatus.OK, target.read_bytes(), mime)

    def do_GET(self) -> None:
        self._handle("GET")

    def do_POST(self) -> None:
        self._handle("POST")

    def do_HEAD(self) -> None:
        self._handle("GET")


def create_server(host: str | None = None, port: int | None = None) -> ThreadingHTTPServer:
    context()
    # port=0 表示由系统分配空闲端口，不能当作"未指定"处理
    bind_port = config.port() if port is None else port
    return ThreadingHTTPServer((host or config.host(), bind_port), Handler)


def serve_forever() -> None:
    server = create_server()
    print(f"  {config.APP_NAME} 已启动：http://{config.host()}:{config.port()}")
    print(f"  数据文件：{config.db_path()}")
    if config.open_browser():
        threading.Timer(1.0, _open_browser).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  已停止。")


def _open_browser() -> None:
    import webbrowser
    webbrowser.open(f"http://{config.host()}:{config.port()}")
