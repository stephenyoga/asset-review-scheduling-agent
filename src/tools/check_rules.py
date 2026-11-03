"""工具：按审核规则检查素材风险。"""
from .utils import get_path, matches


def check_rules(args: dict, store: dict) -> dict:
    asset = args.get("asset")
    if not asset:
        return {"ok": False, "error": "缺少素材数据，无法检查规则"}

    risks = []
    for rule in store["rules"]:
        if rule.get("type") != "risk":
            continue
        value = get_path(asset, rule.get("field", ""))
        condition = rule.get("condition", {})
        if matches(value, condition):
            risks.append(
                {
                    "rule_id": rule["rule_id"],
                    "level": rule.get("level", "low"),
                    "reason": rule.get("reason", ""),
                }
            )

    passed = not any(r["level"] == "high" for r in risks)
    return {"ok": True, "risks": risks, "passed": passed}
