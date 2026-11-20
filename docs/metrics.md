# 指标字典

共 **35** 个指标，口径全部定义于 `ontology/ontology.json`。
本文件由 `scripts/gen_metrics_doc.py` 从本体自动生成，请勿手工编辑。

## 汇总

| 指标 | ID | 类型 | 层级 | 单位 | 目标 | 方向 | 负责人 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 流水线时长 | `ci_duration_minutes` | 派生指标 | 流动效率 | min | 15 | 越低越好 | 工程效能 |
| 需求交付周期 | `cycle_time_hours` | 配对指标 | 流动效率 | h | 72 | 越低越好 | 敏捷教练 |
| 部署频率 | `deploy_frequency` | 原子指标 | 流动效率 | 次/周 | 10 | 越高越好 | 研发效能平台 |
| 交付前置时间 | `lead_time_hours` | 原子指标 | 流动效率 | h | 48 | 越低越好 | 研发效能平台 |
| 评审周期 | `pr_cycle_hours` | 派生指标 | 流动效率 | h | 24 | 越低越好 | 工程效能 |
| 交付吞吐 | `throughput_points` | 原子指标 | 流动效率 | 点/周 | 80 | 越高越好 | 敏捷教练 |
| 人均在制品 | `wip_per_person` | 派生指标 | 流动效率 | 项 | 3 | 越低越好 | 敏捷教练 |
| 变更失败率 | `change_failure_rate` | 派生指标 | 交付质量 | % | 15 | 越低越好 | SRE |
| 流水线成功次数 | `ci_success_count` | 原子指标 | 交付质量 | 次 | 380 | 越高越好 | 工程效能 |
| 流水线成功率 | `ci_success_rate` | 派生指标 | 交付质量 | % | 95 | 越高越好 | 工程效能 |
| 代码返工率 | `code_churn_rate` | 派生指标 | 交付质量 | % | 20 | 越低越好 | 工程效能 |
| 缺陷逃逸率 | `defect_escape_rate` | 派生指标 | 交付质量 | % | 10 | 越低越好 | 质量保障 |
| 逃逸缺陷数 | `defect_escaped` | 原子指标 | 交付质量 | 个 | 4 | 越低越好 | 质量保障 |
| 缺陷总数 | `defect_total` | 原子指标 | 交付质量 | 个 | 40 | 越低越好 | 质量保障 |
| 平均恢复时长 | `mttr_minutes` | 原子指标 | 交付质量 | min | 60 | 越低越好 | SRE |
| 评审覆盖率 | `review_coverage` | 派生指标 | 交付质量 | % | 95 | 越高越好 | 工程效能 |
| 活跃人数 | `active_people` | 原子指标 | 交付过程 | 人 | 10 | 越高越好 | 研发管理部 |
| 交付工作项数 | `delivered_items` | 原子指标 | 交付过程 | 项/周 | 25 | 越高越好 | 研发管理部 |
| 研发效能指数 | `dev_eff_index` | 复合指标 | 交付过程 | 分 | 75 | 越高越好 | 研发管理部 |
| 迭代达成率 | `sprint_completion_rate` | 派生指标 | 交付过程 | % | 90 | 越高越好 | 敏捷教练 |
| 技术债投入占比 | `tech_debt_ratio` | 派生指标 | 交付过程 | % | 15 | 越高越好 | 架构组 |

## 详细口径

### 流动效率

#### 流水线时长

单次流水线平均执行时长，直接影响反馈速度。

| 项 | 值 |
| --- | --- |
| 指标 ID | `ci_duration_minutes` |
| 类型 | 派生指标 |
| 单位 | min |
| 目标值 | 15 |
| 优化方向 | 越低越好 |
| 计算公式 | `Σduration / runs / 60` |
| 依赖指标 | `ci_duration_sec_total`, `ci_total_count` |
| 负责人 | 工程效能 |

#### 需求交付周期

已关闭工作项从创建到关闭的中位耗时。该指标需要把两类事实按同一主体 join，由本体关系驱动，无法从单一事实表直接聚合。

