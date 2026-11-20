"""确定性演示数据：组织层级 + 26 周研发事实。

数据不是随机噪声：团队有各自的能力基线（速度/质量/流程成熟度），
并在中途注入一次流程改进，使指标趋势可解释、可讲故事。
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Any

from .ontology import Ontology
from .store import FactStore

WEEKS = 26
ANCHOR = datetime(2026, 11, 16)  # 数据窗口的最后一周起点

TEAMS = [
    {"id": "team:pay", "label": "支付中台", "project": ("project:pay", "支付平台"),
     "repo": ("repo:pay-core", "pay-core"), "people": ["陈可", "李维", "王睿", "周涵"],
     "speed": 1.15, "quality": 0.75, "maturity": 0.85, "start_week": 0},
    {"id": "team:mall", "label": "交易前台", "project": ("project:mall", "交易商城"),
     "repo": ("repo:mall-web", "mall-web"), "people": ["赵敏", "孙浩", "吴桐", "郑楠", "冯磊"],
     "speed": 1.0, "quality": 1.0, "maturity": 0.6, "start_week": 0},
    {"id": "team:data", "label": "数据平台", "project": ("project:data", "数据智能"),
     "repo": ("repo:data-etl", "data-etl"), "people": ["何静", "许阳", "邓菲"],
     "speed": 0.85, "quality": 0.85, "maturity": 0.95, "start_week": 0},
    {"id": "team:infra", "label": "基础架构", "project": ("project:infra", "云原生底座"),
     "repo": ("repo:infra-k8s", "infra-k8s"), "people": ["马骁", "柳青", "袁博"],
     "speed": 0.95, "quality": 1.1, "maturity": 0.9, "start_week": 0},
    {"id": "team:mobile", "label": "移动端", "project": ("project:app", "移动应用"),
     "repo": ("repo:app-android", "app-android"), "people": ["唐宁", "范洁", "蒋舟"],
     "speed": 1.05, "quality": 0.9, "maturity": 0.55, "start_week": 6},
]

DEPARTMENTS = [
    {"id": "org:tech", "label": "技术中心", "teams": ["team:pay", "team:mall", "team:data", "team:infra", "team:mobile"]},
]

SPRINT_DAYS = 14
IMPROVEMENT_WEEK = 14  # 引入自动化测试与灰度发布


def _dt(week: int, day_offset: float) -> datetime:
    return ANCHOR + timedelta(weeks=week - WEEKS, days=day_offset)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def seed(onto: Ontology, store: FactStore, weeks: int = WEEKS) -> dict[str, Any]:
    rng = random.Random(20261116)
    store.clear()

    for dept in DEPARTMENTS:
        store.upsert_entity(dept["id"], "dev:Organization", dept["label"], None)

    facts: list[dict[str, Any]] = []
    relations: list[tuple[str, str, str]] = []

    for team in TEAMS:
        tid, tlabel = team["id"], team["label"]
        store.upsert_entity(tid, "dev:Team", tlabel, "org:tech")
        relations.append(("belongsTo", tid, "org:tech"))

        proj_id, proj_label = team["project"]
        repo_id, repo_label = team["repo"]
        store.upsert_entity(proj_id, "dev:Project", proj_label, tid, {"owner": tlabel})
        store.upsert_entity(repo_id, "dev:Repository", repo_label, proj_id, {"stack": "backend"})
        relations += [("belongsTo", proj_id, tid), ("belongsTo", repo_id, proj_id),
                      ("ownedBy", proj_id, tid), ("ownedBy", repo_id, tid)]

        for person in team["people"]:
            pid = f"person:{person}"
            store.upsert_entity(pid, "dev:Person", person, tid)
            relations.append(("belongsTo", pid, tid))

        sprint_seq = 0
        for week in range(team["start_week"], weeks):
            if week % 2 == 0:
                sprint_seq += 1
                sprint_id = f"sprint:{tid.split(':')[1]}-{sprint_seq:02d}"
                started = _dt(week, 0)
                ended = started + timedelta(days=SPRINT_DAYS)
                store.upsert_entity(sprint_id, "dev:Sprint", f"{tlabel} S{sprint_seq}",
                                    tid, {"started": _iso(started), "ended": _iso(ended)})
                relations.append(("belongsTo", sprint_id, tid))

                improved = week >= IMPROVEMENT_WEEK
                committed = rng.randint(30, 46) * team["speed"]
                reliability = min(0.98, 0.72 + 0.12 * team["maturity"] + (0.06 if improved else 0))
                completed = committed * rng.uniform(reliability - 0.06, reliability + 0.06)
                facts.append({
                    "fact_type": "sprint.completed", "subject_id": sprint_id,
                    "subject_class": "dev:Sprint", "occurred_at": _iso(ended),
                    "measures": {"committed_points": round(committed),
                                 "completed_points": round(completed)},
                    "fields": {"team": tlabel},
                })

            sprint_id = f"sprint:{tid.split(':')[1]}-{sprint_seq:02d}"
            improved = week >= IMPROVEMENT_WEEK
            items_this_week = max(1, int(round(rng.gauss(5.2 * team["speed"], 1.4))))

            for n in range(items_this_week):
                kind = rng.choices(
                    ["story", "story", "story", "defect", "techdebt"],
                    weights=[5, 5, 4, 2 + (1 if team["quality"] > 1 else 0), 1.4])[0]
                cls = {"story": "dev:Story", "defect": "dev:Defect", "techdebt": "dev:TechDebt"}[kind]
                wid = f"wi:{tid.split(':')[1]}-{week}-{n}"
                created = _dt(week, rng.uniform(0, 6))
                store.upsert_entity(wid, cls, f"{tlabel} 工作项 {week}-{n}", sprint_id,
                                    {"kind": kind})
                relations += [("belongsTo", wid, sprint_id), ("inSprint", wid, sprint_id)]

                points = rng.choice([1, 2, 3, 3, 5, 5, 8]) if kind != "defect" else rng.choice([1, 1, 2, 3])
                status = rng.choices(["done", "in_progress", "todo", "blocked"],
                                     weights=[6, 2, 2, 0.4])[0]
                escaped = kind == "defect" and rng.random() < (0.22 * team["quality"])
                facts.append({
                    "fact_type": "workitem.created", "subject_id": wid, "subject_class": cls,
                    "occurred_at": _iso(created),
                    "measures": {"story_points": points},
                    "fields": {"status": status, "title": f"{tlabel} 工作项", "priority": rng.choice(["P0", "P1", "P2", "P2"]),
                               "escaped": escaped, "labels": [kind]},
                })
                if status == "done":
                    closed = created + timedelta(days=rng.uniform(1.2, 6.5))
                    facts.append({
                        "fact_type": "workitem.closed", "subject_id": wid, "subject_class": cls,
                        "occurred_at": _iso(closed), "measures": {},
                        "fields": {"status": "done"},
                    })

                # 每个工作项 1~2 个提交
                for c in range(rng.randint(1, 2)):
                    author = rng.choice(team["people"])
                    added = int(rng.gauss(120, 45))
                    deleted = int(rng.gauss(35, 20))
                    churn = int(max(0, added * rng.uniform(0.03, 0.22) * (1.25 - 0.4 * team["maturity"])))
                    committed_at = created + timedelta(days=rng.uniform(0.3, 4.5), hours=rng.uniform(0, 9))
                    facts.append({
                        "fact_type": "commit.pushed", "subject_id": f"commit:{wid}-{c}",
                        "subject_class": "dev:Commit", "occurred_at": _iso(committed_at),
                        "measures": {"lines_added": max(added, 5), "lines_deleted": max(deleted, 0),
                                     "lines_changed": max(added, 5) + max(deleted, 0),
                                     "churn_lines": churn, "files_changed": rng.randint(1, 9)},
                        "fields": {"author": author, "repo": repo_id, "message": f"feat: {wid}"},
                    })

                # 合并请求与评审
                if rng.random() < 0.9:
                    pr_id = f"pr:{wid}"
                    pr_created = created + timedelta(days=rng.uniform(0.5, 3))
                    review_lag = rng.uniform(2, 30) * (1.35 - 0.5 * team["maturity"])
                    if week >= IMPROVEMENT_WEEK:
                        review_lag *= 0.72
                    merged = pr_created + timedelta(hours=review_lag)
                    store.upsert_entity(pr_id, "dev:PullRequest", f"PR {wid}", repo_id,
                                        {"repo_label": repo_label})
                    relations += [("belongsTo", pr_id, repo_id), ("implements", pr_id, wid)]
                    facts.append({
                        "fact_type": "pr.merged", "subject_id": pr_id,
                        "subject_class": "dev:PullRequest", "occurred_at": _iso(merged),
                        "measures": {"lines_changed": rng.randint(40, 420),
                                     "open_hours": round((merged - pr_created).total_seconds() / 3600, 2)},
                        "fields": {"author": author, "repo": repo_id, "workitem": wid},
                    })
                    if rng.random() < 0.9 * min(1.0, team["maturity"] + 0.25):
                        facts.append({
                            "fact_type": "review.submitted", "subject_id": f"review:{pr_id}",
                            "subject_class": "dev:Review", "occurred_at": _iso(pr_created + timedelta(hours=review_lag * 0.4)),
                            "measures": {"comments": rng.randint(0, 7)},
                            "fields": {"reviewer": rng.choice(team["people"]), "pr": pr_id,
                                       "verdict": rng.choices(["approve", "comment", "request_changes"],
                                                              weights=[7, 2, 1])[0],
                                       "repo": repo_id},
                        })

            # 流水线
            runs = max(2, int(rng.gauss(9 * team["speed"], 2.2)))
            for r in range(runs):
                started = _dt(week, rng.uniform(0, 7))
                ok = rng.random() < min(0.985, 0.80 + 0.14 * team["maturity"] + (0.04 if improved else 0))
                duration = rng.gauss(13.5 - 3.2 * team["maturity"], 3.5)
                if improved:
                    duration *= 0.85
                facts.append({
                    "fact_type": "pipeline.completed", "subject_id": f"ci:{tid.split(':')[1]}-{week}-{r}",
                    "subject_class": "dev:PipelineRun",
                    "occurred_at": _iso(started + timedelta(minutes=max(duration, 2))),
                    "measures": {"duration_sec": int(max(duration, 2) * 60)},
                    "fields": {"status": "success" if ok else rng.choice(["failed", "failed", "canceled"]),
                               "repo": repo_id, "stage": "build-test"},
                })

            # 部署
            deploys = max(1, int(rng.gauss(3.4 * team["speed"], 1.3)))
            for d in range(deploys):
                dep_at = _dt(week, rng.uniform(0.5, 6.8))
                env = rng.choices(["dev", "staging", "prod"], weights=[2, 2, 5])[0]
                lead = max(6.0, rng.gauss(92 - 30 * team["maturity"], 26))
                if improved:
                    lead *= 0.78
                facts.append({
                    "fact_type": "deployment.finished", "subject_id": f"deploy:{tid.split(':')[1]}-{week}-{d}",
                    "subject_class": "dev:Deployment", "occurred_at": _iso(dep_at),
                    "measures": {"duration_sec": int(rng.gauss(420, 90)),
                                 "lead_time_hours": round(lead, 1)},
                    "fields": {"env": env, "repo": repo_id, "status": "success"},
                })
                if env == "prod" and rng.random() < 0.16 * team["quality"] * (0.7 if improved else 1):
                    resolved = dep_at + timedelta(minutes=rng.gauss(78 * team["quality"], 26))
                    facts.append({
                        "fact_type": "incident.resolved", "subject_id": f"inc:{tid.split(':')[1]}-{week}-{d}",
                        "subject_class": "dev:Incident", "occurred_at": _iso(resolved),
                        "measures": {"mttr_minutes": max(8, round((resolved - dep_at).total_seconds() / 60))},
                        "fields": {"severity": rng.choices(["SEV1", "SEV2", "SEV3"], weights=[1, 3, 5])[0],
                                   "repo": repo_id, "team": tlabel},
                    })

            if week % 4 == 3:
                facts.append({
                    "fact_type": "release.published", "subject_id": f"release:{tid.split(':')[1]}-{week}",
                    "subject_class": "dev:Release", "occurred_at": _iso(_dt(week, 6)),
                    "measures": {},
                    "fields": {"version": f"v1.{week // 4}", "project": proj_label, "repo": repo_id},
                })

    store.add_facts(facts, source="seed")
    store.add_relations(relations)
    store.set_setting("seeded", True)
    store.set_setting("seeded_at", datetime.now().isoformat(timespec="seconds"))
    return {"facts": len(facts), "relations": len(relations), "weeks": weeks}
