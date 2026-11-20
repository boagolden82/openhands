"""事实存储：以三元组 + 度量列的方式保存本体事实。

设计要点
* facts 表统一承载所有事实类型，避免为每种事实建表；
* subject_class 由写入方声明，读取时再用本体推理校验/上卷；
* 实体表保存层级关系（belongsTo）与属性，用于维度上卷。
"""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS entities (
    id           TEXT PRIMARY KEY,
    class_id     TEXT NOT NULL,
    label        TEXT NOT NULL,
    parent_id    TEXT,
    attrs        TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_entities_class ON entities(class_id);
CREATE INDEX IF NOT EXISTS idx_entities_parent ON entities(parent_id);

CREATE TABLE IF NOT EXISTS facts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    fact_type    TEXT NOT NULL,
    subject_id   TEXT NOT NULL,
    subject_class TEXT NOT NULL,
    occurred_at  TEXT NOT NULL,
    measures     TEXT NOT NULL DEFAULT '{}',
    fields       TEXT NOT NULL DEFAULT '{}',
    source       TEXT NOT NULL DEFAULT 'seed',
    imported_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_facts_type ON facts(fact_type);
CREATE INDEX IF NOT EXISTS idx_facts_time ON facts(occurred_at);
CREATE INDEX IF NOT EXISTS idx_facts_subject ON facts(subject_id);

CREATE TABLE IF NOT EXISTS relations (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    rel       TEXT NOT NULL,
    src       TEXT NOT NULL,
    dst       TEXT NOT NULL,
    UNIQUE(rel, src, dst)
);
CREATE INDEX IF NOT EXISTS idx_rel_src ON relations(rel, src);
CREATE INDEX IF NOT EXISTS idx_rel_dst ON relations(rel, dst);

CREATE TABLE IF NOT EXISTS import_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    filename   TEXT NOT NULL,
    fact_type  TEXT,
    rows       INTEGER NOT NULL DEFAULT 0,
    inserted   INTEGER NOT NULL DEFAULT 0,
    rejected   INTEGER NOT NULL DEFAULT 0,
    errors     TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class FactStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self.connection() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            conn = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    # ---------- 写入 ----------
    def upsert_entity(self, entity_id: str, class_id: str, label: str,
                      parent_id: str | None = None, attrs: dict[str, Any] | None = None) -> None:
        self.upsert_entities([{"id": entity_id, "class_id": class_id, "label": label,
                               "parent_id": parent_id, "attrs": attrs or {}}])

    def upsert_entities(self, rows: Iterable[dict[str, Any]]) -> int:
        payload = [
            (r["id"], r["class_id"], r["label"], r.get("parent_id"),
             json.dumps(r.get("attrs") or {}, ensure_ascii=False))
            for r in rows
        ]
        if not payload:
            return 0
        with self.connection() as conn:
            conn.executemany(
                """INSERT INTO entities(id, class_id, label, parent_id, attrs)
                   VALUES(?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     class_id=excluded.class_id, label=excluded.label,
                     parent_id=excluded.parent_id, attrs=excluded.attrs""", payload)
        return len(payload)

    def add_fact(self, fact_type: str, subject_id: str, subject_class: str, occurred_at: str,
                 measures: dict[str, Any] | None = None, fields: dict[str, Any] | None = None,
                 source: str = "seed") -> int:
        with self.connection() as conn:
            cur = conn.execute(
                """INSERT INTO facts(fact_type, subject_id, subject_class, occurred_at, measures, fields, source)
                   VALUES(?,?,?,?,?,?,?)""",
                (fact_type, subject_id, subject_class, occurred_at,
                 json.dumps(measures or {}, ensure_ascii=False),
                 json.dumps(fields or {}, ensure_ascii=False), source),
            )
            return int(cur.lastrowid)

    def add_facts(self, rows: Iterable[dict[str, Any]], source: str = "seed") -> int:
        payload = [
            (r["fact_type"], r["subject_id"], r["subject_class"], r["occurred_at"],
             json.dumps(r.get("measures") or {}, ensure_ascii=False),
             json.dumps(r.get("fields") or {}, ensure_ascii=False), r.get("source", source))
            for r in rows
        ]
        if not payload:
            return 0
        with self.connection() as conn:
            conn.executemany(
                """INSERT INTO facts(fact_type, subject_id, subject_class, occurred_at, measures, fields, source)
                   VALUES(?,?,?,?,?,?,?)""", payload)
        return len(payload)

    def add_relations(self, triples: Iterable[tuple[str, str, str]]) -> int:
        payload = list(triples)
        if not payload:
            return 0
        with self.connection() as conn:
            conn.executemany(
                "INSERT OR IGNORE INTO relations(rel, src, dst) VALUES(?,?,?)", payload)
        return len(payload)

    def log_import(self, filename: str, fact_type: str | None, rows: int, inserted: int,
                   rejected: int, errors: list[dict[str, Any]]) -> None:
        with self.connection() as conn:
            conn.execute(
                """INSERT INTO import_log(filename, fact_type, rows, inserted, rejected, errors)
                   VALUES(?,?,?,?,?,?)""",
                (filename, fact_type, rows, inserted, rejected,
                 json.dumps(errors[:50], ensure_ascii=False)),
            )

    def set_setting(self, key: str, value: Any) -> None:
        with self.connection() as conn:
            conn.execute(
                "INSERT INTO settings(key, value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, json.dumps(value, ensure_ascii=False)))

    def get_setting(self, key: str, default: Any = None) -> Any:
        with self.connection() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default

    # ---------- 读取 ----------
    def facts(self, fact_type: str | None = None, start: str | None = None,
              end: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM facts WHERE 1=1"
        params: list[Any] = []
        if fact_type:
            sql += " AND fact_type=?"
            params.append(fact_type)
        if start:
            sql += " AND occurred_at >= ?"
            params.append(start)
        if end:
            sql += " AND occurred_at < ?"
            params.append(end)
        with self.connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [
            {
                "id": r["id"],
                "fact_type": r["fact_type"],
                "subject_id": r["subject_id"],
                "subject_class": r["subject_class"],
                "occurred_at": r["occurred_at"],
                "measures": json.loads(r["measures"]),
                "fields": json.loads(r["fields"]),
                "source": r["source"],
            }
            for r in rows
        ]

    def entities(self) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM entities").fetchall()
        return [
            {"id": r["id"], "class_id": r["class_id"], "label": r["label"],
             "parent_id": r["parent_id"], "attrs": json.loads(r["attrs"])}
            for r in rows
        ]

    def relation_triples(self, rel: str | None = None) -> list[tuple[str, str, str]]:
        sql = "SELECT rel, src, dst FROM relations"
        params: list[Any] = []
        if rel:
            sql += " WHERE rel=?"
            params.append(rel)
        with self.connection() as conn:
            return [(r["rel"], r["src"], r["dst"]) for r in conn.execute(sql, params)]

    def counts(self) -> dict[str, Any]:
        with self.connection() as conn:
            facts = conn.execute("SELECT COUNT(*) c FROM facts").fetchone()["c"]
            entities = conn.execute("SELECT COUNT(*) c FROM entities").fetchone()["c"]
            rels = conn.execute("SELECT COUNT(*) c FROM relations").fetchone()["c"]
            by_type = {r["fact_type"]: r["c"] for r in conn.execute(
                "SELECT fact_type, COUNT(*) c FROM facts GROUP BY fact_type")}
            window = conn.execute(
                "SELECT MIN(occurred_at) lo, MAX(occurred_at) hi FROM facts").fetchone()
        return {"facts": facts, "entities": entities, "relations": rels,
                "byFactType": by_type, "start": window["lo"], "end": window["hi"]}

    def import_logs(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM import_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [
            {"id": r["id"], "filename": r["filename"], "factType": r["fact_type"],
             "rows": r["rows"], "inserted": r["inserted"], "rejected": r["rejected"],
             "errors": json.loads(r["errors"]), "createdAt": r["created_at"]}
            for r in rows
        ]

    def clear(self) -> None:
        with self.connection() as conn:
            for table in ("facts", "entities", "relations", "import_log"):
                conn.execute(f"DELETE FROM {table}")
