"""指标引擎测试：用人工构造的最小数据集验证新口径的正确性。"""
from __future__ import annotations

import pytest

from app.metrics import MetricsEngine, _attainment, _normalize, _status, safe_eval
from app.ontology import Ontology
from app.store import FactStore


@pytest.fixture()
def onto() -> Ontology:
    from app.config import ontology_path
    return Ontology.load(ontology_path())


def _seed_minimal(store: FactStore) -> None:
    """构造一个可控的小数据集，所有期望值都可以手算。"""
    store.upsert_entity("center:rd", "dev:Center", "研发中心")
    store.upsert_entity("group:a", "dev:ProjectGroup", "A 项目组", "center:rd")
    store.upsert_entity("project:p", "dev:Project", "P 项目", "group:a")
    store.add_relations([("belongsTo", "group:a", "center:rd"),
                         ("belongsTo", "project:p", "group:a")])

    facts = []
    # 人力快照：A 组 10 名中心人力 + 5 名外包，折算系数 0.6
    for month in ("2026-08-01", "2026-09-01", "2026-10-01"):
        facts.append({"fact_type": "headcount.snapshot", "subject_id": "group:a",
                      "subject_class": "dev:ProjectGroup", "occurred_at": f"{month} 00:00:00",
                      "measures": {"center_headcount": 10, "outsourced_headcount": 5,
                                   "outsourced_factor": 0.6},
                      "fields": {}})

    # 4 个 MR：分析 12h、开发 24h、测试 6h、验收 2h
    for i in range(4):
        mid = f"mr:{i}"
        base = f"2026-10-0{i + 1}"
        store.upsert_entity(mid, "dev:MR", f"MR {i}", "project:p")
        store.add_relations([("deliversTo", mid, "project:p")])
        facts += [
            {"fact_type": "mr.created", "subject_id": mid, "subject_class": "dev:MR",
             "occurred_at": f"{base} 00:00:00", "measures": {},
             "fields": {"project": "project:p", "priority": "P1", "source": "业务方提出"}},
            {"fact_type": "mr.analysis.done", "subject_id": mid, "subject_class": "dev:MR",
             "occurred_at": f"{base} 12:00:00",
             "measures": {"ai_analysis": 2, "total_analysis": 4,
                          "ai_solution": 1, "total_solution": 2}, "fields": {}},
            {"fact_type": "mr.dev.done", "subject_id": mid, "subject_class": "dev:MR",
             "occurred_at": f"2026-10-0{i + 2} 12:00:00",
             "measures": {"ai_lines": 300, "total_lines": 1000}, "fields": {}},
            {"fact_type": "mr.test.done", "subject_id": mid, "subject_class": "dev:MR",
             "occurred_at": f"2026-10-0{i + 2} 18:00:00",
             "measures": {"ai_cases": 3, "total_cases": 6,
                          "ai_scripts": 1, "total_scripts": 2}, "fields": {}},
            {"fact_type": "mr.accepted", "subject_id": mid, "subject_class": "dev:MR",
             "occurred_at": f"2026-10-0{i + 2} 20:00:00", "measures": {}, "fields": {}},
            {"fact_type": "mr.delivered", "subject_id": mid, "subject_class": "dev:MR",
             "occurred_at": f"2026-10-0{i + 2} 21:00:00", "measures": {},
             "fields": {"project": "project:p"}},
            {"fact_type": "mr.ai.touched", "subject_id": mid, "subject_class": "dev:MR",
             "occurred_at": f"{base} 00:00:00", "measures": {},
             "fields": {"artifacts": ["analysis", "code"]}},
        ]

    # RR：计划 10 条，按期 8 条
    facts += [
        {"fact_type": "rr.planned", "subject_id": "rr:1", "subject_class": "dev:RR",
         "occurred_at": "2026-10-01 00:00:00", "measures": {"planned_count": 10},
         "fields": {"project": "project:p"}},
        {"fact_type": "rr.delivered", "subject_id": "rr:1", "subject_class": "dev:RR",
         "occurred_at": "2026-10-05 00:00:00",
         "measures": {"delivered_count": 9, "on_time_count": 8, "planned_count": 10},
         "fields": {"project": "project:p"}},
    ]
    store.add_facts(facts)


@pytest.fixture()
def engine(tmp_path, onto) -> MetricsEngine:
    store = FactStore(tmp_path / "t.db")
    _seed_minimal(store)
    return MetricsEngine(onto, store)


