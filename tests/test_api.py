"""HTTP API 与 CSV 导入的集成测试（真实启动服务并走 HTTP）。"""
from __future__ import annotations

import base64
import json
import threading
import urllib.error
import urllib.request

import pytest

from app import server
from app.importer import import_csv, template_csv


@pytest.fixture(scope="module")
def live_server(tmp_path_factory):
    data_dir = tmp_path_factory.mktemp("rde")
    import os
    os.environ["RDE_DATA_DIR"] = str(data_dir)
    os.environ["RDE_NO_BROWSER"] = "1"
    server.CTX = None
    httpd = server.create_server("127.0.0.1", 0)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    httpd.shutdown()
    httpd.server_close()
    server.CTX = None


def get(base, path):
    with urllib.request.urlopen(base + path, timeout=30) as res:
        return json.loads(res.read().decode("utf-8"))


def post(base, path, payload):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(base + path, data=data, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as res:
        return json.loads(res.read().decode("utf-8"))


def test_health_and_seed(live_server):
    data = get(live_server, "/api/health")
    assert data["status"] == "ok"
    assert data["counts"]["facts"] > 0


def test_overview_returns_indicator_and_kpis(live_server):
    data = get(live_server, "/api/overview?periods=12")
    assert data["indicator"]["id"] == "dev_eff_index"
    assert data["kpis"]
    assert all(k.get("primary") or k.get("indicator") for k in data["kpis"])
    assert data["coverage"]["facts"] > 0
    assert isinstance(data["insights"], list)


def test_metric_detail_has_breakdown(live_server):
    data = get(live_server, "/api/metrics/lead_time_hours")
    assert data["id"] == "lead_time_hours"
    assert data["series"]
    assert "team" in data["breakdown"]
    assert data["definition"]["formula"]


def test_unknown_metric_returns_404(live_server):
    with pytest.raises(urllib.error.HTTPError) as exc:
        get(live_server, "/api/metrics/not_a_metric")
    assert exc.value.code == 404


def test_ontology_endpoint(live_server):
    data = get(live_server, "/api/ontology")
    assert data["stats"]["classes"] > 20
    assert data["factTypes"]


def test_lineage_endpoint(live_server):
    data = get(live_server, "/api/lineage?metric=dev_eff_index")
    ids = {n["id"] for n in data["nodes"]}
    assert "dev_eff_index" in ids and "change_failure_rate" in ids


def test_quality_endpoint(live_server):
    data = get(live_server, "/api/quality")
    assert 0 <= data["score"] <= 100
    assert isinstance(data["issues"], list)


def test_facts_endpoint_filters(live_server):
    data = get(live_server, "/api/facts?factType=deployment.finished&limit=5")
    assert len(data["rows"]) <= 5
    assert all(r["fact_type"] == "deployment.finished" for r in data["rows"])


def test_report_html_and_csv(live_server):
    with urllib.request.urlopen(live_server + "/api/report?format=html", timeout=30) as res:
        html = res.read().decode("utf-8")
        assert "研发效能指标报告" in html
        assert "研发效能指数" in html
    with urllib.request.urlopen(live_server + "/api/report?format=csv", timeout=30) as res:
        csv_text = res.read().decode("utf-8-sig")
        assert "指标ID" in csv_text.splitlines()[0]


def test_forecast_endpoint(live_server):
    data = post(live_server, "/api/forecast", {"metric": "delivered_items", "remaining": 60})
    assert data["p50"] <= data["p85"] <= data["p95"]
    assert sum(h["count"] for h in data["histogram"]) > 0


def test_import_roundtrip_and_validation(live_server):
    csv_text = (
        "fact_type,subject_id,subject_class,occurred_at,measure:duration_sec,field:status,field:repo\n"
        "pipeline.completed,ci:test-1,dev:PipelineRun,2026-11-01 10:00:00,300,success,repo:pay-core\n"
        "pipeline.completed,ci:test-2,dev:Commit,2026-11-01 11:00:00,300,success,repo:pay-core\n"
        "pipeline.completed,ci:test-3,dev:PipelineRun,not-a-date,300,success,repo:pay-core\n"
        "unknown.fact,ci:test-4,dev:PipelineRun,2026-11-01 12:00:00,300,success,repo:pay-core\n"
    )
    before = get(live_server, "/api/health")["counts"]["facts"]
    result = post(live_server, "/api/import", {
        "filename": "test.csv",
        "content": base64.b64encode(csv_text.encode("utf-8")).decode("ascii"),
    })
    assert result["accepted"] == 1
    assert result["rejected"] == 3
    errors = " ".join(e["error"] for e in result["errors"])
    assert "子类" in errors
    assert "时间格式" in errors
    assert "未知事实类型" in errors
    after = get(live_server, "/api/health")["counts"]["facts"]
    assert after == before + 1
    logs = get(live_server, "/api/import/logs")["logs"]
    assert logs[0]["filename"] == "test.csv"


def test_static_index_served(live_server):
    with urllib.request.urlopen(live_server + "/", timeout=30) as res:
        html = res.read().decode("utf-8")
        assert "效能指标体系" in html
        assert "/js/app.js" in html


def test_import_csv_dry_run_does_not_write(tmp_path):
    from app.config import ontology_path
    from app.ontology import Ontology
    from app.store import FactStore
    onto = Ontology.load(ontology_path())
    store = FactStore(tmp_path / "dry.db")
    content = ("fact_type,subject_id,subject_class,occurred_at,measure:story_points,field:status\n"
               "workitem.created,w1,dev:Story,2026-10-01 09:00:00,3,todo\n").encode("utf-8")
    result = import_csv(onto, store, content, "dry.csv", dry_run=True)
    assert result["accepted"] == 1
    assert result["inserted"] == 0
    assert store.counts()["facts"] == 0


def test_template_csv_matches_fact_type():
    from app.config import ontology_path
    from app.ontology import Ontology
    onto = Ontology.load(ontology_path())
    text = template_csv(onto, "deployment.finished")
    header = text.splitlines()[0]
    assert "measure:lead_time_hours" in header
    assert "field:env" in header
    assert header.startswith("fact_type,subject_id,subject_class,finished_at")


def test_reseed_resets_data(live_server):
    post(live_server, "/api/reseed", {})
    data = get(live_server, "/api/health")
    assert data["counts"]["facts"] > 1000
