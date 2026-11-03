# examples/ 运行记录与 Trace

三个文件为 CLI 实际运行记录（UTF-8 文本），覆盖全部 6 个验收点。
生成命令见各文件首行对应的 CLI 调用，可本地一键复现。

| 文件 | 输入 | 覆盖验收点 | 复现命令 |
|---|---|---|---|
| `trace_all.txt` | 全部素材 M01/M02/M03/M04/M05/M07 | ①正常 ②缺失 ③风险 ④冲突(软/硬) ⑥保存失败 | `python -m src.cli --all --trace` |
| `trace_duplicate.txt` | M01 重复提交两次 | ⑤重复提交（复用同一草稿） | `python -m src.cli --case M01 --repeat 2 --trace` |
| `trace_interactive_reject.txt` | M01 + 交互模式，用户输入 n 拒绝 | ④待确认边界（用户拒绝不保存） | `printf "n\n" \| python -m src.cli --case M01 --interactive --trace` |

> 注：`trace_all.txt` 中 M01 覆盖④软性冲突（建议 19:00 并待确认），M05 覆盖④硬性冲突
> （阻断 + 请求确认，未擅自变更）。三个文件合计覆盖题目全部验收点。
