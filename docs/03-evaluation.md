# 03 评估

## 1. 测试预期与实际结果

运行 `python -m pytest -q`，结果：**65 passed in 0.09s**。

### 测试文件分布

| 文件 | 用例数 | 覆盖 |
|---|---|---|
| tests/test_agent.py | 10 | 6 验收点 + 护栏 + 步数上限 |
| tests/test_agent_extra.py | 13 | ReAct 链路、结束条件、交互模式、仅草稿约束、护栏 deadline 分支 |
| tests/test_tools_unit.py | 21 | 工具边界、异常、幂等、仅草稿 |
| tests/test_llm_unit.py | 16 | MockLLM 决策表、OpenAICompat 多厂商适配、降级 |
| tests/test_bugs.py | 5 | 3 个 Bug 的回归用例 |

### 6 验收点（核心）

| 验收点 | 用例 | 结果 |
|---|---|---|
| ① 正常排期 | test_normal_schedule | ✅ |
| ② 信息缺失 | test_missing_info | ✅ |
| ③ 规则风险 | test_rule_risk | ✅ |
| ④ 时段冲突（软/硬） | test_slot_conflict_soft / _hard | ✅ |
| ⑤ 重复提交 | test_duplicate_submission | ✅ |
| ⑥ 保存失败 | test_save_fail | ✅ |

### 补充测试发现并已修复的 3 个 Bug

| Bug | 回归用例 | 修复 |
|---|---|---|
| `time_to_minutes` 未校验越界 | test_bug_time_to_minutes_rejects_* | 增加 `0<=h<24 且 0<=m<60` 校验 |
| `_find_free` 仅向后搜索 | test_bug_find_free_considers_earlier_free_slot | 改为双向按距离最近（距离相同更晚优先） |
| `hard_deadline` 未计入硬性 | test_bug_hard_deadline_makes_preferred_immutable / _conflict_treated_as_hard | 抽取 `is_hard()`，含 hard_deadline 即硬性 |

## 2. 运行记录

见 `examples/`（3 组，覆盖全部验收点，含完整 ReAct Trace）：

- `examples/trace_all.txt` —— 全部素材（①正常 ②缺失 ③风险 ④软/硬冲突 ⑥保存失败）
- `examples/trace_duplicate.txt` —— 重复提交（⑤）
- `examples/trace_interactive_reject.txt` —— 交互模式用户拒绝（④待确认边界）

复现：`python -m src.cli --all --trace` 等（见 `examples/README.md`）。

## 3. 参考实例核对

题目参考实例「M01 无风险，要求 18:00，但已占用、19:00 可用，建议 19:00 并待确认，不称已发布」：

- ✅ 建议 19:00（`suggested_slot=19:00`）
- ✅ 标记待确认（`pending_confirmations` 含「建议改为 19:00」）
- ✅ 草稿状态 `draft`，绝不 `published`
- ✅ 相同请求重复保存只一份草稿（`test_duplicate_submission`）
- ✅ 保存失败明确返回失败（`test_save_fail`）

## 4. 失败与限制

| 项 | 说明 |
|---|---|
| Mock 边界 | Mock 决策器只验证流程与边界，**不证明真实模型决策效果**（题目明确） |
| 草稿持久化 | DraftStore 存内存，进程退出即失；未接真实发布/数据库 |
| 时间模型 | 整点 slot，不处理跨日/时区/容量 |
| 真实 LLM | 未经真实 key 联调；结构化输出不稳时降级 Mock（已标注边界） |
| 单 Agent | 无多 Agent 协作、无生产级 Runtime（题目非必需） |
