"""指标引擎测试：用人工构造的最小数据集验证口径正确性。"""
from __future__ import annotations

import pytest

from app.metrics import MetricsEngine, safe_eval, _normalize, _status
from app.ontology import Ontology
from app.store import FactStore


@pytest.fixture()
def onto() -> Ontology:
    from app.config import ontology_path
    return Ontology.load(ontology_path())


@pytest.fixture()
def engine(tmp_path, onto) -> MetricsEngine:
    store = FactStore(tmp_path / "t.db")
    # 组织：org -> team -> project -> repo
    store.upsert_entity("org:x", "dev:Organization", "研发中心")
    store.upsert_entity("team:a", "dev:Team", "A 团队", "org:x")
    store.upsert_entity("project:p", "dev:Project", "P 项目", "team:a")
    store.upsert_entity("repo:r", "dev:Repository", "r", "project:p")
    store.upsert_entity("sprint:s1", "dev:Sprint", "S1", "team:a")
    store.add_relations([("belongsTo", "team:a", "org:x"), ("belongsTo", "project:p", "team:a"),
                         ("belongsTo", "repo:r", "project:p"), ("belongsTo", "sprint:s1", "team:a")])

    facts = []
    # 3 个部署，前置时间 24/48/72 小时 -> 均值 48
    for i, lead in enumerate([24, 48, 72]):
        facts.append({"fact_type": "deployment.finished", "subject_id": f"d{i}",
                      "subject_class": "dev:Deployment", "occurred_at": f"2026-10-0{i + 1} 10:00:00",
                      "measures": {"lead_time_hours": lead, "duration_sec": 60},
                      "fields": {"env": "prod", "repo": "repo:r", "status": "success"}})
    # 1 个线上事件 -> 变更失败率 = 1/3*100
    facts.append({"fact_type": "incident.resolved", "subject_id": "inc1",
                  "subject_class": "dev:Incident", "occurred_at": "2026-10-02 12:00:00",
                  "measures": {"mttr_minutes": 30},
                  "fields": {"severity": "SEV2", "repo": "repo:r", "team": "A 团队"}})
    # 工作项：1 个缺陷（逃逸）、1 个技术债、2 个故事
    specs = [("w1", "dev:Defect", 3, True), ("w2", "dev:TechDebt", 5, False),
             ("w3", "dev:Story", 8, False), ("w4", "dev:Story", 2, False)]
    for wid, cls, points, escaped in specs:
        facts.append({"fact_type": "workitem.created", "subject_id": wid, "subject_class": cls,
                      "occurred_at": "2026-10-01 09:00:00",
                      "measures": {"story_points": points},
                      "fields": {"status": "in_progress", "escaped": escaped, "title": wid}})
    # w3 在 48 小时后关闭 -> 周期 48h
    facts.append({"fact_type": "workitem.closed", "subject_id": "w3",
                  "subject_class": "dev:Story", "occurred_at": "2026-10-03 09:00:00",
                  "measures": {}, "fields": {"status": "done"}})
    # 流水线 2 次成功 1 次失败，时长各 600s
    for i, status in enumerate(["success", "success", "failed"]):
        facts.append({"fact_type": "pipeline.completed", "subject_id": f"ci{i}",
                      "subject_class": "dev:PipelineRun", "occurred_at": f"2026-10-0{i + 1} 08:00:00",
                      "measures": {"duration_sec": 600},
                      "fields": {"status": status, "repo": "repo:r", "stage": "build"}})
    facts.append({"fact_type": "sprint.completed", "subject_id": "sprint:s1",
                  "subject_class": "dev:Sprint", "occurred_at": "2026-10-14 18:00:00",
                  "measures": {"committed_points": 20, "completed_points": 18},
                  "fields": {"team": "A 团队"}})
    store.add_facts(facts)
    return MetricsEngine(onto, store)


def compute(engine, *ids, **kwargs):
    kwargs.setdefault("start", "2026-09-28")
    kwargs.setdefault("end", "2026-10-19")
    result = engine.compute(list(ids), **kwargs)
    return result["metrics"]