| 项 | 值 |
| --- | --- |
| 指标 ID | `cycle_time_hours` |
| 类型 | 配对指标 |
| 单位 | h |
| 目标值 | 72 |
| 优化方向 | 越低越好 |
| 计算公式 | `median(workitem.closed.occurred_at - workitem.created.occurred_at)` |
| 聚合方式 | `median` |
| 度量字段 | `cycle_hours` |
| 起点事实 | `workitem.created` |
| 终点事实 | `workitem.closed` |
| 负责人 | 敏捷教练 |

#### 部署频率

统计周期内完成的部署次数，按周归一化。

| 项 | 值 |
| --- | --- |
| 指标 ID | `deploy_frequency` |
| 类型 | 原子指标 |
| 单位 | 次/周 |
| 目标值 | 10 |
| 优化方向 | 越高越好 |
| 计算公式 | `count(deployment) / window_weeks` |
| 事实来源 | `deployment.finished` |
| 聚合方式 | `count` |
| 归一化 | 按week归一 |
| 负责人 | 研发效能平台 |

#### 交付前置时间

从需求进入开发到部署完成的中位时长，衡量端到端流动效率。

| 项 | 值 |
| --- | --- |
| 指标 ID | `lead_time_hours` |
| 类型 | 原子指标 |
| 单位 | h |
| 目标值 | 48 |
| 优化方向 | 越低越好 |
| 计算公式 | `median(deployment.lead_time_hours)` |
| 事实来源 | `deployment.finished` |
| 聚合方式 | `avg` |
| 度量字段 | `lead_time_hours` |
| 负责人 | 研发效能平台 |

#### 评审周期

合并请求从创建到合入的平均时长，衡量协作摩擦。

| 项 | 值 |
| --- | --- |
| 指标 ID | `pr_cycle_hours` |
| 类型 | 派生指标 |
| 单位 | h |
| 目标值 | 24 |
| 优化方向 | 越低越好 |
| 计算公式 | `Σ(merged_at - created_at) / merged_count` |
| 依赖指标 | `pr_open_hours_total`, `pr_merged_count` |
| 负责人 | 工程效能 |

#### 交付吞吐

每迭代完成的故事点，按周归一化后得到团队稳定交付速率（组织级口径）。

| 项 | 值 |
| --- | --- |
| 指标 ID | `throughput_points` |
| 类型 | 原子指标 |
| 单位 | 点/周 |
| 目标值 | 80 |
| 优化方向 | 越高越好 |
| 计算公式 | `Σcompleted_points / window_weeks` |
| 事实来源 | `sprint.completed` |
| 聚合方式 | `sum` |
| 度量字段 | `completed_points` |
| 归一化 | 按week归一 |
| 负责人 | 敏捷教练 |

#### 人均在制品

同时进行中的工作项数量除以活跃人数，衡量并行度与切换成本。

| 项 | 值 |
| --- | --- |
| 指标 ID | `wip_per_person` |
| 类型 | 派生指标 |
| 单位 | 项 |
| 目标值 | 3 |
| 优化方向 | 越低越好 |
| 计算公式 | `WIP / active_people` |
| 依赖指标 | `wip_total`, `active_people` |
| 负责人 | 敏捷教练 |

### 交付质量

#### 变更失败率

由部署引发的线上事件占全部部署的比例。

| 项 | 值 |
| --- | --- |
| 指标 ID | `change_failure_rate` |
| 类型 | 派生指标 |
| 单位 | % |
| 目标值 | 15 |
| 优化方向 | 越低越好 |
| 计算公式 | `incidents / deployments × 100%` |
| 依赖指标 | `incident_count`, `deploy_count` |
| 负责人 | SRE |

#### 流水线成功次数

status=success 的流水线运行次数。

| 项 | 值 |
| --- | --- |
| 指标 ID | `ci_success_count` |
| 类型 | 原子指标 |
| 单位 | 次 |
| 目标值 | 380 |
| 优化方向 | 越高越好 |
| 计算公式 | `count(pipeline where status=success)` |
| 事实来源 | `pipeline.completed` |
| 聚合方式 | `count` |
| 过滤条件 | `{"field": "status", "op": "eq", "value": "success"}` |
| 负责人 | 工程效能 |

#### 流水线成功率

CI 流水线执行成功的比例，反映测试与构建的稳定性。

