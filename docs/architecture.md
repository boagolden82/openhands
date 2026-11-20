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
| `id` | 实体标识，如 `group:pay`、`project:pay-core` |
| `class_id` | 本体类，如 `dev:ProjectGroup` |
| `parent_id` | 上级实体，构成 `belongsTo` 层级链 |
| `attrs` | 扩展属性（JSON） |

层级链是维度上卷的基础：一条事实只记录 `project:pay-core`，项目组维度通过
`project:pay-core → group:pay → center:rd` 的父链推理得到。

### facts — 事实（单一宽表）

| 列 | 说明 |
| --- | --- |
| `fact_type` | 事实类型，对应本体 `factTypes[].id` |
| `subject_id` | 主体实体 id |
| `subject_class` | 主体所属类，入库前校验必须 ⊑ 事实类型声明的 `subject` |
| `occurred_at` | 事实发生时间，用于时间窗与分桶 |
| `measures` | 度量值（JSON），如 `{"ai_lines": 320, "total_lines": 900}` |
| `fields` | 描述性字段（JSON），如 `{"project": "project:pay-core", "priority": "P1"}` |
| `source` | 数据来源：`seed` 或 `import:<filename>` |

所有事实共用一张表：新增事实类型只需改本体 JSON，不需要 DDL 变更。

### relations — 关系三元组

`(rel, src, dst)`，例如 `("belongsTo", "project:pay-core", "group:pay")`。
传递关系（`belongsTo`）在查询时求闭包，不预存冗余边。

### import_log — 导入审计

记录每次导入的文件名、行数、入库数、拒绝数与前 50 条错误明细。

## 3. 指标计算流水线

```
① 事实加载           store.facts() + entities() + relations()
② 维度富化           resolve_dims()：为每条事实推理出 center/projectGroup/project/phase/priority/source
③ 原子聚合           _atomic_values()：按 filter + agg + measure 聚合，产出 total + series
④ 派生求值           _resolve_all()：按依赖拓扑序求值 safe_eval(expr)
⑤ 复合评分           _eval_metric()：加权归一化到 0-100
⑥ 展示整形           _present()：环比、达标状态、达成率
```

### 维度富化

```python
# 事实只带 project 字段 → 沿实体父链推理出项目组与研发中心
project_id = fields["project"]                            # project:pay-core
dims["project"]      = entities[project_id].label         # 支付核心
dims["projectGroup"] = chain_dim(project_id, "dev:ProjectGroup")  # 支付研发组
dims["center"]       = chain_dim(project_id, "dev:Center")        # 研发中心
```

阶段维度不做字段读取，而是走本体推理：

```python
phase = fact_type.phase    # mr.dev.done → "开发"
```

因此即便上游系统把阶段叫 `coding`、`dev`、`开发中`，只要事实类型在本体里声明了
`phase`，阶段维度的下钻就自动正确。

`DIM_KEYS` 是维度富化的白名单：

```python
DIM_KEYS = ("center", "projectGroup", "project", "phase", "priority", "source")
```

不在白名单里的字段只作为描述性属性，不参与维度上卷。

### 四类指标

| 类型 | 定义方式 | 例子 |
| --- | --- | --- |
| `atomic` | `fact` + `agg` + `measure` + 可选 `filter` | `headcount_center = snapshot(headcount.snapshot.center_headcount)` |
| `pair` | `startFact` + `endFact` + `joinOn` | `mr_dev_cycle = median(mr.dev.done − mr.analysis.done)` |
| `derived` | `expr` + `deps` | `mr_impl_per_capita = mr_impl_count / headcount_center / months` |
| `composite` | `scoring.components[]`（weight/goal/scale） | `rde_index` |

`agg` 支持：`count`、`distinct`、`sum`、`avg`、`median`、`min`、`max`、`p90`、`last`、`snapshot`。

`snapshot` 用于人力这类"时点存量"数据，与流量型聚合的区别：

1. 每个主体（项目组）在窗口内取**最新**一次快照，而不是把所有月份相加；
2. 再把各主体的值按 `snapshotMode` 合并：`sum`（人数）或 `mean`（比率，如折算系数）；
3. 最后跨时间桶取平均，得到"窗口内的平均在册人力"。

若把比率型度量也求和，5 个项目组的 0.7 折算系数会变成 3.5，折算人均会被放大约 5 倍——
这是本项目修复过的真实缺陷。

