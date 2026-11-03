"""CLI 入口：素材审核与发布排期 Agent。

用法：
    python -m src.cli --all                      # 默认 Mock，处理全部素材
    python -m src.cli --case M01                 # 处理单个素材
    python -m src.cli --case M01 --repeat 2      # 重复提交（演示幂等去重）
    python -m src.cli --case M01 --trace         # 输出完整 ReAct Trace
    python -m src.cli --case M01 --interactive   # 交互模式（待确认项逐条 y/n）
    python -m src.cli --all --provider deepseek  # 真实 LLM（需 .env 配置 key）
"""
import argparse
import json
import os
from pathlib import Path
from typing import List, Optional

from .llm import create_llm
from .store import build_store
from .agent import run, MAX_TOOL_CALLS

_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"

_KEY_MAP = {
    "deepseek": ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL"),
    "qwen": ("QWEN_API_KEY", "QWEN_BASE_URL", "QWEN_MODEL"),
    "claude": ("CLAUDE_API_KEY", "CLAUDE_BASE_URL", "CLAUDE_MODEL"),
}


def load_env() -> dict:
    env = {}
    if _ENV_PATH.exists():
        for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def build_llm(provider: str, env: dict):
    if provider == "mock":
        return create_llm("mock")
    key, base, model = _KEY_MAP[provider]
    api_key = env.get(key) or os.environ.get(key)
    if not api_key:
        raise SystemExit(f"未配置 {key}，请在 .env 或环境变量中填写")
    return create_llm(
        provider,
        api_key=api_key,
        base_url=env.get(base),
        model=env.get(model),
    )


def make_confirm_fn():
    def confirm(asset_id: str, slot: str, pending: List[str]) -> bool:
        print(f"\n[待确认] 素材 {asset_id} 建议时段 {slot}")
        for p in pending:
            print(f"   - {p}")
        while True:
            ans = input("是否确认？[y/n] ").strip().lower()
            if ans in ("y", "yes"):
                return True
            if ans in ("n", "no"):
                return False
            print("请输入 y 或 n")

    return confirm


def _summarize_obs(obs: Optional[dict]):
    if obs is None:
        return None
    if not obs.get("ok"):
        return f"失败：{obs.get('error')}"
    if "asset" in obs:
        return f"素材已读取，缺失字段={obs.get('missing_fields', [])}"
    if "risks" in obs:
        return f"风险={[r['reason'] for r in obs.get('risks', [])]}，通过={obs.get('passed')}"
    if "slots" in obs:
        return f"时段={[(s['time'], s.get('status')) for s in obs.get('slots', [])]}"
    if "draft_id" in obs:
        return f"草稿 {obs.get('draft_id')}，重复={obs.get('duplicate', False)}"
    return json.dumps(obs, ensure_ascii=False)[:120]


def print_result(r: dict, show_trace: bool):
    print(f"\n=== 素材 {r['asset_id']} ===")
    print(f"审核状态：{r['review_status']}")
    if r.get("missing_fields"):
        print(f"缺失字段：{', '.join(r['missing_fields'])}")
    if r.get("risk_reasons"):
        print(f"风险原因：{'；'.join(r['risk_reasons'])}")
    if r.get("suggested_slot"):
        print(f"建议时段：{r['suggested_slot']}")
    if r.get("pending_confirmations"):
        print(f"待确认项：{'；'.join(r['pending_confirmations'])}")
    print(f"草稿状态：{r.get('draft_status')}")
    if r.get("draft"):
        d = r["draft"]
        dup = "（重复提交，复用已有草稿）" if d.get("duplicate") else ""
        print(f"草稿 ID：{d.get('draft_id')} @ {d.get('slot')}{dup}")
    if r.get("draft_error"):
        print(f"保存错误：{r['draft_error']}")
    if r.get("unfinished"):
        print(f"未完成：{r.get('unfinished_reason')}")
    print(f"工具调用次数：{r.get('tool_calls')}")

    if show_trace:
        print("\n  --- ReAct Trace ---")
        for s in r["trace"]:
            print(
                f"  [step {s['step']}] action={s['action']}"
                f"({json.dumps(s['action_input'], ensure_ascii=False)})"
            )
            print(f"        决策依据：{s['thought']}")
            print(f"        来源：{s['source']}")
            obs_summary = _summarize_obs(s.get("observation"))
            if obs_summary is not None:
                print(f"        观察：{obs_summary}")


def main(argv: Optional[List[str]] = None):
    parser = argparse.ArgumentParser(description="素材审核与发布排期 Agent")
    parser.add_argument("--case", action="append", dest="cases", help="指定素材 ID，可多次")
    parser.add_argument("--all", action="store_true", help="处理全部素材")
    parser.add_argument("--repeat", type=int, default=1, help="对 --case 素材重复处理次数（演示重复提交）")
    parser.add_argument("--provider", default=None, help="mock / deepseek / qwen / claude")
    parser.add_argument("--interactive", action="store_true", help="交互模式：待确认项逐条 y/n")
    parser.add_argument("--date", default=None, help="排期日期，默认取 schedule.json")
    parser.add_argument("--trace", action="store_true", help="输出完整 ReAct Trace")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    args = parser.parse_args(argv)

    env = load_env()
    provider = args.provider or env.get("AGENT_LLM_PROVIDER", "mock")
    llm = build_llm(provider, env)
    store = build_store()
    date = args.date or store["schedule"]["date"]

    if args.cases:
        asset_ids = []
        for c in args.cases:
            asset_ids.extend([c] * args.repeat)
    else:
        asset_ids = [a["asset_id"] for a in store["assets"]]

    confirm_fn = make_confirm_fn() if args.interactive else None
    results = run(asset_ids, date, llm, store, args.interactive, confirm_fn)

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print(f"排期日期：{date} | 决策器：{provider} | 步数上限：{MAX_TOOL_CALLS}")
        for r in results:
            print_result(r, args.trace)

    return results


if __name__ == "__main__":
    main()