def test_atomic_average_and_count(engine):
    m = compute(engine, "lead_time_hours", "deploy_count")
    assert m["lead_time_hours"]["value"] == 48.0
    assert m["deploy_count"]["value"] == 3.0


def test_class_based_filter_uses_subsumption(engine):
    """缺陷/技术债指标依赖本体类归属推理，而非 type 字段。"""
    m = compute(engine, "defect_total", "defect_escaped", "tech_debt_points", "total_story_points")
    assert m["defect_total"]["value"] == 1.0
    assert m["defect_escaped"]["value"] == 1.0
    assert m["tech_debt_points"]["value"] == 5.0
    assert m["total_story_points"]["value"] == 18.0


def test_derived_ratio_and_percentage(engine):
    m = compute(engine, "change_failure_rate", "ci_success_rate", "ci_duration_minutes",
                "sprint_completion_rate", "tech_debt_ratio")
    assert m["change_failure_rate"]["value"] == pytest.approx(1 / 3 * 100, abs=0.05)
    assert m["ci_success_rate"]["value"] == pytest.approx(2 / 3 * 100, abs=0.05)
    assert m["ci_duration_minutes"]["value"] == pytest.approx(10.0, abs=0.05)
    assert m["sprint_completion_rate"]["value"] == pytest.approx(90.0, abs=0.05)
    assert m["tech_debt_ratio"]["value"] == pytest.approx(5 / 18 * 100, abs=0.05)


def test_pair_metric_joins_two_fact_types(engine):
    m = compute(engine, "cycle_time_hours")
    assert m["cycle_time_hours"]["value"] == 48.0


def test_target_status_and_direction(engine):
    m = compute(engine, "lead_time_hours", "deploy_frequency")
    # 前置时间目标 48，等于目标 -> 达标
    assert m["lead_time_hours"]["status"] == "ok"
    assert m["lead_time_hours"]["direction"] == "down"


def test_dimension_rollup_through_ontology(engine):
    """团队维度由 repo -> project -> team 的传递关系推理得到。"""
    result = engine.compute(["deploy_count"], start="2026-09-28", end="2026-10-19",
                            filters={"team": "A 团队"})
    assert result["metrics"]["deploy_count"]["value"] == 3.0
    assert "A 团队" in result["coverage"]["dimensions"]["team"]


def test_filters_narrow_results(engine):
    """过滤到不存在的环境时，计数指标应为 0 而不是沿用全量数据。"""
    result = engine.compute(["deploy_count"], start="2026-09-28", end="2026-10-19",
                            filters={"env": "staging"})
    assert result["metrics"]["deploy_count"]["value"] == 0.0


def test_per_week_normalization(engine):
    """3 次部署 / 3 周 = 1 次每周。"""
    m = compute(engine, "deploy_frequency")
    assert m["deploy_frequency"]["value"] == pytest.approx(1.0, abs=0.05)


def test_composite_scoring_bounds(engine):
    m = compute(engine, "dev_eff_index")
    assert 0 <= m["dev_eff_index"]["value"] <= 100


def test_breakdown_by_team(engine):
    data = engine.breakdown("deploy_count", "team", "week", 4)
    assert any(item["member"] == "A 团队" for item in data["items"])


def test_lineage_contains_dependencies(engine):
    data = engine.lineage("change_failure_rate")
    ids = {n["id"] for n in data["nodes"]}
    assert {"change_failure_rate", "incident_count", "deploy_count"} <= ids
    edges = {(e["from"], e["to"]) for e in data["edges"]}
    assert ("incident_count", "change_failure_rate") in edges


def test_quality_flags_negative_measure(tmp_path, onto):
    store = FactStore(tmp_path / "q.db")
    store.upsert_entity("team:a", "dev:Team", "A")
    store.upsert_entity("repo:r", "dev:Repository", "r", "team:a")
    store.add_facts([{"fact_type": "commit.pushed", "subject_id": "c1", "subject_class": "dev:Commit",
                      "occurred_at": "2026-10-01 10:00:00",
                      "measures": {"lines_added": -5, "lines_deleted": 0, "lines_changed": 5,
                                   "churn_lines": 0, "files_changed": 1},
                      "fields": {"author": "x", "repo": "repo:r"}}])
    report = MetricsEngine(onto, store).quality()
    types = {i["type"] for i in report["issues"]}
    assert "度量取值为负" in types


