# 指标字典

共 **44** 个指标，口径全部定义于 `ontology/ontology.json`。
本文件由 `scripts/gen_metrics_doc.py` 从本体自动生成，请勿手工编辑。

## 汇总

| 编号 | 指标 | ID | 类型 | 单位 | 目标 | 方向 |
| --- | --- | --- | --- | --- | --- | --- |
| 2.0.1 / 2.5 | MR实现周期 | `mr_impl_cycle` | 配对指标 | h | 120 | 越低越好 |
| 2.0.2 | RR按期达成率 | `rr_on_time_rate` | 派生指标 | % | 90 | 越高越好 |
| 2.1 | MR研发人均交付数 | `mr_delivery_per_capita` | 派生指标 | 个/人月 | 1.2 | 越高越好 |
| 2.2 | MR研发人均实现数 | `mr_impl_per_capita` | 派生指标 | 个/人月 | 1.6 | 越高越好 |
| 2.3 | MR研发人均实现数（实时） | `mr_impl_per_capita_live` | 派生指标 | 个/人月 | 1.6 | 越高越好 |
| 2.4 | MR研发人均实现数（中心+外包折算） | `mr_impl_per_capita_converted` | 派生指标 | 个/人月 | 1.4 | 越高越好 |
| 2.7 | MR人均分析吞吐率 | `mr_analysis_throughput` | 派生指标 | 个/人月 | 1.8 | 越高越好 |
| 2.8 | MR分析周期 | `mr_analysis_cycle` | 配对指标 | h | 48 | 越低越好 |
| 2.9 | MR人均开发吞吐率 | `mr_dev_throughput` | 派生指标 | 个/人月 | 1.6 | 越高越好 |
| 2.10 | MR开发周期 | `mr_dev_cycle` | 配对指标 | h | 72 | 越低越好 |
| 2.11 | MR人均测试吞吐率 | `mr_test_throughput` | 派生指标 | 个/人月 | 1.7 | 越高越好 |
| 2.12 | MR验收周期 | `mr_accept_cycle` | 配对指标 | h | 24 | 越低越好 |
| 3.1 | 需求分析生成率 | `analysis_gen_rate` | 派生指标 | % | 60 | 越高越好 |
| 3.2 | 需求方案生成率 | `solution_gen_rate` | 派生指标 | % | 55 | 越高越好 |
| 3.3 | 代码生成率 | `code_gen_rate` | 派生指标 | % | 45 | 越高越好 |
| 3.4 | AI测试用例生成率 | `ai_testcase_gen_rate` | 派生指标 | % | 50 | 越高越好 |
| 3.5 | AI脚本生成率 | `ai_script_gen_rate` | 派生指标 | % | 40 | 越高越好 |
| 3.6 | MR渗透率（累计） | `mr_ai_penetration` | 派生指标 | % | 70 | 越高越好 |
| — | 研发提效指数 | `rde_index` | 复合指标 | 分 | 85 | 越高越好 |

## 详细口径

### 指标明细

#### 2.0.1 / 2.5 MR实现周期

MR 从提出到开发完成的中位时长；口径上等于分析周期与开发周期之和。

| 项 | 值 |
| --- | --- |
| 指标编号 | 2.0.1 / 2.5 |
| 指标 ID | `mr_impl_cycle` |
| 类型 | 配对指标 |
| 单位 | h |
| 目标值 | 120 |
| 优化方向 | 越低越好 |
| 计算公式 | `median(mr.dev.done - mr.created)` |
| 聚合方式 | `median` |
| 起点事实 | `mr.created` |
| 终点事实 | `mr.dev.done` |
| 负责人 | 研发效能平台 |

#### 2.0.2 RR按期达成率

已交付 RR 中按期交付的比例。分子分母取同一批 RR 事实，避免窗口边界造成口径错位。

| 项 | 值 |
| --- | --- |
| 指标编号 | 2.0.2 |
| 指标 ID | `rr_on_time_rate` |
| 类型 | 派生指标 |
| 单位 | % |
| 目标值 | 90 |
| 优化方向 | 越高越好 |
| 计算公式 | `on_time / planned * 100（同一批已交付 RR）` |
| 依赖指标 | `rr_on_time_count`, `rr_delivered_planned` |
| 负责人 | 研发管理部 |

