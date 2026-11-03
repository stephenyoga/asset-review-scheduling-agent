"""工具层公共辅助：字段路径读取、规则条件匹配、时间比较。"""


def get_path(obj, path: str):
    """按点路径读取嵌套字段，如 'publish_requirement.preferred_time'，缺失返回 None。"""
    cur = obj
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def matches(value, condition: dict) -> bool:
    if "in" in condition:
        return value in condition["in"]
    if "contains" in condition:
        return isinstance(value, list) and condition["contains"] in value
    if "gt" in condition:
        return isinstance(value, (int, float)) and value > condition["gt"]
    return False


def time_to_minutes(t: str) -> int:
    """'18:00' -> 1080；非法（格式错或越界）返回 None。"""
    try:
        h, m = t.split(":")
        h = int(h)
        m = int(m)
    except (ValueError, AttributeError):
        return None
    if not (0 <= h < 24 and 0 <= m < 60):
        return None
    return h * 60 + m
