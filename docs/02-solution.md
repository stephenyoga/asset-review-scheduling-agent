# 02 解决方案

## 1. 系统架构

单进程、分层、运行时零第三方依赖，便于离线复现：

```
CLI (src/cli.py) —— 参数解析 / 环境变量 / 交互确认
        │
Agent (src/agent.py) —— ReAct 循环 + 步数上限 + 后置护栏
        │  decide()               │  execute()
        ▼                        ▼
决策器 (src/llm/)         工具层 (src/tools/)
  · LLM 接口                 · read_asset / check_rules
  · MockLLM（状态机）         · query_slots / save_draft
  · OpenAICompatLLM（多厂商）
        │                        │
        └────────┬───────────────┘
                 ▼
         数据层 (src/store/)
  · assets / rules / schedule（合成 JSON）
  · DraftStore（幂等去重 + faulty 故障）
```

决策器与工具层解耦：决策器只产出 `Action`，工具层负责执行并返回结构化 `observation`，由 Agent 串联。

## 2. 动态决策（ReAct）

### 2.1 循环骨架

```python
for step in range(1, MAX_TOOL_CALLS + 1):   # MAX_TOOL_CALLS = 10
    action = llm.decide(state, obs)         # ① 模型选动作（依据上一步 obs）
    action = apply_guardrail(action, state) # ② 后置护栏
    if action.name == "finish":
        break
    obs = execute(action.name, action.args) # ③ 执行工具
    # ④ 观察结果写回 state，下一轮 decide 据此调整
else:
    state["unfinished"] = True              # 达到上限 → 明确未完成
```

每一步动作由 `decide` 依据**上一步工具返回**产生，非预设死路径；达到步数上限返回明确「未完成」。

### 2.2 动作格式（Mock / 真实 LLM 同构）

```json
{"thought": "决策依据", "action": "save_draft",
 "action_input": {"asset_id": "M01", "slot": "19:00",
                  "pending_confirmations": ["期望时段 18:00 不可用，建议改为 19:00"]}}
```

### 2.3 决策策略表（Mock 实现依据；真实 LLM 写入 system prompt）

| 上一步观察 | 决策动作 | 产物 |
|---|---|---|
| read 缺必填字段 | 结束 + 标记 `need_more_info` | 不排期 |
| check 高风险 | 结束 + `blocked` | 阻断 + 风险原因 |
| check 通过 | query_slots | 继续 |
| 时段 free | save_draft | 草稿 |
| 时段 occupied + 软性 | 找邻近 free → save_draft 替代时段 | 草稿 + 待确认 |
| 时段 occupied + 硬性 | 结束 + `blocked`，不擅自改 | 阻断 + 请求确认 |
| save 重复 | 复用已有草稿 | 一份草稿 |
| save 失败 | 如实上报 `save_failed` | 失败状态 |

## 3. 两道防线

### 3.1 后置校验护栏（防越权）

`apply_guardrail` 在执行 `save_draft` 前校验，对 Mock 与真实 LLM 统一生效。硬性判定由共享函数
`is_hard(requirement)` 给出：**`hard_constraint=true` 或存在 `hard_deadline` 即视为硬性**（`src/policy.py`）。

拦截两类越权，原因可同时累积：

1. 硬性要求且保存时段 ≠ `preferred_time` → 「硬性要求时段不可擅自变更」。
2. 保存时段晚于 `hard_deadline` → 「超出硬性截止时间」。

这是「越权发布 = 关键缺陷」的直接防线：即使真实 LLM 被 prompt 诱导越权，护栏也能兜底。

### 3.2 步数上限

`MAX_TOOL_CALLS = 10`，达到上限返回 `unfinished` + 明确原因，不产出「半成品」结果。

## 4. 数据模型

```python
Asset  = {asset_id, title, category, owner, duration_min, risk_flags,
          publish_requirement: {preferred_time, hard_constraint, hard_deadline, flexible}}
Rule   = {rule_id, type:"risk", field, condition:{"in"/"contains"/"gt"}, level, reason}
Slot   = {time, status:"free"/"occupied", faulty?:true}   # faulty 为隐藏故障
Draft  = {draft_id, asset_id, slot, status:"draft", pending_confirmations}
```

**必填字段**：`title / category / owner / publish_requirement.preferred_time`，缺任一 → 信息不足。

## 5. 工具接口

| 工具 | 输入 | 成功返回 | 失败模式 |
|---|---|---|---|
| `read_asset` | asset_id | 素材 + `missing_fields` | 素材不存在 |
| `check_rules` | asset | `risks[]` + `passed` | 缺素材数据 |
| `query_slots` | date, start?, end? | `slots[]` | — |
| `save_draft` | asset_id, slot, pending | draft_id / duplicate | 非法时段 / occupied / faulty |

统一 observation 结构：`{"ok": true, ...}` 或 `{"ok": false, "error": ...}`。

## 6. 关键取舍（含与用户确认的 10 点）

| 取舍 | 决定 | 理由 |
|---|---|---|
| 模型协议 | 统一 OpenAI 兼容端点 | DeepSeek/Qwen/Claude 均有兼容端点，一个 client 覆盖三家 |
| 多厂商 | DeepSeek / Qwen / Claude（Anthropic API） | 覆盖国产 + 国外 |
| 输出不稳定 | 解析失败重试 → 降级 Mock 并标注 | 真实模型格式抖动不崩 |
| 边界保证 | 后置校验护栏（做） | prompt 无法 100% 约束，护栏兜底 |
| 硬/软要求口径 | `hard_constraint=true` 或含 `hard_deadline` 为硬性 | 其余为软性偏好 |
| 必填字段 | title/category/owner/preferred_time | 缺任一不排期 |
| 幂等键 | `(asset_id, slot)` | 简单无歧义 |
| 保存失败触发 | 素材绑定 faulty_slot（查询时 free、保存时故障） | 贴近真实隐藏故障 |
| 时间粒度 | 整点 slot，duration 仅展示 | 题目只考冲突不考容量 |
| 运行方式 | CLI + `--interactive` 交互模式 | 一条命令复现，待确认项可逐条 y/n |

## 7. 验收点覆盖

| 验收点 | 驱动工具结果 | 决策产物 | 素材 |
|---|---|---|---|
| ① 正常排期 | 无风险 + 时段 free | drafted | M02 |
| ② 信息缺失 | read 缺 owner | need_more_info | M03 |
| ③ 规则风险 | check 高风险 | blocked | M04 |
| ④ 时段冲突 | slots occupied | 建议 19:00 待确认 / 阻断 | M01 / M05 |
| ⑤ 重复提交 | save 幂等命中 | 复用 D-0001 | M01 ×2 |
| ⑥ 保存失败 | faulty slot | save_failed | M07 |