| 项 | 值 |
| --- | --- |
| 指标 ID | `ci_success_rate` |
| 类型 | 派生指标 |
| 单位 | % |
| 目标值 | 95 |
| 优化方向 | 越高越好 |
| 计算公式 | `success_runs / total_runs × 100%` |
| 依赖指标 | `ci_success_count`, `ci_total_count` |
| 负责人 | 工程效能 |

#### 代码返工率

提交后两周内被删除的行数占比，反映返工与需求不稳定。

| 项 | 值 |
| --- | --- |
| 指标 ID | `code_churn_rate` |
| 类型 | 派生指标 |
| 单位 | % |
| 目标值 | 20 |
| 优化方向 | 越低越好 |
| 计算公式 | `churn_lines / changed_lines × 100%` |
| 依赖指标 | `churn_lines`, `lines_changed_total` |
| 负责人 | 工程效能 |

#### 缺陷逃逸率

上线后才被发现的缺陷占全部缺陷的比例。

| 项 | 值 |
| --- | --- |
| 指标 ID | `defect_escape_rate` |
| 类型 | 派生指标 |
| 单位 | % |
| 目标值 | 10 |
| 优化方向 | 越低越好 |
| 计算公式 | `escaped_defects / all_defects × 100%` |
| 依赖指标 | `defect_escaped`, `defect_total` |
| 负责人 | 质量保障 |

#### 逃逸缺陷数

上线后才被发现的缺陷数量。

| 项 | 值 |
| --- | --- |
| 指标 ID | `defect_escaped` |
| 类型 | 原子指标 |
| 单位 | 个 |
| 目标值 | 4 |
| 优化方向 | 越低越好 |
| 计算公式 | `count(workitem.created where subject ⊑ dev:Defect and escaped=true)` |
| 事实来源 | `workitem.created` |
| 聚合方式 | `count` |
| 过滤条件 | `{"all": [{"class": "dev:Defect"}, {"field": "escaped", "op": "eq", "value": true}]}` |
| 负责人 | 质量保障 |

#### 缺陷总数

统计周期内创建的缺陷工作项数量（由本体类归属推理得出，无需依赖 type 字段）。

| 项 | 值 |
| --- | --- |
| 指标 ID | `defect_total` |
| 类型 | 原子指标 |
| 单位 | 个 |
| 目标值 | 40 |
| 优化方向 | 越低越好 |
| 计算公式 | `count(workitem.created where subject ⊑ dev:Defect)` |
| 事实来源 | `workitem.created` |
| 聚合方式 | `count` |
| 过滤条件 | `{"class": "dev:Defect"}` |
| 负责人 | 质量保障 |

#### 平均恢复时长

线上事件从发生到恢复的平均耗时。

| 项 | 值 |
| --- | --- |
| 指标 ID | `mttr_minutes` |
| 类型 | 原子指标 |
| 单位 | min |
| 目标值 | 60 |
| 优化方向 | 越低越好 |
| 计算公式 | `avg(incident.mttr_minutes)` |
| 事实来源 | `incident.resolved` |
| 聚合方式 | `avg` |
| 度量字段 | `mttr_minutes` |
| 负责人 | SRE |

#### 评审覆盖率

合入前至少被一次评审的合并请求比例。

| 项 | 值 |
| --- | --- |
| 指标 ID | `review_coverage` |
| 类型 | 派生指标 |
| 单位 | % |
| 目标值 | 95 |
| 优化方向 | 越高越好 |
| 计算公式 | `reviewed_prs / merged_prs × 100%` |
| 依赖指标 | `pr_with_review_count`, `pr_merged_count` |
| 负责人 | 工程效能 |

### 交付过程

#### 活跃人数

统计周期内产生过提交的人数。

| 项 | 值 |
| --- | --- |
| 指标 ID | `active_people` |
| 类型 | 原子指标 |
| 单位 | 人 |
| 目标值 | 10 |
| 优化方向 | 越高越好 |
| 计算公式 | `count(distinct commit.author)` |
| 事实来源 | `commit.pushed` |
| 聚合方式 | `distinct` |
| 度量字段 | `author` |
| 负责人 | 研发管理部 |

#### 交付工作项数

每周关闭的工作项数量，反映需求消化速度。

