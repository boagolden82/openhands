"""本体加载、推理与校验。

推理能力：
* 子类闭包（subsumption）：判断某实体所属类是否 ⊑ 目标类；
* 传递关系闭包：belongsTo/hasMember/dependsOn 等传递关系的可达集合；
* 维度上卷：组织 -> 团队、项目 -> 代码库；
* 类到工作类型的映射（用于按本体推理出 worktype 维度）。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


class OntologyError(ValueError):
    """本体定义不合法。"""


@dataclass(frozen=True)
class OntoClass:
    id: str
    label: str
    parent: str | None
    namespace: str
    description: str = ""

    @property
    def depth(self) -> int:
        return self.id.count(":")


@dataclass(frozen=True)
class Relation:
    id: str
    label: str
    domain: str
    range: str
    transitive: bool = False
    inverse: str | None = None


@dataclass(frozen=True)
class FactType:
    id: str
    label: str
    subject: str
    time_field: str
    measures: tuple[str, ...] = ()
    fields: tuple[str, ...] = ()
    description: str = ""
    phase: str | None = None


@dataclass
class Ontology:
    version: str
    name: str
    description: str
    namespaces: dict[str, str]
    dimensions: list[dict[str, str]]
    classes: dict[str, OntoClass]
    relations: dict[str, Relation]
    fact_types: dict[str, FactType]
    metrics: list[dict[str, Any]]
    _children: dict[str, set[str]] = field(default_factory=dict, repr=False)

    # ---------- 加载与校验 ----------
    @classmethod
    def load(cls, path: str | Path) -> "Ontology":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        onto = cls(
            version=raw.get("version", "0"),
            name=raw.get("name", "unnamed"),
            description=raw.get("description", ""),
            namespaces=raw.get("namespaces", {}),
            dimensions=raw.get("dimensions", []),
            classes={c["id"]: OntoClass(**c) for c in raw.get("classes", [])},
            relations={r["id"]: Relation(**r) for r in raw.get("relations", [])},
            fact_types={f["id"]: FactType(
                id=f["id"], label=f["label"], subject=f["subject"],
                time_field=f["timeField"], measures=tuple(f.get("measures", [])),
                fields=tuple(f.get("fields", [])), description=f.get("description", ""),
                phase=f.get("phase"),
            ) for f in raw.get("factTypes", [])},
            metrics=raw.get("metrics", []),
        )
        onto.validate()
        return onto

    def validate(self) -> None:
        for cid, c in self.classes.items():
            if c.parent is not None and c.parent not in self.classes:
                raise OntologyError(f"类 {cid} 的父类 {c.parent} 不存在")
        # 环检测
        for cid in self.classes:
            seen, cur = set(), cid
            while cur is not None:
                if cur in seen:
                    raise OntologyError(f"类继承存在环：{cid}")
                seen.add(cur)
                cur = self.classes[cur].parent if cur in self.classes else None
        for fid, f in self.fact_types.items():
            if f.subject not in self.classes:
                raise OntologyError(f"事实类型 {fid} 的主体类 {f.subject} 不存在")
        metric_ids = [m["id"] for m in self.metrics]
        if len(metric_ids) != len(set(metric_ids)):
            raise OntologyError("指标 id 重复")
        known = set(metric_ids)
        for m in self.metrics:
            if m.get("type") == "atomic" and m.get("fact") not in self.fact_types:
                raise OntologyError(f"指标 {m['id']} 引用了未知事实类型 {m.get('fact')}")
            for dep in m.get("deps", []):
                if dep not in known:
                    raise OntologyError(f"指标 {m['id']} 依赖未知指标 {dep}")
            for comp in m.get("scoring", {}).get("components", []):
                if comp["dep"] not in known:
                    raise OntologyError(f"指标 {m['id']} 的评分分量 {comp['dep']} 未定义")
        self._build_children()
        self._check_metric_cycles()

    def _build_children(self) -> None:
        self._children = {cid: set() for cid in self.classes}
        for cid, c in self.classes.items():
            if c.parent:
                self._children[c.parent].add(cid)

    def _check_metric_cycles(self) -> None:
        graph = {m["id"]: list(m.get("deps", [])) for m in self.metrics}
        state: dict[str, int] = {}

        def walk(node: str) -> None:
            if state.get(node) == 1:
                raise OntologyError(f"指标依赖存在环：{node}")
            if state.get(node) == 2:
                return
            state[node] = 1
            for dep in graph.get(node, []):
                walk(dep)
            state[node] = 2

        for node in graph:
            walk(node)

    # ---------- 查询 ----------
    def ancestors(self, class_id: str) -> list[str]:
        chain: list[str] = []
        cur: str | None = class_id
        while cur is not None:
            chain.append(cur)
            cur = self.classes[cur].parent if cur in self.classes else None
        return chain

    def descendants(self, class_id: str) -> set[str]:
        out: set[str] = set()
        stack = [class_id]
        while stack:
            node = stack.pop()
            for child in self._children.get(node, ()):
                if child not in out:
                    out.add(child)
                    stack.append(child)
        return out

    def is_subclass(self, child: str, parent: str) -> bool:
        """child ⊑ parent（含相等），基于父类链推理，不依赖显式声明。"""
        return parent in self.ancestors(child)

    def common_ancestor(self, a: str, b: str) -> str | None:
        chain_b = set(self.ancestors(b))
        for node in self.ancestors(a):
            if node in chain_b:
                return node
        return None

    def class_depth(self, class_id: str) -> int:
        return max(len(self.ancestors(class_id)) - 1, 0)

    def transitive_closure(self, relation_id: str, edges: Iterable[tuple[str, str]]) -> dict[str, set[str]]:
        """对给定边集合按关系的传递性求闭包；非传递关系返回一跳结果。"""
        rel = self.relations.get(relation_id)
        direct: dict[str, set[str]] = {}
        for src, dst in edges:
            direct.setdefault(src, set()).add(dst)
        if rel is None or not rel.transitive:
            return direct
        closure = {k: set(v) for k, v in direct.items()}
        for src in list(closure):
            stack = list(closure[src])
            while stack:
                node = stack.pop()
                for nxt in direct.get(node, ()):
                    if nxt not in closure[src] and nxt != src:
                        closure[src].add(nxt)
                        stack.append(nxt)
        return closure

    def worktype_of(self, class_id: str) -> str | None:
        """按本体类推理工作类型，而不是读取业务字段。"""
        for cid in self.ancestors(class_id):
            label = self.classes[cid].label
            if cid in {"dev:Defect", "dev:TechDebt", "dev:Requirement", "dev:Task", "dev:Story"}:
                return label
        return None

    def fact_type(self, fact_id: str) -> FactType | None:
        return self.fact_types.get(fact_id)

    def metric(self, metric_id: str) -> dict[str, Any] | None:
        for m in self.metrics:
            if m["id"] == metric_id:
                return m
        return None

    def metric_ids(self) -> list[str]:
        return [m["id"] for m in self.metrics]

    def dependency_closure(self, metric_id: str) -> list[str]:
        """指标的传递依赖（不含自身），按依赖优先排序。"""
        ordered: list[str] = []
        seen: set[str] = set()

        def visit(node: str) -> None:
            metric = self.metric(node)
            if not metric:
                return
            for dep in metric.get("deps", []):
                if dep not in seen:
                    seen.add(dep)
                    visit(dep)
                    ordered.append(dep)

        visit(metric_id)
        return ordered

    def dependents(self, metric_id: str) -> list[str]:
        return [m["id"] for m in self.metrics if metric_id in m.get("deps", [])]

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "name": self.name,
            "description": self.description,
            "namespaces": self.namespaces,
            "dimensions": self.dimensions,
            "classes": [vars(c) | {"depth": self.class_depth(c.id)} for c in self.classes.values()],
            "relations": [vars(r) for r in self.relations.values()],
            "factTypes": [
                {
                    "id": f.id, "label": f.label, "subject": f.subject,
                    "timeField": f.time_field, "measures": list(f.measures),
                    "fields": list(f.fields), "description": f.description,
                    "phase": f.phase,
                }
                for f in self.fact_types.values()
            ],
            "metrics": self.metrics,
            "stats": {
                "classes": len(self.classes),
                "relations": len(self.relations),
                "factTypes": len(self.fact_types),
                "metrics": len(self.metrics),
                "atomicMetrics": sum(1 for m in self.metrics if m.get("type") == "atomic"),
                "derivedMetrics": sum(1 for m in self.metrics if m.get("type") == "derived"),
                "compositeMetrics": sum(1 for m in self.metrics if m.get("type") == "composite"),
            },
        }
