"""泵站设施业务规则：状态流转、字段校验与筛选口径都收在这里。

状态必须按既定顺序单向流转：
待接管 → 运行正常 → 减量运行 → 停运检修
每个动作只在它对应的上一个状态下可执行，越序或重复提交一律拦下并说明原因。
"""
from __future__ import annotations

import threading
from datetime import datetime
from typing import Any

from app.store import store

MODULE = "pumpstation"
REQUIRED_FIELDS = ["泵站编号", "泵站名称", "服务区域"]
STATUS_ORDER = ["待接管", "运行正常", "减量运行", "停运检修"]
ACTION_RULES = {"办理接管": "运行正常", "标记减量": "减量运行", "安排检修": "停运检修"}
# 只有首状态算待办；后两个状态属于异常工况。口径集中在这两个函数里，各入口共用。
ABNORMAL_STATUSES = {"减量运行", "停运检修"}

# 动作写入在线程池里执行，加锁保证并发的重复提交只有第一个能落到数据上。
_action_lock = threading.Lock()


def _is_pending(status: str) -> bool:
    return status == STATUS_ORDER[0]


def _is_abnormal(status: str) -> bool:
    return status in ABNORMAL_STATUSES


class PumpstationService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("泵站编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        initial = STATUS_ORDER[0]
        entry["status"] = initial
        # 展示列与内部状态始终写同一个值，避免列表与详情两套口径。
        entry["泵站状态"] = initial
        entry["pending"] = _is_pending(initial)
        entry["abnormal"] = _is_abnormal(initial)
        entry["history"] = [self._history_record("登记建档", None, initial)]
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        # 锁内重新读取状态：并发重复提交时，后到的请求会看到已更新的状态并被拦下。
        with _action_lock:
            entry = store.find(MODULE, entry_id)
            if entry is None:
                return None, f"泵站 {entry_id} 不存在或已归档"
            if action not in ACTION_RULES:
                return None, f"动作「{action}」不属于泵站设施可执行范围"

            label = str(entry.get("泵站编号") or entry_id)
            current = str(entry.get("status") or "")
            if current not in STATUS_ORDER:
                return None, f"泵站 {label} 当前状态「{current}」不在允许的状态序列里，请联系管理员核对"

            current_index = STATUS_ORDER.index(current)
            target = ACTION_RULES[action]

            if current_index == len(STATUS_ORDER) - 1:
                return None, f"泵站 {label} 已{current}，全部流程已办结，不能再执行「{action}」"
            expected_target = STATUS_ORDER[current_index + 1]
            if target == current:
                return None, f"泵站 {label} 已{action}（当前状态：{current}），该动作已生效，请勿重复提交"
            if target != expected_target:
                prerequisites = [
                    name
                    for name, to_status in ACTION_RULES.items()
                    if STATUS_ORDER.index(to_status) <= current_index
                ]
                done = "、".join(prerequisites) if prerequisites else "尚未办理任何手续"
                return None, (
                    f"泵站 {label} 当前为「{current}」，{done}，"
                    f"需先执行「{ACTION_RULES_INV[current]}」后才能「{action}」，不能越序办理"
                )

            # 校验通过才落库：状态、展示列、待办/异常标记一次写齐，历史只追加不覆盖。
            entry["status"] = target
            entry["泵站状态"] = target
            entry["pending"] = _is_pending(target)
            entry["abnormal"] = _is_abnormal(target)
            entry.setdefault("history", []).append(self._history_record(action, current, target))
            return entry, f"泵站 {label} 已{action}，状态更新为{target}"

    @staticmethod
    def _history_record(action: str, from_status: str | None, to_status: str) -> dict[str, str]:
        return {
            "action": action,
            "from": from_status or "",
            "to": to_status,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }


# 每个状态对应的下一步动作名，越序提示时直接取用。
ACTION_RULES_INV = {
    status: next(
        (name for name, to_status in ACTION_RULES.items()
         if STATUS_ORDER.index(to_status) == STATUS_ORDER.index(status) + 1),
        "",
    )
    for status in STATUS_ORDER
}