#### 2.1 MR研发人均交付数

窗口内 MR 交付数 ÷ 中心人力 ÷ 月数，衡量人均对外交付产出。

| 项 | 值 |
| --- | --- |
| 指标编号 | 2.1 |
| 指标 ID | `mr_delivery_per_capita` |
| 类型 | 派生指标 |
| 单位 | 个/人月 |
| 目标值 | 1.2 |
| 优化方向 | 越高越好 |
| 计算公式 | `delivered / headcount / months` |
| 依赖指标 | `mr_delivered_count`, `headcount_center` |
| 负责人 | 研发管理部 |

#### 2.2 MR研发人均实现数

窗口内 MR 开发完成数 ÷ 中心人力 ÷ 月数，衡量人均实现产出。

| 项 | 值 |
| --- | --- |
| 指标编号 | 2.2 |
| 指标 ID | `mr_impl_per_capita` |
| 类型 | 派生指标 |
| 单位 | 个/人月 |
| 目标值 | 1.6 |
| 优化方向 | 越高越好 |
| 计算公式 | `dev_done / headcount / months` |
| 依赖指标 | `mr_dev_done_count`, `headcount_center` |
| 负责人 | 研发管理部 |

#### 2.3 MR研发人均实现数（实时）

与 2.2 同口径，按当前窗口实时计算；配合同比视图对比 2025 全年与 2026 年 1-10 月。

| 项 | 值 |
| --- | --- |
| 指标编号 | 2.3 |
| 指标 ID | `mr_impl_per_capita_live` |
| 类型 | 派生指标 |
| 单位 | 个/人月 |
| 目标值 | 1.6 |
| 优化方向 | 越高越好 |
| 计算公式 | `dev_done / headcount / months` |
| 依赖指标 | `mr_dev_done_count`, `headcount_center` |
| 负责人 | 研发管理部 |

#### 2.4 MR研发人均实现数（中心+外包折算）

分母改用中心人力与外包折算人力之和，口径更贴近实际投入；可按项目组下钻核对人力口径。

| 项 | 值 |
| --- | --- |
| 指标编号 | 2.4 |
| 指标 ID | `mr_impl_per_capita_converted` |
| 类型 | 派生指标 |
| 单位 | 个/人月 |
| 目标值 | 1.4 |
| 优化方向 | 越高越好 |
| 计算公式 | `dev_done / (center + outsourced*factor) / months` |
| 依赖指标 | `mr_dev_done_count`, `converted_headcount` |
| 负责人 | 研发管理部 |

#### 2.7 MR人均分析吞吐率

人均每月完成需求分析的 MR 数，衡量分析环节产能。

| 项 | 值 |
| --- | --- |
| 指标编号 | 2.7 |
| 指标 ID | `mr_analysis_throughput` |
| 类型 | 派生指标 |
| 单位 | 个/人月 |
| 目标值 | 1.8 |
| 优化方向 | 越高越好 |
| 计算公式 | `analysis_done / headcount / months` |
| 依赖指标 | `mr_analysis_done_count`, `headcount_center` |
| 负责人 | 需求分析组 |

#### 2.8 MR分析周期

MR 从提出到需求分析完成的中位时长。

| 项 | 值 |
| --- | --- |
| 指标编号 | 2.8 |
| 指标 ID | `mr_analysis_cycle` |
| 类型 | 配对指标 |
| 单位 | h |
| 目标值 | 48 |
| 优化方向 | 越低越好 |
| 计算公式 | `median(mr.analysis.done - mr.created)` |
| 聚合方式 | `median` |
| 起点事实 | `mr.created` |
| 终点事实 | `mr.analysis.done` |
| 负责人 | 需求分析组 |

#### 2.9 MR人均开发吞吐率

人均每月完成开发的 MR 数，衡量开发环节产能。

