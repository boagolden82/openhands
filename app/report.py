"""报告导出：自包含 HTML 报告与 CSV 指标快照。"""
from __future__ import annotations

import csv
import io
from datetime import datetime
from html import escape
from typing import Any


def build_report(ctx, fmt: str, granularity: str, periods: int) -> tuple[bytes, str, str]:
    result = ctx.engine.compute(granularity=granularity, periods=periods)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    if fmt == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["指标ID", "指标名称", "类型", "层级", "数值", "单位", "目标", "方向",
                         "状态", "达成率", "环比%", "负责人", "口径说明"])
        for metric in result["metrics"].values():
            if metric["hidden"]:
                continue
            writer.writerow([
                metric["id"], metric["label"], metric["type"], metric["layer"],
                metric["value"], metric["unit"], metric["target"], metric["direction"],
                metric["status"], metric["attainment"], metric["delta"],
                metric["owner"], metric["description"],
            ])
        return buf.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8", f"rde-metrics-{stamp}.csv"

    insights = ctx.engine.insights(granularity, periods)
    groups = ctx.engine.breakdown("rde_index", "projectGroup", granularity, periods)["items"]
    compare = ctx.engine.compare()
    indicator = next((m for m in result["metrics"].values() if m["indicator"]), None)
    rows = "".join(
        f"<tr><td class='muted'>{escape(m['code'] or '')}</td><td>{escape(m['label'])}</td><td class='num'>{m['value'] if m['value'] is not None else '—'}"
        f"<span class='unit'>{escape(m['unit'])}</span></td>"
        f"<td class='num'>{m['target'] if m['target'] is not None else '—'}</td>"
        f"<td><span class='pill {m['status']}'>{'达标' if m['status'] == 'ok' else '未达标' if m['status'] == 'off' else '无数据'}</span></td>"
        f"<td class='num'>{m['delta'] if m['delta'] is not None else '—'}</td>"
        f"<td class='muted'>{escape(m['owner'])}</td></tr>"
        for m in result["metrics"].values() if not m["hidden"]
    )
    insight_html = "".join(
        f"<li class='{i['level']}'><strong>{escape(i['title'])}</strong><br>{escape(i['detail'])}</li>"
        for i in insights
    )
    group_html = "".join(
        f"<tr><td>{escape(t['member'])}</td><td class='num'>{t['value'] if t['value'] is not None else '—'}</td></tr>"
        for t in groups
    )
    compare_html = "".join(
        f"<tr><td>{escape(i['code'] or '')}</td><td>{escape(i['label'])}</td>"
        f"<td class='num'>{i['base'] if i['base'] is not None else '—'}<span class='unit'>{escape(i['unit'])}</span></td>"
        f"<td class='num'>{i['current'] if i['current'] is not None else '—'}<span class='unit'>{escape(i['unit'])}</span></td>"
        f"<td class='num'>{i['change'] if i['change'] is not None else '—'}</td></tr>"
        for i in compare["items"] if not i.get("hidden")
    )
    html = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>研发效能指标报告 {stamp}</title>
<style>
:root{{--bg:#0f172a;--card:#16213b;--fg:#e8eefc;--muted:#93a2c4;--accent:#4f8cff;--ok:#3ddc97;--off:#ff6b81}}
*{{box-sizing:border-box}}
body{{margin:0;padding:40px;background:var(--bg);color:var(--fg);
font:14px/1.7 "Microsoft YaHei","PingFang SC",system-ui,sans-serif}}
h1{{font-size:26px;margin:0 0 4px}}h2{{font-size:17px;margin:32px 0 12px}}
.sub{{color:var(--muted);margin-bottom:24px}}
.cards{{display:flex;gap:16px;flex-wrap:wrap}}
.card{{background:var(--card);border-radius:14px;padding:18px 22px;min-width:200px;flex:1}}
.card .k{{color:var(--muted);font-size:12px;letter-spacing:.08em;text-transform:uppercase}}
.card .v{{font-size:30px;font-weight:700;margin-top:6px}}
table{{width:100%;border-collapse:collapse;background:var(--card);border-radius:12px;overflow:hidden}}
th,td{{padding:10px 14px;text-align:left;border-bottom:1px solid #223052}}
th{{color:var(--muted);font-size:12px;font-weight:600;letter-spacing:.05em}}
.num{{text-align:right;font-variant-numeric:tabular-nums}}
.unit{{color:var(--muted);font-size:11px;margin-left:3px}}
.pill{{padding:2px 10px;border-radius:999px;font-size:12px}}
.pill.ok{{background:rgba(61,220,151,.16);color:var(--ok)}}
.pill.off{{background:rgba(255,107,129,.16);color:var(--off)}}
.pill.no_data{{background:#223052;color:var(--muted)}}
.muted{{color:var(--muted)}}
ul.insights{{list-style:none;padding:0;display:grid;gap:10px}}
ul.insights li{{background:var(--card);border-left:3px solid var(--accent);padding:12px 16px;border-radius:8px}}
ul.insights li.critical{{border-color:var(--off)}}ul.insights li.warning{{border-color:#ffc85c}}
footer{{margin-top:36px;color:var(--muted);font-size:12px}}
</style></head><body>
<h1>研发效能指标报告</h1>
<div class="sub">本体版本 {escape(ctx.onto.version)} · 统计窗口 {result['window']['start']} ~ {result['window']['end']} ·
粒度 {escape(granularity)} · 生成时间 {stamp}</div>
<div class="cards">
  <div class="card"><div class="k">研发提效指数</div>
    <div class="v">{indicator['value'] if indicator and indicator['value'] is not None else '—'}<span class="unit">分</span></div></div>
  <div class="card"><div class="k">纳入指标</div>
    <div class="v">{sum(1 for m in result['metrics'].values() if not m['hidden'])}</div></div>
  <div class="card"><div class="k">事实总量</div>
    <div class="v">{result['coverage']['facts']}</div></div>
  <div class="card"><div class="k">未达标指标</div>
    <div class="v">{sum(1 for m in result['metrics'].values() if m['status'] == 'off' and not m['hidden'])}</div></div>
</div>
<h2>关键发现</h2>
<ul class="insights">{insight_html or '<li>本期无异常。</li>'}</ul>
<h2>项目组效能对比</h2>
<table><thead><tr><th>项目组</th><th class="num">提效指数</th></tr></thead><tbody>{group_html}</tbody></table>
<h2>同比对比（{escape(compare['base']['start'])} ~ {escape(compare['base']['end'])} vs
{escape(compare['current']['start'])} ~ {escape(compare['current']['end'])}）</h2>
<table><thead><tr><th>编号</th><th>指标</th><th class="num">基期</th>
<th class="num">当期</th><th class="num">变化%</th></tr></thead><tbody>{compare_html}</tbody></table>
<h2>指标明细</h2>
<table><thead><tr><th>编号</th><th>指标</th><th class="num">当前值</th><th class="num">目标</th>
<th>状态</th><th class="num">环比%</th><th>负责人</th></tr></thead><tbody>{rows}</tbody></table>
<footer>由 RDE-Onto 研发效能指标体系自动生成 · 指标口径来源于本体文件 ontology.json，可自行扩展。</footer>
</body></html>"""
    return html.encode("utf-8"), "text/html; charset=utf-8", f"rde-report-{stamp}.html"
