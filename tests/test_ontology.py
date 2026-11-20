"""本体加载与推理的单元测试。"""
from __future__ import annotations

import json

import pytest

from app.ontology import Ontology, OntologyError


@pytest.fixture(scope="module")
def onto() -> Ontology:
    from app.config import ontology_path
    return Ontology.load(ontology_path())


def test_ontology_loads_with_expected_shape(onto):
    assert onto.version
    assert len(onto.classes) >= 25
    assert len(onto.relations) >= 15
    assert len(onto.fact_types) >= 10
    assert len(onto.metrics) >= 30


def test_subsumption_is_transitive(onto):
    # Story ⊑ Requirement ⊑ WorkItem ⊑ Artifact ⊑ Entity
    assert onto.is_subclass("dev:Story", "dev:Requirement")
    assert onto.is_subclass("dev:Story", "dev:WorkItem")
    assert onto.is_subclass("dev:Story", "core:Entity")
    # 反方向不成立
    assert not onto.is_subclass("dev:WorkItem", "dev:Story")
    assert onto.is_subclass("dev:WorkItem", "dev:WorkItem")


def test_ancestors_and_descendants(onto):
    assert onto.ancestors("dev:TechDebt")[0] == "dev:TechDebt"
    assert onto.ancestors("dev:TechDebt")[-1] == "core:Entity"
    assert "dev:TechDebt" in onto.descendants("dev:WorkItem")
    assert "dev:Story" in onto.descendants("core:Entity")


def test_common_ancestor(onto):
    assert onto.common_ancestor("dev:Story", "dev:Defect") == "dev:WorkItem"
    assert onto.common_ancestor("dev:Commit", "dev:Deployment") == "core:Event"


def test_class_depth(onto):
    assert onto.class_depth("core:Entity") == 0
    assert onto.class_depth("dev:WorkItem") == 2
    # dev:Story -> dev:Requirement -> dev:WorkItem -> core:Artifact -> core:Entity
    assert onto.class_depth("dev:Story") == 4


def test_transitive_relation_closure(onto):
    edges = [("a", "b"), ("b", "c"), ("c", "d")]
    closure = onto.transitive_closure("belongsTo", edges)
    assert closure["a"] == {"b", "c", "d"}
    assert closure.get("d", set()) == set()


def test_non_transitive_relation_stays_one_hop(onto):
    edges = [("a", "b"), ("b", "c")]
    closure = onto.transitive_closure("ownedBy", edges)
    assert closure["a"] == {"b"}


def test_worktype_inferred_from_class_not_field(onto):
    assert onto.worktype_of("dev:Defect") == "缺陷"
    assert onto.worktype_of("dev:TechDebt") == "技术债"
    assert onto.worktype_of("dev:Story") == "用户故事"
    assert onto.worktype_of("dev:Commit") is None


def test_metric_dependency_closure_is_ordered(onto):
    deps = onto.dependency_closure("dev_eff_index")
    assert "change_failure_rate" in deps
    assert "incident_count" in deps
    # 依赖必须先于使用它的指标出现
    assert deps.index("incident_count") < deps.index("change_failure_rate")


def test_dependents(onto):
    assert "change_failure_rate" in onto.dependents("incident_count")
    assert "dev_eff_index" in onto.dependents("lead_time_hours")


def test_cycle_detection_on_bad_metric_graph(tmp_path):
    raw = json.loads(json.dumps({
        "version": "x", "name": "bad", "namespaces": {}, "dimensions": [],
        "classes": [{"id": "c:A", "label": "A", "parent": None, "namespace": "c"}],
        "relations": [], "factTypes": [],
        "metrics": [
            {"id": "m1", "label": "m1", "type": "derived", "expr": "m2", "deps": ["m2"]},
            {"id": "m2", "label": "m2", "type": "derived", "expr": "m1", "deps": ["m1"]},
        ],
    }))
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(OntologyError, match="环"):
        Ontology.load(path)


def test_missing_parent_class_is_rejected(tmp_path):
    raw = {
        "version": "x", "name": "bad", "namespaces": {}, "dimensions": [],
        "classes": [{"id": "c:A", "label": "A", "parent": "c:Missing", "namespace": "c"}],
        "relations": [], "factTypes": [], "metrics": [],
    }
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(OntologyError):
        Ontology.load(path)


def test_metric_requires_known_fact_type(tmp_path):
    raw = {
        "version": "x", "name": "bad", "namespaces": {}, "dimensions": [],
        "classes": [{"id": "c:A", "label": "A", "parent": None, "namespace": "c"}],
        "relations": [], "factTypes": [],
        "metrics": [{"id": "m", "label": "m", "type": "atomic", "fact": "nope", "agg": "count"}],
    }
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(OntologyError, match="事实类型"):
        Ontology.load(path)


def test_to_dict_exposes_stats(onto):
    data = onto.to_dict()
    assert data["stats"]["classes"] == len(onto.classes)
    assert data["stats"]["atomicMetrics"] > 0
    assert all("depth" in c for c in data["classes"])
