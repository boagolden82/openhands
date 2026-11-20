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
    assert onto.version == "2.0.0"
    assert len(onto.classes) >= 25
    assert len(onto.relations) >= 12
    assert len(onto.fact_types) >= 10
    assert len(onto.metrics) >= 40


def test_every_metric_has_unique_id(onto):
    ids = [m["id"] for m in onto.metrics]
    assert len(ids) == len(set(ids))


def test_all_metrics_carry_label_and_unit(onto):
    for metric in onto.metrics:
        assert metric.get("label"), metric["id"]
        assert metric.get("unit"), metric["id"]
        assert metric.get("description"), metric["id"]


def test_visible_metrics_carry_direction_and_target(onto):
    """内部口径指标只做分母，不参与考核，因此允许没有方向与目标。"""
    for metric in onto.metrics:
        if metric.get("hidden"):
            continue
        assert metric.get("direction") in {"up", "down"}, metric["id"]
        assert metric.get("target") is not None, metric["id"]


def test_metric_codes_match_the_published_numbering(onto):
    """指标编号必须与需求清单一致，便于与业务方对账。"""
    expected = {
        "mr_impl_cycle": "2.0.1 / 2.5",
        "rr_on_time_rate": "2.0.2",
        "mr_delivery_per_capita": "2.1",
        "mr_impl_per_capita": "2.2",
        "mr_impl_per_capita_live": "2.3",
        "mr_impl_per_capita_converted": "2.4",
        "mr_analysis_throughput": "2.7",
        "mr_analysis_cycle": "2.8",
        "mr_dev_throughput": "2.9",
        "mr_dev_cycle": "2.10",
        "mr_test_throughput": "2.11",
        "mr_accept_cycle": "2.12",
        "analysis_gen_rate": "3.1",
        "solution_gen_rate": "3.2",
        "code_gen_rate": "3.3",
        "ai_testcase_gen_rate": "3.4",
        "ai_script_gen_rate": "3.5",
        "mr_ai_penetration": "3.6",
    }
    for mid, code in expected.items():
        metric = onto.metric(mid)
        assert metric is not None, mid
        assert metric["code"] == code, mid


def test_duplicate_impl_cycle_code_covers_both_entries(onto):
    """需求清单中 2.0.1 与 2.5 都是 MR实现周期，一个指标覆盖两个编号。"""
    metric = onto.metric("mr_impl_cycle")
    assert "2.0.1" in metric["code"] and "2.5" in metric["code"]


def test_subsumption_is_transitive(onto):
    # MR ⊑ Artifact ⊑ Entity
    assert onto.is_subclass("dev:MR", "core:Artifact")
    assert onto.is_subclass("dev:MR", "core:Entity")
    # 分析阶段 ⊑ 阶段 ⊑ 事件
    assert onto.is_subclass("dev:AnalysisPhase", "dev:Phase")
    assert onto.is_subclass("dev:AnalysisPhase", "core:Event")
    # 中心人力 ⊑ 人员 ⊑ 参与者
    assert onto.is_subclass("dev:Employee", "dev:Person")
    assert onto.is_subclass("dev:Employee", "core:Actor")
    # 反方向不成立
    assert not onto.is_subclass("core:Artifact", "dev:MR")


def test_ancestors_and_descendants(onto):
    assert onto.ancestors("dev:MR")[0] == "dev:MR"
    assert onto.ancestors("dev:MR")[-1] == "core:Entity"
    assert "dev:MR" in onto.descendants("core:Artifact")
    assert "dev:TestPhase" in onto.descendants("dev:Phase")


def test_relation_inverse_pairs_are_symmetric(onto):
    for rel in onto.relations.values():
        if rel.inverse:
            assert rel.inverse in onto.relations, rel.id
            assert onto.relations[rel.inverse].inverse == rel.id


def test_transitive_closure_only_for_transitive_relations(onto):
    edges = [("a", "b"), ("b", "c")]
    closure = onto.transitive_closure("belongsTo", edges)
    assert closure["a"] == {"b", "c"}
    # staffedBy 非传递，只保留一跳
    one_hop = onto.transitive_closure("staffedBy", edges)
    assert one_hop["a"] == {"b"}


def test_fact_type_phase_is_declared_for_stage_events(onto):
    phases = {f.id: f.phase for f in onto.fact_types.values()}
    assert phases["mr.analysis.done"] == "分析"
    assert phases["mr.dev.done"] == "开发"
    assert phases["mr.test.done"] == "测试"
    assert phases["mr.accepted"] == "验收"
    assert phases["mr.created"] is None


def test_atomic_metrics_reference_existing_facts_and_measures(onto):
    for metric in onto.metrics:
        if metric.get("type") != "atomic":
            continue
        fact = onto.fact_types[metric["fact"]]
        measure = metric.get("measure")
        if measure and metric.get("agg") != "count":
            assert measure in fact.measures, f"{metric['id']} 的度量 {measure} 未在事实中声明"


def test_pair_metrics_reference_existing_fact_types(onto):
    for metric in onto.metrics:
        if metric.get("type") != "pair":
            continue
        assert metric["startFact"] in onto.fact_types, metric["id"]
        assert metric["endFact"] in onto.fact_types, metric["id"]


def test_derived_metrics_expression_variables_match_deps(onto):
    import re
    for metric in onto.metrics:
        if metric.get("type") != "derived":
            continue
        variables = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", metric["expr"]))
        variables -= {"max", "min", "months", "abs", "round", "sqrt"}
        assert variables == set(metric["deps"]), metric["id"]


def test_dependency_closure_is_ordered(onto):
    closure = onto.dependency_closure("rde_index")
    assert "mr_impl_cycle" in closure
    assert "code_gen_rate" in closure
    assert "rde_index" not in closure


def test_cycle_detection_rejects_self_dependency(tmp_path, onto):
    raw = json.loads((onto_path := __import__("app.config", fromlist=["x"]).ontology_path())
                     .read_text(encoding="utf-8"))
    raw["metrics"].append({
        "id": "loop_metric", "label": "环", "unit": "个", "type": "derived",
        "expr": "loop_metric", "deps": ["loop_metric"], "direction": "up",
    })
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(OntologyError):
        Ontology.load(path)


def test_unknown_dependency_is_rejected(tmp_path, onto):
    from app.config import ontology_path
    raw = json.loads(ontology_path().read_text(encoding="utf-8"))
    raw["metrics"].append({
        "id": "orphan", "label": "孤儿", "unit": "个", "type": "derived",
        "expr": "nope", "deps": ["nope"], "direction": "up",
    })
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(OntologyError):
        Ontology.load(path)


def test_to_dict_exposes_stats(onto):
    data = onto.to_dict()
    assert data["stats"]["classes"] == len(onto.classes)
    assert data["stats"]["metrics"] == len(onto.metrics)
    assert data["stats"]["atomicMetrics"] >= 20
    assert data["dimensions"]
