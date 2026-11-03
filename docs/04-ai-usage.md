# 04 AI 辅助使用记录

## AI 辅助范围

| 环节 | AI 辅助内容 |
|---|---|
| 需求理解 | 将试卷要求拆解为 6 验收点、硬/软要求边界、ReAct 硬性要求 |
| 方案设计 | 分层架构、数据模型、工具接口、决策策略表、护栏设计 |
| 代码实现 | 全部源码（store/tools/llm/agent/cli）、合成数据 |
| 测试 | 10 个 pytest 用例（6 验收点 + 护栏 + 步数上限） |
| 验证材料 | 运行 Trace、examples、本套 docs |

## 个人决策（候选人与 AI 讨论后确认的 10 个关键取舍）

1. 多厂商统一走 **OpenAI 兼容端点**（而非分别实现协议）
2. Claude 指 **Anthropic API** 的模型
3. 接受「解析失败重试 → 降级 Mock」策略
4. **后置校验护栏**要做（防越权改硬性要求）
5. 硬性要求口径：`hard_constraint=true` 或含 `hard_deadline`
6. 必填字段集合：title/category/owner/preferred_time
7. 幂等键用 `(asset_id, slot)`
8. 保存失败用 **faulty_slot**（查询时 free、保存时故障）
9. slot 整点、duration 仅展示
10. 需要 **交互模式**（`--interactive`）

## 个人修改与验证

### 第二轮：补充测试发现 3 个 Bug

候选人补充了 4 个测试文件（55 个用例），使覆盖从 10 增至 65，并发现 3 个缺陷，
由 AI 修复：

| Bug | 位置 | 修复 |
|---|---|---|
| `time_to_minutes` 未校验越界 | src/tools/utils.py | 增加 `0<=h<24 且 0<=m<60` 校验 |
| `_find_free` 仅向后搜索 | src/llm/mock.py | 改为双向按距离最近（距离相同更晚优先） |
| `hard_deadline` 未计入硬性 | src/agent.py + src/llm/mock.py | 抽取 `is_hard()`，含 hard_deadline 即硬性 |

其中 Bug 3 触及「越权修改硬性发布要求」关键缺陷防线。经与候选人确认语义后，按**语义 B**
（含 hard_deadline 即硬性、preferred 不可擅自改）修复，并同步更新了与旧语义冲突的
`test_guardrail_deadline_boundary_inclusive`。

### 验证命令

- `python -m pytest -q` → **65 passed**
- `python -m src.cli --all --trace` → 6 验收点 Trace 正确、端到端无回归

## 边界声明

- 本项目的 AI 辅助覆盖「设计 + 实现 + 测试 + 文档」全链路；个人贡献体现在
  关键取舍的确认与对生成结果的验证把关。
- 未提交任何真实 API key 或隐私数据（`.env` 已 gitignore，`.env.example` 仅占位）。