| 项 | 值 |
| --- | --- |
| 指标编号 | 2.9 |
| 指标 ID | `mr_dev_throughput` |
| 类型 | 派生指标 |
| 单位 | 个/人月 |
| 目标值 | 1.6 |
| 优化方向 | 越高越好 |
| 计算公式 | `dev_done / headcount / months` |
| 依赖指标 | `mr_dev_done_count`, `headcount_center` |
| 负责人 | 开发组 |

#### 2.10 MR开发周期

MR 从分析完成到编码实现完成的中位时长。

| 项 | 值 |
| --- | --- |
| 指标编号 | 2.10 |
| 指标 ID | `mr_dev_cycle` |
| 类型 | 配对指标 |
| 单位 | h |
| 目标值 | 72 |
| 优化方向 | 越低越好 |
| 计算公式 | `median(mr.dev.done - mr.analysis.done)` |
| 聚合方式 | `median` |
| 起点事实 | `mr.analysis.done` |
| 终点事实 | `mr.dev.done` |
| 负责人 | 开发组 |

#### 2.11 MR人均测试吞吐率

人均每月完成测试的 MR 数，衡量测试环节产能。

| 项 | 值 |
| --- | --- |
| 指标编号 | 2.11 |
| 指标 ID | `mr_test_throughput` |
| 类型 | 派生指标 |
| 单位 | 个/人月 |
| 目标值 | 1.7 |
| 优化方向 | 越高越好 |
| 计算公式 | `test_done / headcount / months` |
| 依赖指标 | `mr_test_done_count`, `headcount_center` |
| 负责人 | 质量保障 |

#### 2.12 MR验收周期

MR 从开发完成到验收通过的中位时长。

| 项 | 值 |
| --- | --- |
| 指标编号 | 2.12 |
| 指标 ID | `mr_accept_cycle` |
| 类型 | 配对指标 |
| 单位 | h |
| 目标值 | 24 |
| 优化方向 | 越低越好 |
| 计算公式 | `median(mr.accepted - mr.dev.done)` |
| 聚合方式 | `median` |
| 起点事实 | `mr.dev.done` |
| 终点事实 | `mr.accepted` |
| 负责人 | 质量保障 |

### 过程指标

#### 3.1 需求分析生成率

AI 生成的需求分析份数占分析总份数比例。

| 项 | 值 |
| --- | --- |
| 指标编号 | 3.1 |
| 指标 ID | `analysis_gen_rate` |
| 类型 | 派生指标 |
| 单位 | % |
| 目标值 | 60 |
| 优化方向 | 越高越好 |
| 计算公式 | `ai_analysis / total_analysis * 100` |
| 依赖指标 | `ai_analysis_count`, `total_analysis_count` |
| 负责人 | 工程效能 |

#### 3.2 需求方案生成率

AI 生成的需求方案份数占方案总份数比例。

| 项 | 值 |
| --- | --- |
| 指标编号 | 3.2 |
| 指标 ID | `solution_gen_rate` |
| 类型 | 派生指标 |
| 单位 | % |
| 目标值 | 55 |
| 优化方向 | 越高越好 |
| 计算公式 | `ai_solution / total_solution * 100` |
| 依赖指标 | `ai_solution_count`, `total_solution_count` |
| 负责人 | 工程效能 |

#### 3.3 代码生成率

AI 生成代码行数占代码变更总行数比例，按行统计。

| 项 | 值 |
| --- | --- |
| 指标编号 | 3.3 |
| 指标 ID | `code_gen_rate` |
| 类型 | 派生指标 |
| 单位 | % |
| 目标值 | 45 |
| 优化方向 | 越高越好 |
| 计算公式 | `ai_lines / total_lines * 100` |
| 依赖指标 | `ai_lines`, `total_lines` |
| 负责人 | 工程效能 |

#### 3.4 AI测试用例生成率

AI 生成的测试用例数占用例总数比例。

| 项 | 值 |
| --- | --- |
| 指标编号 | 3.4 |
| 指标 ID | `ai_testcase_gen_rate` |
| 类型 | 派生指标 |
| 单位 | % |
| 目标值 | 50 |
| 优化方向 | 越高越好 |
| 计算公式 | `ai_cases / total_cases * 100` |
| 依赖指标 | `ai_cases`, `total_cases` |
| 负责人 | 质量保障 |

