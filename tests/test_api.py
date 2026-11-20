"""HTTP API 端到端测试：真实启动服务并走完整请求链路。"""
from __future__ import annotations

import base64
import json
import threading
import urllib.error
import urllib.request

import pytest

from app.server import create_server


@pytest.fixture()
def live_server(tmp_path, monkeypatch):
    monkeypatch.setenv("RDE_DATA_DIR", str(tmp_path / "data"))
    import app.config as config
    import app.server as server
    monkeypatch.setattr(config, "data_root", lambda: tmp_path / "data")
    monkeypatch.setattr(config, "db_path", lambda: tmp_path / "data" / "rde.db")
    server.CTX = None
    srv = create_server(port=0)
    port = srv.server_address[1]
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        srv.shutdown()
        srv.server_close()
        server.CTX = None


def get(base, path):
    with urllib.request.urlopen(base + path, timeout=30) as res:
        return json.loads(res.read())


def get_raw(base, path):
    with urllib.request.urlopen(base + path, timeout=30) as res:
        return res.read(), res.headers.get("content-type", "")


def post(base, path, payload):
    req = urllib.request.Request(
        base + path, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as res:
        return json.loads(res.read())


# ---------------------------------------------------------------- 基础
def test_health_reports_seeded_counts(live_server):
    data = get(live_server, "/api/health")
    assert data["status"] == "ok"
    assert data["version"] == "2.0.0"
    assert data["counts"]["facts"] > 1000
    assert data["counts"]["byFactType"]["mr.created"] > 100


def test_index_page_served(live_server):
    body, ctype = get_raw(live_server, "/")
    assert "text/html" in ctype
    assert "RDE".encode() in body
    assert b"group-filter" in body


def test_static_assets_served(live_server):
    js, ctype = get_raw(live_server, "/js/app.js")
    assert "javascript" in ctype
    assert b"renderCompare" in js
    css, _ = get_raw(live_server, "/css/app.css")
    assert b".compare-body" in css


# ---------------------------------------------------------------- 总览
def test_overview_has_index_kpis_and_groups(live_server):
    data = get(live_server, "/api/overview?granularity=month&periods=12")
    assert data["indicator"]["id"] == "rde_index"
    assert 0 <= data["indicator"]["value"] <= 100
    assert data["kpis"]
    assert all("status" in k for k in data["kpis"])
    assert {g["member"] for g in data["groups"]}
    assert data["counts"]["facts"] > 0


def test_overview_embeds_year_over_year_compare(live_server):
    data = get(live_server, "/api/overview?granularity=month&periods=12")
    cmp = data["compare"]
    assert cmp["base"]["start"] == "2025-01-01"
    assert cmp["current"]["start"] == "2026-01-01"
    ids = {i["id"] for i in cmp["items"]}
    assert {"mr_impl_cycle", "code_gen_rate", "mr_ai_penetration"} <= ids


def test_overview_group_filter_narrows_results(live_server):
    all_groups = get(live_server, "/api/overview?granularity=month&periods=6")
    name = all_groups["groups"][0]["member"]
    filtered = get(live_server, f"/api/overview?granularity=month&periods=6"
                                 f"&projectGroup={urllib.parse.quote(name)}")
    assert filtered["coverage"]["facts"] <= all_groups["coverage"]["facts"]


# ---------------------------------------------------------------- 指标
def test_metrics_list_exposes_codes_and_layers(live_server):
    data = get(live_server, "/api/metrics")
    by_id = {m["id"]: m for m in data["metrics"]}
    assert by_id["mr_impl_cycle"]["code"] == "2.0.1"
    assert by_id["code_gen_rate"]["code"] == "3.3"
    assert by_id["headcount_center"]["hidden"] is True
    assert by_id["rde_index"]["indicator"] is True
    assert by_id["mr_impl_per_capita_live"]["realtime"] is True


def test_metric_detail_includes_breakdown_by_project_group(live_server):
    data = get(live_server, "/api/metrics/mr_impl_cycle?granularity=month&periods=12")
    assert data["id"] == "mr_impl_cycle"
    assert data["code"] == "2.0.1"
    assert "projectGroup" in data["breakdown"]
    assert data["series"]


def test_metric_detail_accepts_filters(live_server):
    base = get(live_server, "/api/metrics/mr_impl_per_capita?granularity=month&periods=12")
    name = base["breakdown"]["projectGroup"][0]["member"]
    filtered = get(live_server, "/api/metrics/mr_impl_per_capita?granularity=month&periods=12"
                                f"&projectGroup={urllib.parse.quote(name)}")
    assert filtered["value"] is not None


def test_unknown_metric_returns_404(live_server):
    with pytest.raises(urllib.error.HTTPError) as exc:
        get(live_server, "/api/metrics/not_a_metric")
    assert exc.value.code == 404


# ---------------------------------------------------------------- 同比
def test_compare_endpoint_uses_defaults(live_server):
    data = get(live_server, "/api/compare")
    assert data["base"]["start"] == "2025-01-01"
    assert data["current"]["start"] == "2026-01-01"
    assert len(data["items"]) >= 15


def test_compare_endpoint_accepts_custom_ranges(live_server):
    data = get(live_server, "/api/compare?baseStart=2025-01-01&baseEnd=2025-06-30"
                            "&currentStart=2026-01-01&currentEnd=2026-06-30")
    assert data["base"]["end"] == "2025-06-30"
    assert data["current"]["end"] == "2026-06-30"


def test_compare_excludes_internal_metrics(live_server):
    data = get(live_server, "/api/compare")
    ids = {i["id"] for i in data["items"]}
    assert "headcount_center" not in ids
    assert "ai_lines" not in ids


# ---------------------------------------------------------------- 本体与血缘
def test_ontology_endpoint_exposes_structure(live_server):
    data = get(live_server, "/api/ontology")
    assert data["version"] == "2.0.0"
    assert data["stats"]["classes"] >= 25
    assert data["stats"]["factTypes"] >= 10
    assert data["namespaces"]
    assert any(c["id"] == "dev:MR" for c in data["classes"])
    assert any(f["id"] == "mr.created" for f in data["factTypes"])


def test_lineage_reaches_base_metrics(live_server):
    data = get(live_server, "/api/lineage?metric=rde_index")
    ids = {n["id"] for n in data["nodes"]}
    assert "rde_index" in ids
    assert "mr_impl_cycle" in ids
    assert "code_gen_rate" in ids
    assert data["edges"]


def test_quality_reports_full_score_on_seed(live_server):
    data = get(live_server, "/api/quality")
    assert data["score"] >= 99
    assert data["issueCount"] == 0
    assert data["facts"] > 0


# ---------------------------------------------------------------- 事实与导入
def test_facts_endpoint_filters_by_type(live_server):
    data = get(live_server, "/api/facts?factType=mr.created&limit=5")
    assert data["total"] > 0
    assert len(data["rows"]) == 5
    assert all(r["fact_type"] == "mr.created" for r in data["rows"])
    assert any(f["id"] == "mr.dev.done" for f in data["factTypes"])


def test_import_template_matches_fact_type(live_server):
    body, ctype = get_raw(live_server, "/api/import/template?factType=mr.created")
    header = body.decode("utf-8-sig").splitlines()[0]
    assert "text/csv" in ctype
    assert "subject_id" in header
    assert "measure:" not in header


def test_import_roundtrip_writes_rows(live_server):
    before = get(live_server, "/api/health")["counts"]["facts"]
    csv = ("fact_type,subject_id,subject_class,occurred_at,field:project\n"
           "mr.created,test:mr-1,dev:MR,2026-11-01 09:00:00,project:p1\n")
    result = post(live_server, "/api/import", {
        "filename": "t.csv",
        "content": base64.b64encode(csv.encode("utf-8")).decode("ascii"),
    })
    assert result["inserted"] == 1
    assert result["rejected"] == 0
    after = get(live_server, "/api/health")["counts"]["facts"]
    assert after == before + 1


def test_import_dry_run_does_not_write(live_server):
    before = get(live_server, "/api/health")["counts"]["facts"]
    csv = ("fact_type,subject_id,subject_class,occurred_at\n"
           "mr.created,dry:1,dev:MR,2026-11-01 09:00:00\n")
    result = post(live_server, "/api/import", {
        "filename": "d.csv",
        "content": base64.b64encode(csv.encode("utf-8")).decode("ascii"),
        "dryRun": True,
    })
    assert result["inserted"] == 0
    assert get(live_server, "/api/health")["counts"]["facts"] == before


def test_import_rejects_unknown_subject_class(live_server):
    csv = ("fact_type,subject_id,subject_class,occurred_at\n"
           "mr.created,bad:1,dev:NotAClass,2026-11-01 09:00:00\n")
    result = post(live_server, "/api/import", {
        "filename": "b.csv",
        "content": base64.b64encode(csv.encode("utf-8")).decode("ascii"),
    })
    assert result["rejected"] == 1
    assert result["errors"]


# ---------------------------------------------------------------- 报告与预测
def test_report_html_contains_compare_section(live_server):
    body, ctype = get_raw(live_server, "/api/report?format=html&granularity=month&periods=12")
    html = body.decode("utf-8")
    assert "text/html" in ctype
    assert "同比对比" in html
    assert "MR实现周期" in html
    assert "项目组效能对比" in html


def test_report_csv_has_one_row_per_metric(live_server):
    body, ctype = get_raw(live_server, "/api/report?format=csv&granularity=month&periods=12")
    assert "text/csv" in ctype
    lines = body.decode("utf-8-sig").strip().splitlines()
    assert len(lines) > 15
    assert "mr_impl_cycle" in body.decode("utf-8-sig")


def test_forecast_runs_on_mr_throughput(live_server):
    data = post(live_server, "/api/forecast", {"metric": "mr_dev_done_count",
                                               "remaining": 300, "simulations": 500})
    assert data["p50"] <= data["p85"] <= data["p95"]
    assert data["backlog"] == 300


def test_reseed_rebuilds_dataset(live_server):
    data = post(live_server, "/api/reseed", {})
    assert data["ok"] is True
    assert data["facts"] > 1000
    assert get(live_server, "/api/health")["counts"]["facts"] == data["facts"]


def test_settings_expose_paths(live_server):
    data = get(live_server, "/api/settings")
    assert data["ontologyPath"].endswith("ontology.json")
    assert data["dbPath"].endswith(".db")
    assert data["counts"]["entities"] > 0
