"""指标计算引擎。

流程：事实 -> 维度富化（本体推理）-> 原子指标聚合 -> 派生指标求值 -> 复合指标评分。
所有指标口径来自 ontology.json，代码中不出现任何指标常量。
"""
from __future__ import annotations

import ast
import math
import random
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Callable, Iterable

from .ontology import Ontology
from .store import FactStore

DIM_KEYS = ("team", "project", "repo", "sprint", "env", "worktype", "author", "severity", "status")


class MetricError(RuntimeError):
    pass


# ---------------------------------------------------------------- 时间工具
def parse_dt(value: str) -> datetime:
    value = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        dt = datetime.strptime(value[:19], "%Y-%m-%d %H:%M:%S")
    return dt.replace(tzinfo=None)


def bucket_key(dt: datetime, granularity: str) -> str:
    if granularity == "day":
        return dt.strftime("%Y-%m-%d")
    if granularity == "month":
        return dt.strftime("%Y-%m")
    iso = dt.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def bucket_start(key: str) -> date:
    if "-W" in key:
        year, week = key.split("-W")
        return date.fromisocalendar(int(year), int(week), 1)
    if len(key) == 7:
        return date.fromisoformat(key + "-01")
    return date.fromisoformat(key)


def window_bounds(granularity: str, periods: int, end: date | None = None) -> tuple[str, str]:
    """返回 [start, end) 的日期字符串，覆盖最近 periods 个桶。"""
    end = end or date.today()
    if granularity == "month":
        start = date(end.year - (periods - 1) // 12, ((end.month - 1 - (periods - 1)) % 12) + 1, 1)
        stop = date(end.year + (end.month // 12), (end.month % 12) + 1, 1)
    elif granularity == "day":
        start, stop = end - timedelta(days=periods), end + timedelta(days=1)
    else:
        start = end - timedelta(weeks=periods)
        stop = end + timedelta(days=1)
    return start.isoformat(), stop.isoformat()


# ---------------------------------------------------------------- 表达式
_ALLOWED_NODES = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Name, ast.Load,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.USub, ast.UAdd, ast.Call, ast.Pow,
)
_ALLOWED_FUNCS: dict[str, Callable[..., float]] = {
    "min": min, "max": max, "abs": abs, "round": round, "sqrt": math.sqrt,
}


def safe_eval(expr: str, names: dict[str, float | None]) -> float | None:
    """受限表达式求值：只允许四则运算、幂与白名单函数。"""
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:  # pragma: no cover
        raise MetricError(f"表达式语法错误：{expr}") from exc
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise MetricError(f"表达式包含不允许的语法：{type(node).__name__}")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _ALLOWED_FUNCS:
                raise MetricError("表达式调用了未授权的函数")
        if isinstance(node, ast.Name) and node.id not in names and node.id not in _ALLOWED_FUNCS:
            raise MetricError(f"表达式引用了未知变量：{node.id}")
    env = {**_ALLOWED_FUNCS, **{k: v for k, v in names.items() if v is not None}}
    if any(v is None for v in names.values()):
        return None
    try:
        value = eval(compile(tree, "<metric>", "eval"), {"__builtins__": {}}, env)  # noqa: S307
    except ZeroDivisionError:
        return None
    return float(value) if isinstance(value, (int, float)) else None


# ---------------------------------------------------------------- 索引
@dataclass
class FactIndex:
    facts: list[dict[str, Any]]
    entities: dict[str, dict[str, Any]]
    ancestors: dict[str, list[str]]
    in_sprint: dict[str, str]

    def entity_chain(self, entity_id: str) -> list[str]:
        return self.ancestors.get(entity_id, [entity_id])

    def dim_of_chain(self, entity_id: str, class_id: str) -> str | None:
        for node in self.entity_chain(entity_id):
            ent = self.entities.get(node)
            if ent and ent["class_id"] == class_id:
                return ent["label"]
        return None


def build_index(store: FactStore, onto: Ontology) -> FactIndex:
    entities = {e["id"]: e for e in store.entities()}
    ancestors: dict[str, list[str]] = {}
    for eid in entities:
        chain, cur, guard = [], eid, 0
        while cur and guard < 32:
            chain.append(cur)
            cur = entities.get(cur, {}).get("parent_id")
            guard += 1
        ancestors[eid] = chain
    in_sprint = {src: dst for rel, src, dst in store.relation_triples("inSprint")}
    facts = store.facts()
    for fact in facts:
        fact["dims"] = resolve_dims(fact, entities, ancestors, in_sprint, onto)
        fact["dt"] = parse_dt(fact["occurred_at"])
    return FactIndex(facts=facts, entities=entities, ancestors=ancestors, in_sprint=in_sprint)


def resolve_dims(fact: dict[str, Any], entities: dict[str, dict[str, Any]],
                 ancestors: dict[str, list[str]], in_sprint: dict[str, str],
                 onto: Ontology) -> dict[str, Any]:
    """把事实映射到分析维度，全部通过本体关系/类归属推理。"""
    dims: dict[str, Any] = {}
    fields = fact["fields"]
    subject = fact["subject_id"]

    def chain_dim(entity_id: str, class_id: str) -> str | None:
        for node in ancestors.get(entity_id, [entity_id]):
            ent = entities.get(node)
            if ent and ent["class_id"] == class_id:
                return ent["label"]
        return None

    repo_id = fields.get("repo")
    if not repo_id and entities.get(subject, {}).get("class_id") == "dev:Repository":
        repo_id = subject
    if repo_id:
        dims["repo"] = entities.get(repo_id, {}).get("label", repo_id)
        dims["project"] = chain_dim(repo_id, "dev:Project")
        dims["team"] = chain_dim(repo_id, "dev:Team")

    if fact["fact_type"].startswith("workitem."):
        dims["project"] = dims.get("project") or chain_dim(subject, "dev:Project")
        dims["team"] = dims.get("team") or chain_dim(subject, "dev:Team")
        sprint_id = in_sprint.get(subject)
        if sprint_id:
            dims["sprint"] = entities.get(sprint_id, {}).get("label", sprint_id)
            dims["team"] = dims.get("team") or chain_dim(sprint_id, "dev:Team")
            dims["project"] = dims.get("project") or chain_dim(sprint_id, "dev:Project")

    if fact["fact_type"] == "sprint.completed":
        dims["sprint"] = entities.get(subject, {}).get("label", subject)
        dims["team"] = dims.get("team") or chain_dim(subject, "dev:Team")
        dims["project"] = dims.get("project") or chain_dim(subject, "dev:Project")

    if fact["fact_type"] == "review.submitted" and fields.get("pr"):
        dims["repo"] = dims.get("repo") or entities.get(fields["pr"], {}).get("attrs", {}).get("repo_label")

    for key in ("env", "author", "severity", "status", "priority", "verdict"):
        if fields.get(key) is not None:
            dims[key] = fields[key]

    worktype = onto.worktype_of(fact["subject_class"])
    if worktype:
        dims["worktype"] = worktype
    return {k: v for k, v in dims.items() if v is not None}


# ---------------------------------------------------------------- 过滤器
def match_filter(flt: dict[str, Any] | None, fact: dict[str, Any], onto: Ontology) -> bool:
    if not flt:
        return True
    if "all" in flt:
        return all(match_filter(f, fact, onto) for f in flt["all"])
    if "any" in flt:
        return any(match_filter(f, fact, onto) for f in flt["any"])
    if "class" in flt:
        return onto.is_subclass(fact["subject_class"], flt["class"])
    field, op, value = flt.get("field"), flt.get("op", "eq"), flt.get("value")
    actual = fact["fields"].get(field, fact["dims"].get(field))
    if op == "eq":
        return actual == value
    if op == "ne":
        return actual != value
    if op == "in":
        return actual in (value or [])
    if op == "gt":
        return actual is not None and actual > value
    if op == "lt":
        return actual is not None and actual < value
    if op == "exists":
        return actual is not None
    raise MetricError(f"未知过滤操作符：{op}")


# ---------------------------------------------------------------- 聚合
def aggregate(values: list[float], agg: str) -> float | None:
    if agg == "count":
        return float(len(values))
    if not values:
        return None
    if agg == "sum":
        return float(sum(values))
    if agg == "avg":
        return float(sum(values) / len(values))
    if agg == "median":
        return float(statistics.median(values))
    if agg == "min":
        return float(min(values))
    if agg == "max":
        return float(max(values))
    if agg == "p90":
        ordered = sorted(values)
        idx = max(0, min(len(ordered) - 1, math.ceil(0.9 * len(ordered)) - 1))
        return float(ordered[idx])
    raise MetricError(f"未知聚合方式：{agg}")


class MetricsEngine:
    def __init__(self, onto: Ontology, store: FactStore):
        self.onto = onto
        self.store = store

    # ---------- 公共入口 ----------
    def index(self) -> FactIndex:
        return build_index(self.store, self.onto)

    def compute(self, metric_ids: Iterable[str] | None = None, start: str | None = None,
                end: str | None = None, granularity: str = "week",
                filters: dict[str, Any] | None = None, periods: int = 12) -> dict[str, Any]:
        index = self.index()
        start, end = self._bounds(index, start, end, granularity, periods)
        scoped = self._scope(index, start, end, filters)
        # 配对指标需要回看窗口之前的起点事实（工单可能在窗口前创建、窗口内关闭）
        history = self._scope(index, None, end, filters)
        values = self._window_values(scoped, start, end, granularity, history)
        prev_start = self._shift(start, end)
        prev = self._window_values(self._scope(index, prev_start, start, filters),
                                   prev_start, start, granularity,
                                   self._scope(index, None, start, filters))
        wanted = list(metric_ids) if metric_ids else self.onto.metric_ids()
        return {
            "window": {"start": start, "end": end, "granularity": granularity,
                       "previousStart": prev_start},
            "metrics": {mid: self._present(mid, values[mid],
                                           prev.get(mid, {}).get("total"))
                        for mid in wanted if mid in values},
            "coverage": {
                "facts": len(scoped),
                "totalFacts": len(index.facts),
                "dimensions": {k: sorted({f["dims"].get(k) for f in scoped if f["dims"].get(k)})[:20]
                               for k in DIM_KEYS},
            },
        }

    # ---------- 内部 ----------
    def _bounds(self, index: FactIndex, start: str | None, end: str | None,
                granularity: str, periods: int) -> tuple[str, str]:
        if start and end:
            return start, end
        if index.facts:
            latest = max(f["dt"] for f in index.facts).date()
        else:
            latest = date.today()
        default_start, default_end = window_bounds(granularity, periods, latest)
        return start or default_start, end or default_end

    def _scope(self, index: FactIndex, start: str | None, end: str | None,
               filters: dict[str, Any] | None) -> list[dict[str, Any]]:
        out = []
        for fact in index.facts:
            if start and fact["occurred_at"] < start:
                continue
            if end and fact["occurred_at"] >= end:
                continue
            if filters and not self._match_dims(filters, fact):
                continue
            out.append(fact)
        return out

    @staticmethod
    def _match_dims(filters: dict[str, Any], fact: dict[str, Any]) -> bool:
        for key, expected in filters.items():
            if expected in (None, "", "all", []):
                continue
            actual = fact["dims"].get(key)
            if isinstance(expected, list):
                if actual not in expected:
                    return False
            elif actual != expected:
                return False
        return True

    @staticmethod
    def _shift(start: str, end: str) -> str:
        """上一个等长窗口的起点。"""
        span = (date.fromisoformat(end) - date.fromisoformat(start)).days
        return (date.fromisoformat(start) - timedelta(days=span)).isoformat()

    def _window_values(self, facts: list[dict[str, Any]], start: str, end: str,
                       granularity: str,
                       history: list[dict[str, Any]] | None = None) -> dict[str, dict[str, Any]]:
        grid = _bucket_grid(start, end, granularity)
        atomic = self._atomic_values(facts, start, end, granularity, grid,
                                     history if history is not None else facts)
        return self._resolve_all(atomic, facts, grid, granularity)

    def _atomic_values(self, facts: list[dict[str, Any]], start: str, end: str,
                       granularity: str, grid: list[str],
                       history: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """返回 {metric_id: {"total": v, "series": {bucket: v}, "samples": [...]}}"""
        by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for fact in facts:
            by_type[fact["fact_type"]].append(fact)
        span_weeks = max((date.fromisoformat(end) - date.fromisoformat(start)).days / 7, 1e-9)

        out: dict[str, dict[str, Any]] = {}
        for metric in self.onto.metrics:
            if metric.get("type") == "pair":
                out[metric["id"]] = self._pair_values(metric, facts, granularity, grid, history)
                continue
            if metric.get("type") != "atomic":
                continue
            rows = [f for f in by_type.get(metric["fact"], [])
                    if match_filter(metric.get("filter"), f, self.onto)]
            agg = metric["agg"]
            measure = metric.get("measure")
            if agg == "distinct":
                # 去重计数需要按时间桶分别去重，不能先拍平再聚合
                per_bucket: dict[str, set] = defaultdict(set)
                for f in rows:
                    key = f["fields"].get(measure) or f["dims"].get(measure)
                    if key is not None:
                        per_bucket[bucket_key(f["dt"], granularity)].add(key)
                seen_all = set().union(*per_bucket.values()) if per_bucket else set()
                per_week = (metric.get("normalize") or {}).get("per") == "week"
                bucket_weeks = {"week": 1.0, "month": 4.345, "day": 1 / 7}[granularity]
                total = float(len(seen_all))
                series_out: dict[str, float | None] = {k: None for k in grid}
                for key, members in per_bucket.items():
                    series_out[key] = float(len(members)) / bucket_weeks if per_week else float(len(members))
                if per_week:
                    total = total / span_weeks
                out[metric["id"]] = {
                    "total": total,
                    "series": _forward_fill(series_out, grid, limit=2),
                    "samples": [1.0] * len(seen_all),
                    "count": len(seen_all),
                }
                continue
            if agg == "count":
                samples = [1.0] * len(rows)
            else:
                samples = []
                kept = []
                for f in rows:
                    val = f["measures"].get(measure)
                    if val is None and measure:
                        val = f["fields"].get(measure)
                    if isinstance(val, (int, float)):
                        samples.append(float(val))
                        kept.append(f)
                rows = kept

            series: dict[str, list[float]] = defaultdict(list)
            for fact, val in zip(rows, samples):
                series[bucket_key(fact["dt"], granularity)].append(val)
            per_week = (metric.get("normalize") or {}).get("per") == "week"
            bucket_weeks = {"week": 1.0, "month": 4.345, "day": 1 / 7}[granularity]
            total = aggregate(samples, "count" if agg == "distinct" else agg)
            series_out: dict[str, float | None] = {k: None for k in grid}
            for key, vals in series.items():
                series_out[key] = aggregate(vals, "count" if agg == "distinct" else agg)
            if per_week:
                if total is not None:
                    total = total / span_weeks
                series_out = {k: (v / bucket_weeks if v is not None else None)
                              for k, v in series_out.items()}
            # 稀疏事实（如双周迭代）在无数据桶上沿用上一期速率，避免曲线断裂
            series_out = _forward_fill(series_out, grid, limit=2)
            out[metric["id"]] = {
                "total": total,
                "series": series_out,
                "samples": samples,
                "count": len(rows),
            }
        return out

    def _pair_values(self, metric: dict[str, Any], facts: list[dict[str, Any]],
                     granularity: str, grid: list[str],
                     history: list[dict[str, Any]]) -> dict[str, Any]:
        """成对事实指标：按 joinOn 键把起点事实与终点事实配对，计算时长。

        这正是本体驱动的价值：workitem.created 与 workitem.closed 是两类事实，
        通过『同一主体』这一本体关系连接后才可计算周期。
        """
        starts = {f["subject_id"]: f for f in history if f["fact_type"] == metric["startFact"]}
        ends = [f for f in facts if f["fact_type"] == metric["endFact"]]
        samples, series = [], defaultdict(list)
        for end in ends:
            start = starts.get(end["subject_id"])
            if not start:
                continue
            hours = (end["dt"] - start["dt"]).total_seconds() / 3600
            if hours < 0:
                continue
            samples.append(hours)
            series[bucket_key(end["dt"], granularity)].append(hours)
        agg = metric.get("agg", "median")
        grid_series: dict[str, float | None] = {k: None for k in grid}
        for key, vals in series.items():
            grid_series[key] = aggregate(vals, agg)
        return {
            "total": aggregate(samples, agg),
            "series": _forward_fill(grid_series, grid, limit=2),
            "samples": samples,
            "count": len(samples),
        }

    def _resolve_all(self, atomic: dict[str, dict[str, Any]], facts: list[dict[str, Any]],
                     grid: list[str], granularity: str) -> dict[str, dict[str, Any]]:
        values: dict[str, dict[str, Any]] = dict(atomic)
        pending = [m for m in self.onto.metrics if m.get("type") not in {"atomic", "pair"}]
        order = self._topo_order(pending)
        buckets = grid
        for metric in order:
            mid = metric["id"]
            deps = metric.get("deps", [])
            total = self._eval_metric(metric, {d: values[d]["total"] for d in deps if d in values})
            series = {}
            for bucket in buckets:
                series[bucket] = self._eval_metric(
                    metric, {d: values[d]["series"].get(bucket) for d in deps if d in values})
            values[mid] = {"total": total, "series": series, "samples": [], "count": None}
        return values

    def _topo_order(self, metrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_id = {m["id"]: m for m in metrics}
        done: set[str] = set()
        ordered: list[dict[str, Any]] = []

        def visit(mid: str) -> None:
            if mid in done:
                return
            metric = by_id.get(mid)
            if not metric:
                return
            for dep in metric.get("deps", []):
                visit(dep)
            done.add(mid)
            ordered.append(metric)

        for mid in by_id:
            visit(mid)
        return ordered

    def _eval_metric(self, metric: dict[str, Any], deps: dict[str, float | None]) -> float | None:
        mtype = metric.get("type")
        if mtype == "derived":
            return safe_eval(metric["expr"], deps)
        if mtype == "composite":
            components = metric.get("scoring", {}).get("components", [])
            if not components:
                return None
            total_weight = sum(c["weight"] for c in components)
            score = 0.0
            for comp in components:
                value = deps.get(comp["dep"])
                if value is None:
                    return None
                score += comp["weight"] * _normalize(value, comp["goal"], comp.get("scale", "higher_better"))
            return score / total_weight * 100 if total_weight else None
        return deps.get(metric["id"])

    def _present(self, metric_id: str, raw: dict[str, Any],
                 prev_total: float | None = None) -> dict[str, Any]:
        metric = self.onto.metric(metric_id) or {}
        precision = metric.get("precision", 2)
        direction = metric.get("direction", "up")
        target = metric.get("target")
        value = raw.get("total")
        series = [
            {"bucket": b, "value": _round(v, precision)}
            for b, v in sorted(raw.get("series", {}).items())
        ]
        delta = None
        if value is not None and prev_total not in (None, 0):
            delta = (value - prev_total) / abs(prev_total) * 100
        return {
            "id": metric_id,
            "label": metric.get("label", metric_id),
            "unit": metric.get("unit", ""),
            "type": metric.get("type"),
            "layer": metric.get("layer"),
            "description": metric.get("description", ""),
            "formula": metric.get("formula", ""),
            "owner": metric.get("owner", ""),
            "direction": direction,
            "target": target,
            "precision": precision,
            "indicator": bool(metric.get("indicator")),
            "hidden": bool(metric.get("hidden")),
            "primary": bool(metric.get("primary")),
            "value": _round(value, precision),
            "previous": _round(prev_total, precision),
            "delta": _round(delta, 1),
            "status": _status(value, target, direction),
            "attainment": _round(_attainment(value, target, direction), 3),
            "series": series,
            "samples": len(raw.get("samples") or []),
        }

    # ---------- 分析能力 ----------
    def trend(self, metric_id: str, granularity: str = "week", periods: int = 12,
              filters: dict[str, Any] | None = None) -> dict[str, Any]:
        result = self.compute([metric_id], granularity=granularity, periods=periods, filters=filters)
        metric = result["metrics"].get(metric_id, {})
        return {
            "metric": metric_id,
            "label": metric.get("label"),
            "unit": metric.get("unit"),
            "target": metric.get("target"),
            "series": metric.get("series", []),
            "window": result["window"],
        }

    def breakdown(self, metric_id: str, dimension: str = "team", granularity: str = "week",
                  periods: int = 12) -> dict[str, Any]:
        index = self.index()
        start, end = self._bounds(index, None, None, granularity, periods)
        members = sorted({f["dims"].get(dimension) for f in index.facts
                          if f["dims"].get(dimension) and start <= f["occurred_at"] < end})
        items = []
        for member in members:
            result = self.compute([metric_id], start=start, end=end, granularity=granularity,
                                  filters={dimension: member})
            metric = result["metrics"].get(metric_id, {})
            items.append({
                "member": member,
                "value": metric.get("value"),
                "status": metric.get("status"),
                "series": metric.get("series", []),
            })
        items.sort(key=lambda x: (x["value"] is None, -(x["value"] or 0)))
        return {"metric": metric_id, "dimension": dimension, "window": {"start": start, "end": end},
                "items": items}

    def lineage(self, metric_id: str | None = None) -> dict[str, Any]:
        nodes, edges = [], set()
        root = metric_id or next((m["id"] for m in self.onto.metrics if m.get("indicator")), None)
        keep = set()
        if root:
            keep.add(root)
            keep.update(self.onto.dependency_closure(root))
        for metric in self.onto.metrics:
            mid = metric["id"]
            if keep and mid not in keep:
                continue
            nodes.append({
                "id": mid, "label": metric["label"], "type": metric.get("type"),
                "layer": metric.get("layer"), "unit": metric.get("unit"),
                "indicator": bool(metric.get("indicator")),
                "deps": [d for d in metric.get("deps", []) if not keep or d in keep],
            })
            for dep in metric.get("deps", []):
                if not keep or dep in keep:
                    edges.add((dep, mid))
        return {"root": root, "nodes": nodes,
                "edges": [{"from": a, "to": b} for a, b in sorted(edges)]}

    def insights(self, granularity: str = "week", periods: int = 12) -> list[dict[str, Any]]:
        result = self.compute(granularity=granularity, periods=periods)
        out: list[dict[str, Any]] = []
        for mid, m in result["metrics"].items():
            if not m.get("primary") and not m.get("indicator"):
                continue
            if m["value"] is None:
                out.append({"level": "info", "metric": mid, "title": f"{m['label']} 暂无数据",
                            "detail": "当前窗口内没有可聚合的事实，请检查数据接入或扩大时间范围。"})
                continue
            if m["status"] == "off":
                out.append({
                    "level": "critical" if m["attainment"] is not None and m["attainment"] < 0.6 else "warning",
                    "metric": mid,
                    "title": f"{m['label']} 未达标",
                    "detail": f"当前 {m['value']}{m['unit']}，目标 {m['target']}{m['unit']}，"
                              f"达成率 {round((m['attainment'] or 0) * 100)}%，负责人 {m['owner']}。",
                })
            if m["delta"] is not None and abs(m["delta"]) >= 10:
                worse = (m["delta"] > 0) != (m["direction"] == "up")
                trend = "上升" if m["delta"] > 0 else "下降"
                if worse:
                    out.append({"level": "warning", "metric": mid,
                                "title": f"{m['label']} 环比{trend} {abs(m['delta'])}%，方向不利",
                                "detail": f"上一周期为 {m['previous']}{m['unit']}，当前 {m['value']}{m['unit']}。"
                                          f"该指标越低越好，建议下钻到团队维度定位原因。" if m["direction"] == "down"
                                          else f"上一周期为 {m['previous']}{m['unit']}，当前 {m['value']}{m['unit']}。"
                                               f"该指标越高越好，建议下钻到团队维度定位原因。"})
        order = {"critical": 0, "warning": 1, "info": 2}
        out.sort(key=lambda x: order.get(x["level"], 3))
        return out[:12]

    def forecast(self, metric_id: str = "delivered_items", periods: int = 12,
                 remaining: float | None = None, simulations: int = 2000,
                 seed: int = 42) -> dict[str, Any]:
        """基于历史周期吞吐的蒙特卡洛交付预测。"""
        result = self.compute([metric_id], granularity="week", periods=periods)
        series = [p["value"] for p in result["metrics"].get(metric_id, {}).get("series", [])
                  if p["value"] is not None]
        if len(series) < 3:
            raise MetricError("历史数据不足，至少需要 3 个周期")
        backlog = remaining if remaining is not None else sum(series) / len(series) * 4
        rng = random.Random(seed)
        weeks = []
        for _ in range(simulations):
            delivered, week = 0.0, 0
            while delivered < backlog and week < 520:
                delivered += rng.choice(series)
                week += 1
            weeks.append(week)
        weeks.sort()
        pct = lambda p: weeks[min(len(weeks) - 1, int(p * len(weeks)))]  # noqa: E731
        return {
            "metric": metric_id, "backlog": round(backlog, 1), "samples": len(series),
            "mean": round(sum(series) / len(series), 2),
            "p50": pct(0.50), "p85": pct(0.85), "p95": pct(0.95),
            "histogram": _histogram(weeks),
            "assumption": "以历史周吞吐为独立同分布样本，未建模需求新增与人员变动。",
        }

    def quality(self) -> dict[str, Any]:
        index = self.index()
        facts = index.facts
        issues: list[dict[str, Any]] = []
        by_subject: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for fact in facts:
            by_subject[fact["subject_id"]].append(fact)

        for fact in facts:
            ftype = self.onto.fact_type(fact["fact_type"])
            if ftype is None:
                issues.append({"severity": "high", "type": "未知事实类型",
                               "subject": fact["subject_id"], "detail": fact["fact_type"]})
                continue
            if not self.onto.is_subclass(fact["subject_class"], ftype.subject):
                issues.append({"severity": "high", "type": "主体类与事实类型不匹配",
                               "subject": fact["subject_id"],
                               "detail": f"{fact['subject_class']} 不是 {ftype.subject} 的子类"})
            if (self.onto.is_subclass(fact["subject_class"], "core:Artifact")
                    and fact["subject_id"] not in index.entities):
                issues.append({"severity": "medium", "type": "主体未注册",
                               "subject": fact["subject_id"], "detail": "实体表中不存在该主体"})
            for measure in ftype.measures:
                val = fact["measures"].get(measure)
                if val is None:
                    issues.append({"severity": "low", "type": "度量缺失",
                                   "subject": fact["subject_id"], "detail": f"缺少度量 {measure}"})
                elif isinstance(val, (int, float)) and val < 0:
                    issues.append({"severity": "high", "type": "度量取值为负",
                                   "subject": fact["subject_id"], "detail": f"{measure}={val}"})
            if not fact["dims"].get("team"):
                issues.append({"severity": "medium", "type": "维度缺失",
                               "subject": fact["subject_id"], "detail": "无法推理出所属团队"})

        for subject, group in by_subject.items():
            created = [f for f in group if f["fact_type"] == "workitem.created"]
            closed = [f for f in group if f["fact_type"] == "workitem.closed"]
            if created and closed and min(f["occurred_at"] for f in closed) < min(f["occurred_at"] for f in created):
                issues.append({"severity": "high", "type": "时序倒置", "subject": subject,
                               "detail": "关闭时间早于创建时间"})

        total_checks = max(len(facts) * 3, 1)
        penalty = sum({"high": 3, "medium": 2, "low": 1}[i["severity"]] for i in issues)
        score = max(0.0, 100 - penalty / total_checks * 100)
        by_type: dict[str, int] = defaultdict(int)
        for issue in issues:
            by_type[issue["type"]] += 1
        return {
            "score": round(score, 1),
            "facts": len(facts),
            "issueCount": len(issues),
            "byType": dict(by_type),
            "issues": issues[:200],
            "checkedAt": datetime.now().isoformat(timespec="seconds"),
        }


def _normalize(value: float, goal: float, scale: str) -> float:
    if goal <= 0:
        return 0.0
    if scale == "lower_better":
        if value <= 0:
            return 1.0
        return max(0.0, min(1.0, goal / value))
    return max(0.0, min(1.0, value / goal))


def _status(value: float | None, target: float | None, direction: str) -> str:
    if value is None:
        return "no_data"
    if target is None:
        return "unknown"
    if direction == "down":
        return "ok" if value <= target else "off"
    return "ok" if value >= target else "off"


def _attainment(value: float | None, target: float | None, direction: str) -> float | None:
    if value is None or target in (None, 0):
        return None
    if direction == "down":
        return min(1.5, target / value) if value > 0 else 1.5
    return min(1.5, value / target)


def _round(value: float | None, precision: int) -> float | None:
    if value is None:
        return None
    return round(float(value), precision)


def _bucket_grid(start: str, end: str, granularity: str) -> list[str]:
    """窗口内完整时间桶序列，保证曲线连续且可对齐。"""
    grid: list[str] = []
    cur = bucket_start(bucket_key(parse_dt(start), granularity))
    stop = date.fromisoformat(end)
    step = {"day": timedelta(days=1), "week": timedelta(weeks=1), "month": timedelta(days=28)}[granularity]
    guard = 0
    while cur < stop and guard < 2000:
        grid.append(bucket_key(datetime(cur.year, cur.month, cur.day), granularity))
        cur = cur + step
        guard += 1
    return list(dict.fromkeys(grid))


def _forward_fill(series: dict[str, float | None], grid: list[str],
                  limit: int = 2) -> dict[str, float | None]:
    out = dict(series)
    last, gap = None, 0
    for key in grid:
        if out.get(key) is None:
            gap += 1
            if last is not None and gap <= limit:
                out[key] = last
        else:
            last, gap = out[key], 0
    return out


def _histogram(values: list[int], bins: int = 12) -> list[dict[str, Any]]:
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi == lo:
        return [{"from": lo, "to": hi, "count": len(values)}]
    width = max(1, math.ceil((hi - lo + 1) / bins))
    out = []
    edge = lo
    while edge <= hi:
        upper = edge + width - 1
        out.append({"from": edge, "to": upper,
                    "count": sum(1 for v in values if edge <= v <= upper)})
        edge = upper + 1
    return out
