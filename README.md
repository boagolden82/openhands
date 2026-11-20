# RDE-Onto · 基于本体论的研发提效指标体系

一套可以下载到本地、双击即用的研发效能度量系统。指标不是写死在代码里的 SQL，而是从一份**本体文件**（类、关系、事实、指标口径）推理出来的——换一套口径只改 JSON，不动代码。

- 零第三方依赖：仅用 Python 标准库（`sqlite3` + `http.server`），不需要 pip 装任何包
- 原生支持 Windows：双击 `start.bat` 或 `RDE-Onto.exe` 即用，无需安装 Python（使用发布包时）
- 自带 26 周演示数据，打开就有 35 个指标、5 个团队、4676 条事实可看

---

## 一、Windows 上怎么用

### 方式 A：直接用打包好的 exe（推荐给业务同学）

1. 下载 `RDE-Onto.exe`（或解压 `RDE-Onto-win64.zip`）
2. 双击 `RDE-Onto.exe`（或 `start.bat`）
3. 浏览器自动打开 <http://127.0.0.1:8765>
4. 关闭黑窗口即停止服务

数据保存在 exe 同级的 `data\rde.db`，删掉这个文件即可恢复初始演示数据。

### 方式 B：源码运行（推荐给需要改口径的同学）

需要 Python 3.9+（[下载](https://www.python.org/downloads/windows/)，安装时勾选 **Add Python to PATH**）。

```bat
git clone https://github.com/boagolden82/openhands.git
cd openhands
start.bat
```

或手动：

```bat
python -m app
```

### 方式 C：自己打包成 exe

```bat
build_exe.bat
```

产物在 `dist\RDE-Onto.exe`，`dist\RDE-Onto-win64\` 是可直接分发的目录（含 exe、启动脚本、文档）。

> GitHub Actions 也会在每次推送时自动在 `windows-latest` 上打包，到 **Actions → Windows Build → Artifacts** 下载 `RDE-Onto-win64`。

---

## 二、启动参数

| 参数 | 说明 |
| --- | --- |
| `--port 8080` | 指定端口（默认 8765） |
| `--host 0.0.0.0` | 允许局域网访问（默认仅本机） |
| `--no-browser` | 启动后不自动打开浏览器 |
| `--reseed` | 启动前重建演示数据 |
| `--version` / `--help` | 版本 / 帮助 |

也可用环境变量：`RDE_PORT`、`RDE_HOST`、`RDE_DATA_DIR`、`RDE_DB`、`RDE_ONTOLOGY`、`RDE_NO_BROWSER`。

---

## 三、为什么要"基于本体"

传统做法：每个指标一条 SQL，口径散落在代码、文档、Excel 里，改口径要改代码、发版本，而且没人说得清"这个数是怎么来的"。

本系统把度量知识抽成四层本体：

```
类（Class）        研发域里有哪些东西：组织、团队、项目、代码库、迭代、需求、缺陷、提交、部署、事件……
关系（Relation）    它们怎么连：隶属于（传递）、归属团队、属于迭代、实现、部署、由…引起……
事实（FactType）    发生过什么：workitem.created、commit.pushed、deployment.finished……
指标（Metric）      怎么算：原子（直接聚合事实）/ 派生（公式）/ 配对（双事实 join）/ 复合（加权评分）
```

指标计算全部由本体驱动，代码里没有一处硬编码的指标逻辑：

| 能力 | 本体里的表达 | 效果 |
| --- | --- | --- |
| 子类推理 | `dev:Story ⊑ dev:Requirement ⊑ dev:WorkItem ⊑ core:Artifact ⊑ core:Entity` | 写 `filter: {class: "dev:Defect"}` 就能统计所有缺陷子类，不用维护 `type='bug'` 这类字符串 |
| 传递关系 | `belongsTo` 标记 `transitive: true` | 事实只记录 `repo`，团队/项目维度靠 `repo → project → team → org` 推理出来，不需要宽表打平 |
| 依赖闭包 | 指标 `deps` 自动拓扑排序 | 派生指标按依赖顺序求值，且能检测循环依赖 |
| 配对事实 | `type: "pair"` + `startFact`/`endFact` | 需求交付周期 = `workitem.closed` 时间 − `workitem.created` 时间，跨两类事实按主体 join |
| 加权评分 | `scoring.components[].weight/goal/scale` | 研发效能指数的权重、目标值都是数据，可解释、可调 |
| 一致性校验 | 事实的 `subject_class` 必须是事实类型声明主体的子类 | CSV 导入时直接拒绝"用提交类承载工作项事实"这类脏数据 |

改一个指标口径的完整流程：编辑 `ontology/ontology.json` → 重启服务。不用改 Python、不用改前端。

---

## 四、功能地图

| 页面 | 内容 |
| --- | --- |
| **效能总览** | 研发效能指数环形仪表 + 走势、17 张 KPI 卡（含迷你走势与环比）、核心指标趋势图（带目标线）、团队效能横向对比、自动洞察、指标达标矩阵 |
| **指标字典** | 35 个指标的可搜索清单，点开看口径公式、目标、达成率、依赖关系、趋势图，以及按团队 / 代码库 / 工作类型的下钻 |
| **指标血缘** | 从北极星指标出发的分层血缘图，依赖在左、派生在右，点击节点跳到指标详情 |
| **本体模型** | 类层次树（27 类）、关系定义（20 个，标注传递性与逆关系）、事实类型（11 种），点任一节点看它与哪些关系、事实、指标相连 |
| **数据接入** | 拖拽 CSV 导入（本体校验 + 逐行错误报告）、按事实类型下载模板、数据质量体检、事实浏览器 |
| **分析预测** | 蒙特卡洛交付预测（P50/P85/P95）、按影响度排序的改进建议、10×10 指标相关性热力图 |

其他：深/浅色主题切换、周/月/日粒度、近 8/12/26 期窗口、团队筛选、一键导出 HTML/CSV 报告。

---

## 五、数据接入（对接你公司自己的系统）

### 1. 下载模板

数据接入页选一个事实类型 → 点"下载模板"，得到该类型的标准表头。例如 `deployment.finished`：

```csv
fact_type,subject_id,subject_class,finished_at,measure:duration_sec,field:env,field:repo,field:status,field:lead_time_hours
```

### 2. 从你的系统导出并映射

| 事实类型 | 常见来源 |
| --- | --- |
| `workitem.created` / `workitem.closed` | Jira、禅道、TAPD、飞书项目 |
| `commit.pushed` / `pr.merged` / `review.submitted` | GitLab、GitHub、Bitbucket、Gerrit |
| `pipeline.completed` | Jenkins、GitLab CI、GitHub Actions |
| `deployment.finished` | Argo CD、Spinnaker、自建发布平台 |
| `incident.resolved` | PagerDuty、Opsgenie、自建告警平台 |
| `sprint.completed` | Jira、Azure DevOps |

关键点：`repo` 字段要填**已注册的代码库实体 id**（如 `repo:pay-core`），维度上卷（团队/项目）靠它推理。若要新增团队或代码库，先通过 API 或直接改 `data/rde.db` 的 `entities` 表注册实体。

### 3. 导入

拖到上传区即可。系统会逐行校验并给出报告：

- ✅ 通过：主体类合法、时间是可解析格式
- ❌ 拒绝：未知事实类型、主体类不是声明主体的子类（违反本体约束）、时间无法解析、缺少主体 id

导入结果会记入 `import_log` 表，可在页面上查看历史。

### 4. 用 API 自动化

```bash
# 事实列表（可按类型过滤）
curl "http://127.0.0.1:8765/api/facts?factType=deployment.finished&limit=20"

# 指标计算（可传 start/end/granularity/team）
curl "http://127.0.0.1:8765/api/overview?granularity=week&periods=12"

# 单个指标 + 下钻
curl "http://127.0.0.1:8765/api/metrics/lead_time_hours?granularity=month"

# 导出报告
curl -o report.html "http://127.0.0.1:8765/api/report?format=html"
curl -o metrics.csv  "http://127.0.0.1:8765/api/report?format=csv"
```

完整接口清单见 [docs/architecture.md](docs/architecture.md)。

---

## 六、指标清单

35 个指标分 4 层。完整口径（公式、目标、负责人、计算方式）见 [docs/metrics.md](docs/metrics.md)。

| 层级 | 指标 |
| --- | --- |
| **流动效率** | 交付前置时间、需求交付周期、部署频率、评审周期、流水线时长、交付吞吐 |
| **交付质量** | 变更失败率、平均恢复时长、流水线成功率、缺陷逃逸率、代码返工率、评审覆盖率、线上事件数 |
| **交付过程** | 迭代达成率、人均在制品、技术债投入占比、交付工作项数、活跃人数 |
| **北极星** | 研发效能指数（6 项加权，权重可调） |

---

## 七、目录结构

```
.
├── app/
│   ├── ontology.py     本体加载、子类闭包、传递关系、依赖拓扑
│   ├── store.py        SQLite 事实存储（entities / facts / relations / import_log）
│   ├── metrics.py      指标引擎：维度富化 → 原子聚合 → 派生求值 → 复合评分
│   ├── importer.py     CSV 导入与本体校验
│   ├── report.py       HTML / CSV 报告生成
│   ├── server.py       HTTP 服务与 JSON API（标准库）
│   ├── seed.py         确定性演示数据
│   ├── config.py       路径与端口配置
│   └── web/            前端（原生 JS + 自绘 SVG，无 CDN 依赖）
├── ontology/ontology.json   本体定义：27 类 / 20 关系 / 11 事实 / 35 指标
├── tests/              46 个单元与集成测试
├── docs/               架构说明、指标字典
├── start.bat           Windows 一键启动
├── build_exe.bat       Windows 打包脚本
├── rde_onto.spec       PyInstaller 配置
└── run.py              打包入口
```

---

## 八、开发

```bash
pip install pytest
python -m pytest tests/ -q      # 46 passed
```

代码约定：

- 指标口径只写在 `ontology/ontology.json`，Python 代码里不出现指标常量
- 表达式求值走 AST 白名单（`app/metrics.py::safe_eval`），只允许四则运算、幂和白名单函数，禁止属性访问与函数调用逃逸
- 事实的 `subject_class` 必须通过 `is_subclass` 校验，脏数据在入库前被拒绝

---

## 九、常见问题

**Q：双击 `start.bat` 一闪而过？**
A：目录里既没有 `RDE-Onto.exe` 也没装 Python。装 Python 时务必勾选 "Add Python to PATH"，或直接使用发布包里的 exe。

**Q：端口 8765 被占用？**
A：`start.bat --port 8888`，或 `python -m app --port 8888`。

**Q：想让同事访问我的数据？**
A：`python -m app --host 0.0.0.0`，然后用 `http://你的IP:8765` 访问。注意当前版本没有登录鉴权，只在可信内网使用。

**Q：数据存在哪？**
A：`data/rde.db`（SQLite）。备份就复制这个文件；想重置就删掉它再启动。

**Q：怎么加一个新指标？**
A：在 `ontology/ontology.json` 的 `metrics` 数组里加一条。原子指标给 `fact`+`agg`+`measure`，派生指标给 `expr`+`deps`。重启服务即可在页面看到。

---

## 许可

MIT

