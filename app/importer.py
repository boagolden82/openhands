"""CSV 事实导入：把外部系统（Jira/禅道/GitLab/Jenkins）数据映射为本体事实。

两种格式：
1) 长表：fact_type,subject_id,subject_class,occurred_at,measure:xxx,field:xxx
2) 模板表：由 fact type 的字段定义驱动（如 workitem.created 需要 status/title 等）
"""
from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any

from .ontology import Ontology
from .store import FactStore

TIME_ALIASES = ("occurred_at", "time", "timestamp", "时间", "发生时间", "date")
SUBJECT_ALIASES = ("subject_id", "subject", "id", "主体")
CLASS_ALIASES = ("subject_class", "class", "类")


def _norm(value: str) -> str:
    return (value or "").strip()


def _parse_time(value: str) -> str | None:
    value = _norm(value)
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M",
                "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d"):
        try:
            return datetime.strptime(value.replace("Z", "")[:19], fmt).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
    return None


def _coerce(value: str) -> Any:
    text = _norm(value)
    if text == "":
        return None
    low = text.lower()
    if low in {"true", "yes", "y", "1"}:
        return True
    if low in {"false", "no", "n", "0"}:
        return False
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return text


def import_csv(onto: Ontology, store: FactStore, content: bytes, filename: str,
               fact_type: str | None = None, dry_run: bool = False) -> dict[str, Any]:
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("CSV 缺少表头")
    headers = {_norm(h).lower(): h for h in reader.fieldnames}

    def pick(row: dict[str, Any], aliases: tuple[str, ...]) -> str | None:
        for alias in aliases:
            key = headers.get(alias.lower())
            if key and _norm(row.get(key, "")):
                return _norm(row[key])
        return None

    rows, errors = [], []
    for line_no, row in enumerate(reader, start=2):
        ftype = fact_type or pick(row, ("fact_type", "type", "事实类型"))
        if not ftype or ftype not in onto.fact_types:
            errors.append({"line": line_no, "error": f"未知事实类型：{ftype}"})
            continue
        spec = onto.fact_types[ftype]
        subject = pick(row, SUBJECT_ALIASES)
        if not subject:
            errors.append({"line": line_no, "error": "缺少主体 id"})
            continue
        subject_class = pick(row, CLASS_ALIASES) or spec.subject
        if subject_class not in onto.classes:
            errors.append({"line": line_no, "error": f"未知主体类：{subject_class}"})
            continue
        if not onto.is_subclass(subject_class, spec.subject):
            errors.append({"line": line_no,
                           "error": f"{subject_class} 不是 {spec.subject} 的子类（本体校验失败）"})
            continue
        occurred = _parse_time(pick(row, (spec.time_field,) + TIME_ALIASES) or "")
        if not occurred:
            errors.append({"line": line_no, "error": "时间格式无法解析"})
            continue

        measures, fields = {}, {}
        for measure in spec.measures:
            for candidate in (f"measure:{measure}", measure):
                key = headers.get(candidate.lower())
                if key:
                    value = _coerce(row.get(key, ""))
                    if value is not None:
                        measures[measure] = value
                    break
        for field in spec.fields + ("env", "author", "repo", "severity", "pr"):
            for candidate in (f"field:{field}", field):
                key = headers.get(candidate.lower())
                if key:
                    value = _coerce(row.get(key, ""))
                    if value is not None:
                        fields[field] = value
                    break
        rows.append({
            "fact_type": ftype, "subject_id": subject, "subject_class": subject_class,
            "occurred_at": occurred, "measures": measures, "fields": fields,
        })

    inserted = 0
    if rows and not dry_run:
        inserted = store.add_facts(rows, source=f"import:{filename}")
        store.log_import(filename, fact_type, len(rows) + len(errors), inserted, len(errors), errors)

    return {
        "filename": filename, "rows": len(rows) + len(errors), "accepted": len(rows),
        "inserted": inserted, "rejected": len(errors), "errors": errors[:100],
        "preview": rows[:5], "dryRun": dry_run,
    }


def template_csv(onto: Ontology, fact_type: str) -> str:
    spec = onto.fact_types.get(fact_type)
    if not spec:
        raise ValueError(f"未知事实类型：{fact_type}")
    columns = ["fact_type", "subject_id", "subject_class", spec.time_field]
    columns += [f"measure:{m}" for m in spec.measures]
    columns += [f"field:{f}" for f in spec.fields]
    sample_measures = {"story_points": 3, "lines_added": 120, "lines_deleted": 30,
                       "lines_changed": 150, "churn_lines": 12, "files_changed": 4,
                       "duration_sec": 600, "lead_time_hours": 48.5,
                       "committed_points": 40, "completed_points": 36, "mttr_minutes": 45,
                       "open_hours": 12.5, "comments": 2}
    sample_fields = {"status": "success", "title": "示例工作项", "priority": "P1",
                     "escaped": False, "labels": "story", "env": "prod", "author": "张三",
                     "repo": "repo:pay-core", "severity": "SEV2", "pr": "pr:wi-1-1",
                     "reviewer": "李四", "verdict": "approve", "stage": "build-test"}
    row = {"fact_type": fact_type, "subject_id": f"example:{fact_type}", "subject_class": spec.subject,
           spec.time_field: datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    row.update({f"measure:{m}": sample_measures.get(m, 1) for m in spec.measures})
    row.update({f"field:{f}": sample_fields.get(f, "") for f in spec.fields})

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns)
    writer.writeheader()
    writer.writerow(row)
    return buf.getvalue()
