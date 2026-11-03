"""工具：查询某日期的时段占用情况。"""
from .utils import time_to_minutes


def query_slots(args: dict, store: dict) -> dict:
    schedule = store["schedule"]
    date = args.get("date", schedule.get("date"))
    slots = schedule.get("slots", [])

    start = time_to_minutes(args["start"]) if args.get("start") else None
    end = time_to_minutes(args["end"]) if args.get("end") else None

    if start is not None or end is not None:
        filtered = []
        for s in slots:
            t = time_to_minutes(s["time"])
            if t is None:
                continue
            if start is not None and t < start:
                continue
            if end is not None and t > end:
                continue
            filtered.append(s)
        slots = filtered

    return {"ok": True, "date": date, "slots": slots}