def test_quality_flags_class_mismatch(tmp_path, onto):
    store = FactStore(tmp_path / "q2.db")
    store.upsert_entity("team:a", "dev:Team", "A")
    store.upsert_entity("repo:r", "dev:Repository", "r", "team:a")
    # 用 Commit 类去承载 workitem.created 事实 -> 违反本体约束
    store.add_facts([{"fact_type": "workitem.created", "subject_id": "x1",
                      "subject_class": "dev:Commit", "occurred_at": "2026-10-01 10:00:00",
                      "measures": {"story_points": 3}, "fields": {"status": "todo"}}])
    report = MetricsEngine(onto, store).quality()
    assert any(i["type"] == "主体类与事实类型不匹配" for i in report["issues"])


def test_forecast_requires_history(tmp_path, onto):
    """历史周期不足 3 个时应拒绝预测，而不是给出误导性结论。"""
    from app.metrics import MetricError
    store = FactStore(tmp_path / "fc.db")
    store.upsert_entity("team:a", "dev:Team", "A")
    store.add_facts([{"fact_type": "workitem.closed", "subject_id": "w1",
                      "subject_class": "dev:Story", "occurred_at": "2026-10-01 10:00:00",
                      "measures": {}, "fields": {"status": "done"}}])
    with pytest.raises(MetricError):
        MetricsEngine(onto, store).forecast("delivered_items", periods=4)


def test_safe_eval_blocks_unsafe_code():
    from app.metrics import MetricError
    with pytest.raises(MetricError):
        safe_eval("__import__('os').system('echo hi')", {})
    with pytest.raises(MetricError):
        safe_eval("open('/etc/passwd')", {})
    assert safe_eval("a / b * 100", {"a": 1, "b": 4}) == 25.0
    assert safe_eval("a / b", {"a": 1, "b": 0}) is None
    assert safe_eval("a + b", {"a": None, "b": 1}) is None


def test_normalize_and_status_helpers():
    assert _normalize(60, 48, "lower_better") == pytest.approx(0.8)
    assert _normalize(10, 10, "higher_better") == 1.0
    assert _normalize(100, 10, "higher_better") == 1.0  # 上限裁剪
    assert _status(40, 48, "down") == "ok"
    assert _status(60, 48, "down") == "off"
    assert _status(None, 48, "down") == "no_data"


def test_insights_skip_non_primary_metrics(engine):
    insights = engine.insights()
    primary = {m["id"] for m in engine.onto.metrics if m.get("primary") or m.get("indicator")}
    assert all(i["metric"] in primary for i in insights)


def test_pair_metric_reads_start_facts_before_window(tmp_path, onto):
    """工单在窗口前创建、窗口内关闭，周期仍应算全，不能被截断成窗口内时长。"""
    store = FactStore(tmp_path / "pair.db")
    store.upsert_entity("team:a", "dev:Team", "A")
    store.upsert_entity("repo:r", "dev:Repository", "r", "team:a")
    store.add_facts([
        {"fact_type": "workitem.created", "subject_id": "w1", "subject_class": "dev:Story",
         "occurred_at": "2026-09-20 00:00:00", "measures": {"story_points": 3},
         "fields": {"status": "todo", "repo": "repo:r"}},
        {"fact_type": "workitem.closed", "subject_id": "w1", "subject_class": "dev:Story",
         "occurred_at": "2026-10-10 00:00:00", "measures": {},
         "fields": {"status": "done", "repo": "repo:r"}},
    ])
    engine = MetricsEngine(onto, store)
    result = engine.compute(["cycle_time_hours"], start="2026-10-05", end="2026-10-19")
    # 2026-09-20 00:00 → 2026-10-10 00:00 = 20 天 = 480 小时
    assert result["metrics"]["cycle_time_hours"]["value"] == pytest.approx(480.0, abs=0.5)