`filter` 支持三种谓词，可嵌套：

```json
{"class": "dev:Defect"}                                   // 子类推理
{"field": "status", "op": "eq", "value": "success"}        // 字段比较
{"all": [{"class": "dev:Defect"}, {"field": "escaped", "op": "eq", "value": true}]}
```

操作符：`eq`、`ne`、`in`、`gt`、`lt`、`exists`。

### 时间归一化

`normalize: {"per": "week"}` 的指标会把窗口总量除以窗口周数，并把每个时间桶的值
除以桶周数，使不同粒度下可比。人均类指标则用 `months` 变量（`MONTH_DAYS = 30.44`）
把窗口天数换算成月数，保证"个/人月"的口径与窗口长度无关。

### 稀疏数据填充

RR 按月产生，切换到周粒度时会出现空洞。`carry` 会把上一个有效值结转到空桶，
最多沿用有限个周期，避免趋势线断裂；超出则留空，不臆造数据。

### 同比对比

`compare(base, current)` 用两个区间各算一遍全部对外指标，再按 `direction` 判断
变化是向好还是恶化：

```python
change = (current - base) / base * 100
```

默认区间是数据跨度上的自然年：基期取数据起始年到该年末，当期取最近一年到数据
最新日期。2.3「实时人均实现数」直接复用它，前端同比表也来自同一个方法。

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
| GET | `/api/overview` | 总览：北极星指标、KPI 列表、洞察、项目组对比、同比、覆盖度 |
| GET | `/api/compare` | 双区间同比（`baseStart/baseEnd/currentStart/currentEnd`） |
| GET | `/api/metrics` | 指标元数据清单 + 维度定义 |
| GET | `/api/metrics/{id}` | 单指标：数值、趋势、依赖、按项目组/项目/阶段下钻 |
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

通用查询参数：`granularity`（`day`/`week`/`month`/`year`）、`periods`、`start`、`end`，
以及 `center`/`projectGroup`/`project`/`phase`/`priority`/`source` 维度过滤
（即 `DIM_KEYS` 白名单）。

## 6. 扩展指南

### 新增一个指标

以"MR 返工率"为例，先在本体里补两个原子指标，再声明派生口径：

```json
{
  "id": "mr_rework_count",
  "label": "返工MR数",
  "unit": "个",
  "type": "atomic",
  "layer": "base",
  "fact": "mr.accepted",
  "agg": "count",
  "measure": null,
  "filter": {"field": "rework", "op": "eq", "value": true},
  "hidden": true,
  "description": "验收后被判定需要返工的 MR 数。"
}
```

```json
{
  "id": "mr_rework_rate",
  "code": "2.13",
  "label": "MR返工率",
  "unit": "%",
  "type": "derived",
  "layer": "detail",
  "expr": "mr_rework_count / mr_accepted_count * 100",
  "deps": ["mr_rework_count", "mr_accepted_count"],
  "direction": "down",
  "target": 10,
  "precision": 1,
  "description": "验收后返工的 MR 占比。",
  "formula": "返工数 ÷ 验收数 × 100%",
  "owner": "质量保障",
  "indicator": true
}
```

重启服务，新指标自动出现在总览、字典页、同比表与血缘图里。
`code` 字段是给业务方对账用的编号，与需求清单一一对应。

若该指标要进入北极星指数，再把它加进 `rde_index` 的
`scoring.components` 与 `deps`——两处的依赖集合必须一致，否则本体加载会报错。

### 新增一个事实类型

1. 在 `factTypes` 里声明 `id`、`subject`（必须已存在的类）、`timeField`、`measures`、`fields`
2. 在 `seed.py` 里产生示例数据（可选）
3. 数据接入页就能下载该类型的模板并导入

### 新增一个实体层级

写入 `entities` 表即可，父链自动参与维度上卷：

```python
store.upsert_entity("group:new", "dev:ProjectGroup", "新项目组", "center:rd")
store.upsert_entity("project:new", "dev:Project", "新项目", "group:new")
store.add_relations([("belongsTo", "group:new", "center:rd"),
                     ("belongsTo", "project:new", "group:new")])
```

父链写入 `entities.parent_id` 即可，`belongsTo` 的传递闭包会自动把它接到维度上。