def compute(engine, *ids, **kwargs):
    kwargs.setdefault("start", "2026-10-01")
    kwargs.setdefault("end", "2026-11-01")
    return engine.compute(list(ids), **kwargs)["metrics"]


# ---------------------------------------------------------------- 表达式
def test_safe_eval_blocks_dangerous_syntax():
    assert safe_eval("a / b * 100", {"a": 3, "b": 4}) == 75.0
    with pytest.raises(Exception):
        safe_eval("__import__('os').system('ls')", {})


def test_safe_eval_returns_none_on_zero_division():
    assert safe_eval("a / b", {"a": 1, "b": 0}) is None


def test_normalize_and_status_helpers():
    assert _normalize(50, 100, "higher_better") == 0.5
    assert _normalize(50, 100, "lower_better") == 1.0
    assert _normalize(200, 100, "lower_better") == 0.5
    assert _status(5, 10, "up") == "off"
    assert _status(15, 10, "up") == "ok"
    assert _status(5, 10, "down") == "ok"
    assert _status(None, 10, "up") == "no_data"
    assert _attainment(12, 10, "down") == pytest.approx(0.8333, abs=1e-3)


# ---------------------------------------------------------------- 周期（配对指标）
def test_mr_analysis_cycle_pairs_two_facts(engine):
    m = compute(engine, "mr_analysis_cycle")
    assert m["mr_analysis_cycle"]["value"] == pytest.approx(12.0, abs=0.01)


def test_mr_dev_cycle_pairs_analysis_to_dev(engine):
    m = compute(engine, "mr_dev_cycle")
    assert m["mr_dev_cycle"]["value"] == pytest.approx(24.0, abs=0.01)


def test_mr_impl_cycle_is_created_to_dev_done(engine):
    m = compute(engine, "mr_impl_cycle")
    # 分析 12h + 开发 24h
    assert m["mr_impl_cycle"]["value"] == pytest.approx(36.0, abs=0.01)


def test_mr_accept_cycle_is_dev_to_accepted(engine):
    m = compute(engine, "mr_accept_cycle")
    # 开发完成 10-02 12:00 -> 验收 10-02 20:00
    assert m["mr_accept_cycle"]["value"] == pytest.approx(8.0, abs=0.01)


def test_cycle_metrics_are_lower_better(engine):
    m = compute(engine, "mr_impl_cycle")["mr_impl_cycle"]
    assert m["direction"] == "down"
    assert m["status"] == "ok"


# ---------------------------------------------------------------- 人力口径
def test_snapshot_sums_across_groups_not_average_of_averages(engine):
    """中心人力应为本组 10 人，而不是把三个月的快照相加或平均两次。"""
    m = compute(engine, "headcount_center", "headcount_outsourced", "outsourced_factor")
    assert m["headcount_center"]["value"] == pytest.approx(10.0)
    assert m["headcount_outsourced"]["value"] == pytest.approx(5.0)
    # 折算系数是比率，不能跨组求和
    assert m["outsourced_factor"]["value"] == pytest.approx(0.6)


def test_converted_headcount_applies_factor_to_outsourced_only(engine):
    m = compute(engine, "converted_headcount")
    assert m["converted_headcount"]["value"] == pytest.approx(10 + 5 * 0.6)


def test_per_capita_uses_months_in_denominator(engine):
    """4 个 MR / 10 人 / 1.018 个月（10 月 31 天）= 0.393。"""
    from app.metrics import MONTH_DAYS
    months = 31 / MONTH_DAYS
    m = compute(engine, "mr_impl_per_capita", "mr_impl_per_capita_converted")
    assert m["mr_impl_per_capita"]["value"] == pytest.approx(
        round(4 / 10 / months, 2), abs=1e-6)
    assert m["mr_impl_per_capita_converted"]["value"] == pytest.approx(
        round(4 / (10 + 5 * 0.6) / months, 2), abs=1e-6)


def test_per_capita_scales_with_window_length(engine):
    """两个月的窗口应让月度人均值减半（分母含 months）。"""
    one = compute(engine, "mr_impl_per_capita")
    two = engine.compute(["mr_impl_per_capita"], start="2026-10-01",
                         end="2026-12-01")["metrics"]
    assert one["mr_impl_per_capita"]["value"] > two["mr_impl_per_capita"]["value"]