| 项 | 值 |
| --- | --- |
| 指标 ID | `delivered_items` |
| 类型 | 原子指标 |
| 单位 | 项/周 |
| 目标值 | 25 |
| 优化方向 | 越高越好 |
| 计算公式 | `count(workitem.closed) / window_weeks` |
| 事实来源 | `workitem.closed` |
| 聚合方式 | `count` |
| 归一化 | 按week归一 |
| 负责人 | 研发管理部 |

#### 研发效能指数

DORA 四指标 + 迭代达成率的加权归一化综合得分。每个分量按『达标即满分』归一化（越低越好者取 goal/value），权重可在本体文件中调整。

| 项 | 值 |
| --- | --- |
| 指标 ID | `dev_eff_index` |
| 类型 | 复合指标 |
| 单位 | 分 |
| 目标值 | 75 |
| 优化方向 | 越高越好 |
| 计算公式 | `Σ wᵢ · norm(metricᵢ, goalᵢ) × 100` |
| 依赖指标 | `lead_time_hours`, `deploy_frequency`, `change_failure_rate`, `mttr_minutes`, `sprint_completion_rate`, `cycle_time_hours` |
| 评分分量 | `lead_time_hours` 权重 0.2（目标 48）；`deploy_frequency` 权重 0.15（目标 10）；`change_failure_rate` 权重 0.2（目标 15）；`mttr_minutes` 权重 0.1（目标 60）；`sprint_completion_rate` 权重 0.15（目标 90）；`cycle_time_hours` 权重 0.2（目标 72） |
| 负责人 | 研发管理部 |

#### 迭代达成率

迭代实际交付与承诺的比例，衡量计划可信度。

| 项 | 值 |
| --- | --- |
| 指标 ID | `sprint_completion_rate` |
| 类型 | 派生指标 |
| 单位 | % |
| 目标值 | 90 |
| 优化方向 | 越高越好 |
| 计算公式 | `completed / committed × 100%` |
| 依赖指标 | `sprint_completed_points`, `sprint_committed_points` |
| 负责人 | 敏捷教练 |

#### 技术债投入占比

技术债故事点占全部需求故事点的比例，用于评估长期健康度投入是否充足。

| 项 | 值 |
| --- | --- |
| 指标 ID | `tech_debt_ratio` |
| 类型 | 派生指标 |
| 单位 | % |
| 目标值 | 15 |
| 优化方向 | 越高越好 |
| 计算公式 | `tech_debt_points / total_story_points × 100%` |
| 依赖指标 | `tech_debt_points`, `total_story_points` |
| 负责人 | 架构组 |

## 内部指标（不作为 KPI 展示）

以下指标作为其他指标的分子/分母存在，只在详情页与血缘图中可见。

| 指标 | ID | 用途 |
| --- | --- | --- |
| 返工行数 | `churn_lines` | 被 `code_churn_rate` 使用 |
| 流水线时长合计 | `ci_duration_sec_total` | 被 `ci_duration_minutes` 使用 |
| 流水线运行次数 | `ci_total_count` | 被 `ci_success_rate`, `ci_duration_minutes` 使用 |
| 部署次数 | `deploy_count` | 被 `change_failure_rate` 使用 |
| 线上事件数 | `incident_count` | 被 `change_failure_rate` 使用 |
| 代码变更行数 | `lines_changed_total` | 被 `code_churn_rate` 使用 |
| 合入合并请求数 | `pr_merged_count` | 被 `pr_cycle_hours`, `review_coverage` 使用 |
| 合并请求滞留时长合计 | `pr_open_hours_total` | 被 `pr_cycle_hours` 使用 |
| 有评审的合并请求数 | `pr_with_review_count` | 被 `review_coverage` 使用 |
| 迭代承诺点数 | `sprint_committed_points` | 被 `sprint_completion_rate` 使用 |
| 迭代完成点数 | `sprint_completed_points` | 被 `sprint_completion_rate` 使用 |
| 技术债点数 | `tech_debt_points` | 被 `tech_debt_ratio` 使用 |
| 需求点数 | `total_story_points` | 被 `tech_debt_ratio` 使用 |
| 在制品数量 | `wip_total` | 被 `wip_per_person` 使用 |
