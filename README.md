# 素材审核与发布排期 Agent

帮助内容团队找出待处理素材，形成**无冲突、可确认**的发布排期（仅保存草稿，不接真实发布）。

- **动态决策**：ReAct 循环「模型选择动作 → 执行工具 → 观察结果 → 调整下一步或结束」，动作选择由工具返回驱动。
- **多模型接入**：默认离线 Mock（零依赖可复现），可切换 DeepSeek / Qwen / Claude（OpenAI 兼容协议）。
- **两道防线**：步数上限（超限返回明确未完成）+ 后置护栏（拦截越权修改硬性发布要求）。

## 环境要求

- Python 3.10+（开发环境 3.13）
- 运行时**零第三方依赖**（核心代码仅标准库，真实 LLM 用 `urllib` 直连）
- 测试依赖：`pytest`

## 安装

```bash
# 1) 创建虚拟环境（可选）
python -m venv .venv
# Windows: .venv\Scripts\activate   Linux/macOS: source .venv/bin/activate

# 2) 安装测试依赖
pip install -r requirements.txt

# 3) 无需任何环境变量即可运行（默认 Mock）
#    仅在使用真实 LLM 时，复制 .env.example 为 .env 并填写对应 key
```

## 运行

```bash
python -m src.cli --all                      # 处理全部素材（默认 Mock）
python -m src.cli --case M01                 # 处理单个素材
python -m src.cli --case M01 --trace         # 输出完整 ReAct Trace
python -m src.cli --case M01 --repeat 2      # 重复提交（演示幂等去重）
python -m src.cli --case M01 --interactive   # 交互模式（待确认项逐条 y/n）
python -m src.cli --all --provider deepseek  # 真实 LLM（需 .env 配置 key）

# 运行测试
python -m pytest -q                          # 10 个测试全部通过
```

> Windows 终端若中文乱码，先执行 `set PYTHONIOENCODING=utf-8`（或 `chcp 65001`）。
> 真实 LLM 输出不稳定时会自动降级到 Mock 并在 Trace 标注 `mock(fallback)`。

## 评审入口（建议阅读顺序）

1. `docs/01-requirements.md` —— 用户、目标、范围、成功标准
2. `docs/02-solution.md` —— 调用流程、动态决策、技术取舍（**核心设计**）
3. `docs/03-evaluation.md` —— 测试预期、实际结果、失败与限制
4. `docs/04-ai-usage.md` —— AI 辅助内容、个人修改与验证
5. `docs/05-retrospective.md` —— 最难问题、学习收获、下一步
6. `tests/test_agent.py` —— 6 验收点可执行测试
7. `examples/` —— 3 组运行记录与完整 ReAct Trace

## 目录结构

```
├── src/
│   ├── cli.py            # CLI 入口（含交互模式）
│   ├── agent.py          # ReAct 循环 + 步数上限 + 后置护栏
│   ├── llm/              # 决策器：base / mock / openai_compat（多厂商）
│   ├── tools/            # read_asset / check_rules / query_slots / save_draft
│   └── store/            # 数据加载 + DraftStore（幂等 + faulty 故障）
├── data/                 # 合成素材、规则、排期
├── tests/                # 6 验收点 + 护栏 + 步数上限（10 用例）
├── examples/             # 运行记录与 Trace
└── docs/                 # 01-05 文档
```

## 验收点覆盖

| 验收点 | 素材 | 结果 |
|---|---|---|
| ① 正常排期 | M02 | approved → 10:00 drafted |
| ② 信息缺失 | M03 | need_more_info（缺 owner） |
| ③ 规则风险 | M04 | blocked（违禁分类 + 违禁词） |
| ④ 时段冲突 | M01 软性 / M05 硬性 | 建议 19:00 待确认 / 阻断请求确认 |
| ⑤ 重复提交 | M01 ×2 | 复用同一草稿 D-0001 |
| ⑥ 保存失败 | M07 | save_failed，如实返回错误 |