# ---------------------------------------------------------------- 生成率
def test_generation_rates_use_ai_over_total(engine):
    m = compute(engine, "analysis_gen_rate", "code_gen_rate",
                "ai_testcase_gen_rate", "ai_script_gen_rate", "solution_gen_rate")
    assert m["analysis_gen_rate"]["value"] == pytest.approx(50.0)
    assert m["solution_gen_rate"]["value"] == pytest.approx(50.0)
    assert m["code_gen_rate"]["value"] == pytest.approx(30.0)
    assert m["ai_testcase_gen_rate"]["value"] == pytest.approx(50.0)
    assert m["ai_script_gen_rate"]["value"] == pytest.approx(50.0)


def test_penetration_counts_mrs_not_artifacts(engine):
    """4 个 MR 全部使用 AI -> 100%，与生成率高低无关。"""
    m = compute(engine, "mr_ai_penetration")
    assert m["mr_ai_penetration"]["value"] == pytest.approx(100.0)


# ---------------------------------------------------------------- RR
def test_rr_on_time_rate_aligns_numerator_and_denominator(engine):
    """分子分母取同一批 RR 事实，避免窗口边界错位导致 >100%。"""
    m = compute(engine, "rr_on_time_rate")
    assert m["rr_on_time_rate"]["value"] == pytest.approx(80.0)


def test_rr_rate_never_exceeds_100_with_misaligned_planned_facts(engine):
    """计划在窗口外、交付在窗口内时，达成率仍不得超过 100%。"""
    result = engine.compute(["rr_on_time_rate"], start="2026-10-04", end="2026-11-01")
    value = result["metrics"]["rr_on_time_rate"]["value"]
    assert value is not None and value <= 100.0


# ---------------------------------------------------------------- 复合与下钻
def test_composite_index_within_bounds(engine):
    m = compute(engine, "rde_index")
    assert 0 <= m["rde_index"]["value"] <= 100


def test_composite_declares_all_dependencies(engine, onto):
    index = onto.metric("rde_index")
    components = [c["dep"] for c in index["scoring"]["components"]]
    assert set(components) == set(index["deps"])
    assert sum(c["weight"] for c in index["scoring"]["components"]) == pytest.approx(1.0)


def test_breakdown_by_project_group(engine):
    data = engine.breakdown("mr_impl_per_capita", "projectGroup", "month", 2)
    assert any(i["member"] == "A 项目组" for i in data["items"])


def test_dimension_rollup_through_ontology(engine):
    """项目组维度由 MR -> project -> group 的父链推理得到。"""
    result = engine.compute(["mr_impl_cycle"], start="2026-10-01", end="2026-11-01",
                            filters={"projectGroup": "A 项目组"})
    assert "A 项目组" in result["coverage"]["dimensions"]["projectGroup"]


def test_lineage_contains_transitive_dependencies(engine):
    data = engine.lineage("rde_index")
    ids = {n["id"] for n in data["nodes"]}
    assert {"rde_index", "mr_impl_cycle", "code_gen_rate"} <= ids
    assert data["edges"]


# ---------------------------------------------------------------- 同比对比
def test_compare_returns_base_and_current(engine):
    data = engine.compare(base=("2026-09-01", "2026-09-30"),
                          current=("2026-10-01", "2026-10-31"))
    assert data["base"]["start"] == "2026-09-01"
    ids = {i["id"] for i in data["items"]}
    assert "mr_impl_cycle" in ids
    for item in data["items"]:
        assert set(item) >= {"id", "label", "base", "current", "change", "direction"}


def test_compare_excludes_hidden_metrics(engine):
    data = engine.compare(base=("2026-09-01", "2026-09-30"),
                          current=("2026-10-01", "2026-10-31"))
    ids = {i["id"] for i in data["items"]}
    assert "headcount_center" not in ids


# ---------------------------------------------------------------- 质量检查
def test_quality_flags_time_inversion(tmp_path, onto):
    store = FactStore(tmp_path / "q.db")
    store.upsert_entity("group:a", "dev:ProjectGroup", "A 组")
    store.add_facts([
        {"fact_type": "mr.created", "subject_id": "mr:x", "subject_class": "dev:MR",
         "occurred_at": "2026-10-05 00:00:00", "measures": {}, "fields": {}},
        {"fact_type": "mr.dev.done", "subject_id": "mr:x", "subject_class": "dev:MR",
         "occurred_at": "2026-10-01 00:00:00",
         "measures": {"ai_lines": 1, "total_lines": 2}, "fields": {}},
    ])
    quality = MetricsEngine(onto, store).quality()
    assert any(i["type"] == "时序倒置" for i in quality["issues"])