#### 3.5 AI脚本生成率

AI 生成的自动化测试脚本数占脚本总数比例。

| 项 | 值 |
| --- | --- |
| 指标编号 | 3.5 |
| 指标 ID | `ai_script_gen_rate` |
| 类型 | 派生指标 |
| 单位 | % |
| 目标值 | 40 |
| 优化方向 | 越高越好 |
| 计算公式 | `ai_scripts / total_scripts * 100` |
| 依赖指标 | `ai_scripts`, `total_scripts` |
| 负责人 | 质量保障 |

#### 3.6 MR渗透率（累计）

窗口内使用过 AI 辅助的 MR 占全部 MR 比例；默认按 2026 年累计口径查看各项目组。

| 项 | 值 |
| --- | --- |
| 指标编号 | 3.6 |
| 指标 ID | `mr_ai_penetration` |
| 类型 | 派生指标 |
| 单位 | % |
| 目标值 | 70 |
| 优化方向 | 越高越好 |
| 计算公式 | `ai_touched / created * 100` |
| 依赖指标 | `mr_ai_touched_count`, `mr_created_count` |
| 负责人 | 工程效能 |

## 内部口径指标（不作为 KPI 展示）

以下指标作为其他指标的分子/分母存在，只在详情页与血缘图中可见。

| 指标 | ID | 用途 |
| --- | --- | --- |
| AI需求分析数 | `ai_analysis_count` | 被 `analysis_gen_rate` 使用 |
| AI生成用例数 | `ai_cases` | 被 `ai_testcase_gen_rate` 使用 |
| AI生成代码行 | `ai_lines` | 被 `code_gen_rate` 使用 |
| AI生成脚本数 | `ai_scripts` | 被 `ai_script_gen_rate` 使用 |
| AI需求方案数 | `ai_solution_count` | 被 `solution_gen_rate` 使用 |
| 折算总人力 | `converted_headcount` | 被 `mr_impl_per_capita_converted` 使用 |
| 中心人力 | `headcount_center` | 被 `converted_headcount`, `mr_delivery_per_capita`, `mr_impl_per_capita`, `mr_impl_per_capita_live`, `mr_analysis_throughput`, `mr_dev_throughput`, `mr_test_throughput` 使用 |
| 外包人力 | `headcount_outsourced` | 被 `converted_headcount` 使用 |
| MR验收完成数 | `mr_accepted_count` | 被 内部计算 使用 |
| 使用AI的MR数 | `mr_ai_touched_count` | 被 `mr_ai_penetration` 使用 |
| MR分析完成数 | `mr_analysis_done_count` | 被 `mr_analysis_throughput` 使用 |
| MR提出数 | `mr_created_count` | 被 `mr_ai_penetration` 使用 |
| MR交付数 | `mr_delivered_count` | 被 `mr_delivery_per_capita` 使用 |
| MR开发完成数 | `mr_dev_done_count` | 被 `mr_impl_per_capita`, `mr_impl_per_capita_live`, `mr_impl_per_capita_converted`, `mr_dev_throughput` 使用 |
| MR测试完成数 | `mr_test_done_count` | 被 `mr_test_throughput` 使用 |
| 外包折算系数 | `outsourced_factor` | 被 `converted_headcount` 使用 |
| RR实际交付数 | `rr_delivered_count` | 被 内部计算 使用 |
| 已交付RR计划数 | `rr_delivered_planned` | 被 `rr_on_time_rate` 使用 |
| RR按期交付数 | `rr_on_time_count` | 被 `rr_on_time_rate` 使用 |
| RR计划数 | `rr_planned_count` | 被 内部计算 使用 |
| 需求分析总数 | `total_analysis_count` | 被 `analysis_gen_rate` 使用 |
| 用例总数 | `total_cases` | 被 `ai_testcase_gen_rate` 使用 |
| 代码变更总行 | `total_lines` | 被 `code_gen_rate` 使用 |
| 脚本总数 | `total_scripts` | 被 `ai_script_gen_rate` 使用 |
| 需求方案总数 | `total_solution_count` | 被 `solution_gen_rate` 使用 |
