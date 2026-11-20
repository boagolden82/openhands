"""确定性演示数据：研发中心 -> 项目组 -> 研发项目 -> MR/RR 全流程事实。

数据有故事性：各项目组有不同的人效基线、AI 采纳节奏与交付纪律，
2026 年起全中心推进 AI 辅助研发，因此生成率与渗透率呈阶梯上升。
时间跨度覆盖 2025-01 至 2026-10，便于做"2025 全年 vs 2026 年 1-10 月"同比。
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Any

from .ontology import Ontology
from .store import FactStore

START = datetime(2025, 1, 1)
END = datetime(2026, 10, 31)

# AI 辅助研发的分阶段推广：越晚比例越高
AI_PHASES = [
    (datetime(2025, 1, 1), 0.15),
    (datetime(2025, 7, 1), 0.30),
    (datetime(2026, 1, 1), 0.55),
    (datetime(2026, 6, 1), 0.72),
]

GROUPS = [
    {
        "id": "group:trade", "label": "交易研发组", "center": ("center:rd", "研发中心"),
        "projects": [("project:trade-core", "交易核心"), ("project:trade-app", "交易前端")],
        "people": 42, "outsourced": 12, "factor": 0.7,
        "speed": 1.10, "discipline": 0.93, "ai_bias": 0.05, "volume": 1.15,
    },
    {
        "id": "group:pay", "label": "支付研发组", "center": ("center:rd", "研发中心"),
        "projects": [("project:pay-core", "支付核心")],
        "people": 28, "outsourced": 8, "factor": 0.7,
        "speed": 1.05, "discipline": 0.90, "ai_bias": 0.02, "volume": 0.95,
    },
    {
        "id": "group:data", "label": "数据研发组", "center": ("center:rd", "研发中心"),
        "projects": [("project:data-plat", "数据平台"), ("project:data-etl", "数据集成")],
        "people": 24, "outsourced": 4, "factor": 0.7,
        "speed": 0.92, "discipline": 0.96, "ai_bias": 0.10, "volume": 0.85,
    },
    {
        "id": "group:infra", "label": "基础架构组", "center": ("center:rd", "研发中心"),
        "projects": [("project:infra-cloud", "云原生底座")],
        "people": 20, "outsourced": 6, "factor": 0.7,
        "speed": 0.88, "discipline": 0.88, "ai_bias": 0.08, "volume": 0.75,
    },
    {
        "id": "group:growth", "label": "增长业务组", "center": ("center:rd", "研发中心"),
        "projects": [("project:growth-mkt", "营销增长"), ("project:growth-crm", "客户运营")],
        "people": 18, "outsourced": 10, "factor": 0.7,
        "speed": 1.18, "discipline": 0.84, "ai_bias": 0.06, "volume": 1.05,
    },
]

SOURCES = ["业务方提出", "客户反馈", "内部规划", "线上问题"]
PRIORITIES = ["P0", "P1", "P2", "P3"]


def _ai_ratio(rng: random.Random, at: datetime, bias: float) -> float:
    ratio = 0.0
    for since, level in AI_PHASES:
        if at >= since:
            ratio = level
    return max(0.0, min(0.95, ratio + bias + rng.uniform(-0.10, 0.10)))


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def seed(onto: Ontology, store: FactStore) -> dict[str, Any]:
    rng = random.Random(20261120)
    store.clear()

    facts: list[dict[str, Any]] = []
    relations: list[tuple[str, str, str]] = []
    entities: list[dict[str, Any]] = []

    def add_entity(entity_id: str, class_id: str, label: str,
                   parent_id: str | None = None, attrs: dict[str, Any] | None = None) -> None:
        entities.append({"id": entity_id, "class_id": class_id, "label": label,
                         "parent_id": parent_id, "attrs": attrs or {}})

    center_id, center_label = GROUPS[0]["center"]
    add_entity(center_id, "dev:Center", center_label)

    for group in GROUPS:
        gid, glabel = group["id"], group["label"]
        add_entity(gid, "dev:ProjectGroup", glabel, center_id,
                   {"people": group["people"], "outsourced": group["outsourced"]})
        relations.append(("belongsTo", gid, center_id))

        for pid, plabel in group["projects"]:
            add_entity(pid, "dev:Project", plabel, gid)
            relations.append(("belongsTo", pid, gid))

        # 人力快照：按月记录，外包按折算系数计入
        month = START
        while month < END:
            facts.append({
                "fact_type": "headcount.snapshot", "subject_id": gid,
                "subject_class": "dev:ProjectGroup", "occurred_at": _iso(month),
                "measures": {
                    "center_headcount": group["people"] + rng.randint(-1, 2),
                    "outsourced_headcount": group["outsourced"] + rng.randint(-1, 2),
                    "outsourced_factor": group["factor"],
                },
                "fields": {},
            })
            month += timedelta(days=30)

        # RR：按研发项目、按月计划与交付
        for pid, plabel in group["projects"]:
            month = START
            while month < END:
                planned = rng.randint(6, 12)
                # 按期达成率随年份提升：滚动排期与 AI 辅助估算带来的真实改善
                year_lift = 0.055 * (month.year - START.year)
                on_time_rate = min(0.99, group["discipline"] + year_lift
                                   + rng.uniform(-0.09, 0.05))
                delivered = max(0, round(planned * rng.uniform(0.85, 1.0)))
                on_time = min(delivered, round(planned * on_time_rate))
                rr_id = f"rr:{pid}-{month:%Y%m}"
                add_entity(rr_id, "dev:RR", f"{plabel} {month:%Y-%m} RR", pid)
                facts.append({
                    "fact_type": "rr.planned", "subject_id": rr_id,
                    "subject_class": "dev:RR", "occurred_at": _iso(month),
                    "measures": {"planned_count": planned},
                    "fields": {"project": pid},
                })
                facts.append({
                    "fact_type": "rr.delivered",
                    "subject_id": rr_id,
                    "subject_class": "dev:RR",
                    "occurred_at": _iso(month + timedelta(days=27)),
                    "measures": {"delivered_count": delivered, "on_time_count": on_time,
                                 "planned_count": planned},
                    "fields": {"project": pid},
                })
                month += timedelta(days=30)

        # MR：每个项目组按周产出，走完分析/开发/测试/验收四阶段
        week = START
        seq = 0
        while week < END:
            # 产出规模逐年爬升：AI 辅助研发让同样的团队承接更多 MR
            ramp = 1.0 + 0.22 * (week.year - START.year) + 0.15 * max(0, (week - START).days / 365 - 1)
            count = max(1, int(round(rng.gauss(
                7.2 * group["volume"] * group["speed"] * ramp, 1.6))))
            for _ in range(count):
                seq += 1
                pid = rng.choice(group["projects"])[0]
                mid = f"mr:{gid.split(':')[1]}-{seq:05d}"
                created = week + timedelta(days=rng.uniform(0, 6), hours=rng.uniform(0, 23))

                # 阶段时长：受 speed 影响，AI 采纳后整体压缩
                ai = _ai_ratio(rng, created, group["ai_bias"])
                # 渗透率是"MR 是否用过 AI"的二值判断，不等于该 MR 有 AI 产物
                uses_ai = rng.random() < ai
                fast = 1.0 - 0.28 * (ai if uses_ai else 0.0)
                analysis_h = rng.uniform(4, 26) / group["speed"] * fast
                dev_h = rng.uniform(12, 68) / group["speed"] * fast
                test_h = rng.uniform(4, 30) / group["speed"] * fast
                accept_h = rng.uniform(2, 18) * fast

                analysis_done = created + timedelta(hours=analysis_h)
                dev_done = analysis_done + timedelta(hours=dev_h)
                test_done = dev_done + timedelta(hours=test_h)
                accepted = test_done + timedelta(hours=accept_h)

                priority = rng.choices(PRIORITIES, weights=[1, 3, 5, 2])[0]
                add_entity(mid, "dev:MR", f"MR {gid.split(':')[1]}-{seq}", pid,
                           {"priority": priority})
                relations.append(("deliversTo", mid, pid))

                facts.append({
                    "fact_type": "mr.created", "subject_id": mid, "subject_class": "dev:MR",
                    "occurred_at": _iso(created),
                    "measures": {},
                    "fields": {"project": pid, "priority": priority,
                               "source": rng.choice(SOURCES)},
                })

                # 分析：AI 生成分析与方案份数
                total_analysis = rng.randint(2, 5)
                total_solution = rng.randint(1, 3)
                if uses_ai:
                    ai_analysis = round(total_analysis * rng.uniform(0.4, 0.9))
                    ai_solution = round(total_solution * rng.uniform(0.4, 0.9))
                else:
                    ai_analysis = ai_solution = 0
                facts.append({
                    "fact_type": "mr.analysis.done", "subject_id": mid,
                    "subject_class": "dev:MR", "occurred_at": _iso(analysis_done),
                    "measures": {"ai_analysis": ai_analysis, "total_analysis": total_analysis,
                                 "ai_solution": ai_solution, "total_solution": total_solution},
                    "fields": {},
                })

                # 开发：AI 生成代码行占比
                total_lines = rng.randint(120, 900)
                ai_lines = round(total_lines * rng.uniform(0.4, 0.9)) if uses_ai else 0
                facts.append({
                    "fact_type": "mr.dev.done", "subject_id": mid, "subject_class": "dev:MR",
                    "occurred_at": _iso(dev_done),
                    "measures": {"ai_lines": ai_lines, "total_lines": total_lines},
                    "fields": {},
                })

                # 测试：用例与脚本
                total_cases = rng.randint(4, 18)
                total_scripts = rng.randint(2, 9)
                ai_cases = round(total_cases * rng.uniform(0.4, 0.9)) if uses_ai else 0
                ai_scripts = round(total_scripts * rng.uniform(0.4, 0.9)) if uses_ai else 0
                facts.append({
                    "fact_type": "mr.test.done", "subject_id": mid, "subject_class": "dev:MR",
                    "occurred_at": _iso(test_done),
                    "measures": {"ai_cases": ai_cases, "total_cases": total_cases,
                                 "ai_scripts": ai_scripts, "total_scripts": total_scripts},
                    "fields": {},
                })

                # 验收：大部分通过，少量返工
                if rng.random() < 0.90:
                    facts.append({
                        "fact_type": "mr.accepted", "subject_id": mid,
                        "subject_class": "dev:MR", "occurred_at": _iso(accepted),
                        "measures": {}, "fields": {},
                    })
                    if rng.random() < 0.88:
                        facts.append({
                            "fact_type": "mr.delivered", "subject_id": mid,
                            "subject_class": "dev:MR",
                            "occurred_at": _iso(accepted + timedelta(hours=rng.uniform(1, 12))),
                            "measures": {}, "fields": {"project": pid},
                        })

                if uses_ai:
                    touched = [name for name, value in
                               (("analysis", ai_analysis), ("code", ai_lines),
                                ("cases", ai_cases), ("scripts", ai_scripts)) if value]
                    facts.append({
                        "fact_type": "mr.ai.touched", "subject_id": mid,
                        "subject_class": "dev:MR", "occurred_at": _iso(created),
                        "measures": {}, "fields": {"artifacts": touched},
                    })

            week += timedelta(weeks=1)

    store.upsert_entities(entities)
    store.add_facts(facts, source="seed")
    store.add_relations(relations)
    store.set_setting("seeded", True)
    store.set_setting("seeded_at", datetime.now().isoformat(timespec="seconds"))
    return {"facts": len(facts), "entities": len(entities), "relations": len(relations)}
