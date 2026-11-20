"""从 ontology.json 生成 docs/metrics.md，保证文档与口径一致。

用法：python scripts/gen_metrics_doc.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LAYER_CN = {"detail": "指标明细", "process": "过程指标", "base": "内部口径"}
TYPE_CN = {"atomic": "原子指标", "derived": "派生指标", "composite": "复合指标", "pair": "配对指标"}
ORDER = ["detail", "process", "base"]


def code_key(metric: dict) -> tuple:
    """按需求清单编号排序：2.0.1 → 2.1 → 2.10 → 3.1。"""
    code = (metric.get("code") or "").split(" / ")[0]
    parts = []
    for chunk in code.split("."):
        parts.append(int(chunk) if chunk.isdigit() else 99)
    return (parts, metric["id"])


def direction_cn(metric: dict) -> str:
    return "越高越好" if metric.get("direction") == "up" else "越低越好"


def main() -> int:
    ontology = json.loads((ROOT / "ontology" / "ontology.json").read_text(encoding="utf-8"))
    metrics = ontology["metrics"]
    visible = [m for m in metrics if not m.get("hidden")]
    hidden = [m for m in metrics if m.get("hidden")]
    layer_rank = {layer: i for i, layer in enumerate(ORDER)}

    lines = [
        "# 指标字典",
        "",
        f"共 **{len(metrics)}** 个指标，口径全部定义于 `ontology/ontology.json`。",
        "本文件由 `scripts/gen_metrics_doc.py` 从本体自动生成，请勿手工编辑。",
        "",
        "## 汇总",
        "",
        "| 编号 | 指标 | ID | 类型 | 单位 | 目标 | 方向 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for metric in sorted(visible, key=lambda m: (layer_rank.get(m.get("layer"), 9), code_key(m))):
        lines.append(
            f"| {metric.get('code') or '—'} | {metric['label']} | `{metric['id']}` | "
            f"{TYPE_CN.get(metric['type'], metric['type'])} | "
            f"{metric.get('unit', '')} | {metric.get('target', '—')} | {direction_cn(metric)} |"
        )

    lines += ["", "## 详细口径", ""]
    for layer in ORDER:
        items = [m for m in visible if m.get("layer") == layer]
        if not items:
            continue
        lines += [f"### {LAYER_CN[layer]}", ""]
        for metric in sorted(items, key=code_key):
            title = f"{metric['code']} {metric['label']}" if metric.get("code") else metric["label"]
            lines += [f"#### {title}", "", metric.get("description", ""), "",
                      "| 项 | 值 |", "| --- | --- |",
                      f"| 指标编号 | {metric.get('code') or '—'} |",
                      f"| 指标 ID | `{metric['id']}` |",
                      f"| 类型 | {TYPE_CN.get(metric['type'], metric['type'])} |",
                      f"| 单位 | {metric.get('unit', '—')} |",
                      f"| 目标值 | {metric.get('target', '—')} |",
                      f"| 优化方向 | {direction_cn(metric)} |",
                      f"| 计算公式 | `{metric.get('formula', '—')}` |"]
            for key, label in (("fact", "事实来源"), ("agg", "聚合方式"), ("measure", "度量字段"),
                               ("startFact", "起点事实"), ("endFact", "终点事实")):
                if metric.get(key):
                    lines.append(f"| {label} | `{metric[key]}` |")
            if metric.get("filter"):
                lines.append(f"| 过滤条件 | `{json.dumps(metric['filter'], ensure_ascii=False)}` |")
            if metric.get("normalize"):
                lines.append(f"| 归一化 | 按{metric['normalize']['per']}归一 |")
            if metric.get("deps"):
                lines.append(f"| 依赖指标 | {', '.join(f'`{d}`' for d in metric['deps'])} |")
            if metric.get("scoring"):
                detail = "；".join(
                    f"`{c['dep']}` 权重 {c['weight']}（目标 {c['goal']}）"
                    for c in metric["scoring"]["components"]
                )
                lines.append(f"| 评分分量 | {detail} |")
            lines += [f"| 负责人 | {metric.get('owner', '—')} |", ""]

    if hidden:
        lines += ["## 内部口径指标（不作为 KPI 展示）", "",
                  "以下指标作为其他指标的分子/分母存在，只在详情页与血缘图中可见。", "",
                  "| 指标 | ID | 用途 |", "| --- | --- | --- |"]
        for metric in sorted(hidden, key=lambda m: m["id"]):
            users = [m["id"] for m in metrics if metric["id"] in m.get("deps", [])]
            used_by = ", ".join(f"`{u}`" for u in users) or "内部计算"
            lines.append(f"| {metric['label']} | `{metric['id']}` | 被 {used_by} 使用 |")
        lines.append("")

    (ROOT / "docs" / "metrics.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"docs/metrics.md: {len(visible)} 个展示指标 + {len(hidden)} 个内部指标")
    return 0


if __name__ == "__main__":
    sys.exit(main())
