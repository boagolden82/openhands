# 架构说明

## 1. 分层结构

```
┌─────────────────────────────────────────────────────┐
│  前端 SPA（app/web）  原生 JS + 自绘 SVG，无 CDN 依赖   │
└────────────────────────┬────────────────────────────┘
                         │ JSON / HTTP
┌────────────────────────▼────────────────────────────┐
│  API 层（app/server.py）  ThreadingHTTPServer + 路由表  │
├─────────────────────────────────────────────────────┤
│  指标引擎（app/metrics.py）                            │
│    维度富化 → 原子聚合 → 派生求值 → 复合评分 → 洞察      │
├─────────────────────────────────────────────────────┤
│  本体层（app/ontology.py）                             │
│    子类闭包 / 传递关系 / 依赖拓扑 / 校验                │
├─────────────────────────────────────────────────────┤
│  存储层（app/store.py）  SQLite                        │
│    entities · facts · relations · import_log          │
└─────────────────────────────────────────────────────┘
                         ▲
              ontology/ontology.json（唯一口径来源）
```

## 2. 数据模型

### entities — 实体与层级

| 列 | 说明 |
| --- | --- |
| `id` | 实体标识，如 `team:pay`、`repo:pay-core` |
| `class_id` | 本体类，如 `dev:Team` |
| `parent_id` | 上级实体，构成 `belongsTo` 层级链 |
| `attrs` | 扩展属性（JSON） |

层级链是维度上卷的基础：一条事实只记录 `repo:pay-core`，团队维度通过
`repo:pay-core → project:pay → team:pay → org:tech` 的父链推理得到。

### facts — 事实（单一宽表）

| 列 | 说明 |
| --- | --- |
| `fact_type` | 事实类型，对应本体 `factTypes[].id` |
| `subject_id` | 主体实体 id |
| `subject_class` | 主体所属类，入库前校验必须 ⊑ 事实类型声明的 `subject` |
| `occurred_at` | 事实发生时间，用于时间窗与分桶 |
| `measures` | 度量值（JSON），如 `{"lead_time_hours": 48.5}` |
| `fields` | 描述性字段（JSON），如 `{"env": "prod", "repo": "repo:pay-core"}` |
| `source` | 数据来源：`seed` 或 `import:<filename>` |

所有事实共用一张表：新增事实类型只需改本体 JSON，不需要 DDL 变更。

### relations — 关系三元组

`(rel, src, dst)`，例如 `("inSprint", "wi:pay-1-0", "sprint:pay-03")`。
传递关系（`belongsTo`、`dependsOn`）在查询时求闭包，不预存冗余边。

### import_log — 导入审计

记录每次导入的文件名、行数、入库数、拒绝数与前 50 条错误明细。

## 3. 指标计算流水线

```
① 事实加载           store.facts() + entities() + relations()
② 维度富化           resolve_dims()：为每条事实推理出 team/project/repo/sprint/env/worktype
③ 原子聚合           _atomic_values()：按 filter + agg + measure 聚合，产出 total + series
④ 派生求值           _resolve_all()：按依赖拓扑序求值 safe_eval(expr)
⑤ 复合评分           _eval_metric()：加权归一化到 0-100
⑥ 展示整形           _present()：环比、达标状态、达成率
```

### 维度富化

```python
# 事实只带 repo 字段 → 沿实体父链推理出项目与团队
repo_id = fields["repo"]                        # repo:pay-core
dims["repo"]    = entities[repo_id].label       # pay-core
dims["project"] = chain_dim(repo_id, "dev:Project")   # 支付平台
dims["team"]    = chain_dim(repo_id, "dev:Team")      # 支付中台
```

工作类型不做字段读取，而是走本体推理：

```python
worktype = onto.worktype_of(fact["subject_class"])  # dev:Defect → "缺陷"
```

因此即便上游系统把缺陷叫 `bug`、`defect`、`线上问题`，只要主体类挂到
`dev:Defect` 下，指标口径就自动正确。

### 四类指标

| 类型 | 定义方式 | 例子 |
| --- | --- | --- |
| `atomic` | `fact` + `agg` + `measure` + 可选 `filter` | `mttr_minutes = avg(incident.resolved.mttr_minutes)` |
| `pair` | `startFact` + `endFact` + `joinOn` | `cycle_time_hours = median(closed_at − created_at)` |
| `derived` | `expr` + `deps` | `change_failure_rate = incident_count / deploy_count * 100` |
| `composite` | `scoring.components[]`（weight/goal/scale） | `dev_eff_index` |

`agg` 支持：`count`、`distinct`、`sum`、`avg`、`median`、`min`、`max`、`p90`。

`filter` 支持三种谓词，可嵌套：

```json
{"class": "dev:Defect"}                                   // 子类推理
{"field": "status", "op": "eq", "value": "success"}        // 字段比较
{"all": [{"class": "dev:Defect"}, {"field": "escaped", "op": "eq", "value": true}]}
```

操作符：`eq`、`ne`、`in`、`gt`、`lt`、`exists`。

### 时间归一化

`normalize: {"per": "week"}` 的指标（部署频率、交付吞吐、交付工作项数）会把
窗口总量除以窗口周数，并把每个时间桶的值除以桶周数，使不同粒度下可比。

### 稀疏数据填充

双周迭代等稀疏事实会导致时间桶出现空洞。`_forward_fill` 最多沿用一个周期
的值（`limit=2`），避免趋势线断裂；超出则留空，不臆造数据。

## 4. 安全设计

| 风险 | 处置 |
| --- | --- |
| 指标公式代码注入 | `safe_eval` 用 AST 白名单：只允许 `BinOp`/`UnaryOp`/`Constant`/`Name`/`Call`（白名单函数 `min/max/abs/round/sqrt`），拒绝属性访问、下标、lambda、导入 |
| 路径穿越 | 静态文件请求先 `resolve()` 再校验是否位于 `web/` 根目录内，否则回落到 `index.html` |
| 脏数据入库 | 事实 `subject_class` 必须 ⊑ 事实类型声明主体，否则整行拒绝并记录原因 |
| 负值度量 | 数据质量检查标记 `high`，负值会污染均值类指标 |
| 表达式除零 | `ZeroDivisionError` 捕获后返回 `None`，指标显示"—"而不是崩溃 |
| SQL 注入 | 全部查询使用参数化占位符 |

> 当前版本没有身份认证，默认只监听 `127.0.0.1`。若用 `--host 0.0.0.0` 暴露到
> 局域网，请自行在反向代理层加认证。

## 5. API 一览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 健康检查 + 事实/实体计数 |
| GET | `/api/overview` | 总览：北极星指标、KPI 列表、洞察、团队对比、覆盖度 |
| GET | `/api/metrics` | 指标元数据清单 + 维度定义 |
| GET | `/api/metrics/{id}` | 单指标：数值、趋势、依赖、下钻 |
| GET | `/api/ontology` | 完整本体（类/关系/事实/指标/统计） |
| GET | `/api/lineage?metric=` | 指标血缘子图 |
| GET | `/api/quality` | 数据质量体检报告 |
| GET | `/api/facts?factType=&limit=&offset=` | 事实浏览 |
| GET | `/api/import/template?factType=` | 下载 CSV 模板 |
| POST | `/api/import` | 导入 CSV（`{filename, content(base64), factType?, dryRun?}`） |
| GET | `/api/import/logs` | 导入历史 |
| POST | `/api/forecast` | 蒙特卡洛交付预测 |
| GET | `/api/report?format=html\|csv` | 导出报告 |
| POST | `/api/reseed` | 重建演示数据 |
| GET | `/api/settings` | 数据目录、本体版本等运行信息 |

通用查询参数：`granularity`（`day`/`week`/`month`）、`periods`、`start`、`end`、
`team`/`repo`/`worktype` 等维度过滤。

## 6. 扩展指南

### 新增一个原子指标

```json
{
  "id": "rollback_rate",
  "label": "回滚率",
  "unit": "%",
  "type": "derived",
  "layer": "quality",
  "expr": "rollback_count / deploy_count * 100",
  "deps": ["rollback_count", "deploy_count"],
  "direction": "down",
  "target": 5,
  "precision": 1,
  "description": "因问题回滚的部署占比。",
  "formula": "rollbacks / deployments × 100%",
  "owner": "SRE",
  "primary": true
}
```

同时补上 `rollback_count` 原子指标：

```json
{
  "id": "rollback_count", "label": "回滚次数", "unit": "次",
  "type": "atomic", "layer": "quality",
  "fact": "deployment.finished", "agg": "count", "measure": null,
  "filter": {"field": "status", "op": "eq", "value": "rolled_back"},
  "hidden": true, "direction": "down", "target": 2, "precision": 0
}
```

重启服务，新指标自动出现在总览与字典页，血缘图也会自动接上。

### 新增一个事实类型

1. 在 `factTypes` 里声明 `id`、`subject`（必须已存在的类）、`timeField`、`measures`、`fields`
2. 在 `seed.py` 里产生示例数据（可选）
3. 数据接入页就能下载该类型的模板并导入

### 新增一个实体层级

写入 `entities` 表即可，父链自动参与维度上卷：

```python
store.upsert_entity("team:new", "dev:Team", "新团队", "org:tech")
store.upsert_entity("project:new", "dev:Project", "新项目", "team:new")
store.upsert_entity("repo:new", "dev:Repository", "new-repo", "project:new")
store.add_relations([("belongsTo", "team:new", "org:tech")])
```
