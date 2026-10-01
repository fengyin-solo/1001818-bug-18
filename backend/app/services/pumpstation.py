"""泵站设施业务规则：状态流转、字段校验与筛选口径都收在这里。

泵站动作严格按顺序流转：待接管 → 运行正常 → 减量运行 → 停运检修，
对应 办理接管 → 标记减量 → 安排检修。越序或重复动作一律拦下；
每次有效动作追加一条历史记录，不覆盖旧记录。
"""
from __future__ import annotations

import threading
from datetime import datetime
from typing import Any

from app.store import store

MODULE = "pumpstation"
REQUIRED_FIELDS = ["泵站编号", "泵站名称", "服务区域"]
STATUS_ORDER = ["待接管", "运行正常", "减量运行", "停运检修"]
# 与 STATUS_ORDER 对齐：ACTION_ORDER[i] 表示从 STATUS_ORDER[i] 流转到下一个状态的动作
ACTION_ORDER = ["办理接管", "标记减量", "安排检修"]
ACTION_RULES = {"办理接管": "运行正常", "标记减量": "减量运行", "安排检修": "停运检修"}
NEGATIVE_ACTIONS = []
DISPLAY_STATUS_FIELD = "泵站状态"

# 同一泵站动作在途时加锁，挡住双击/并发造成的重复提交
_action_locks: dict[int, threading.Lock] = {}
_locks_guard = threading.Lock()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _action_lock(entry_id: int) -> threading.Lock:
    with _locks_guard:
        lock = _action_locks.get(entry_id)
        if lock is None:
            lock = threading.Lock()
            _action_locks[entry_id] = lock
        return lock


def _is_pending(status: str) -> bool:
    """待办口径：只有尚未接管的泵站算待处理，接管后动作不再产生新待办。"""
    return status == STATUS_ORDER[0]


def _next_action(status: str) -> str | None:
    try:
        index = STATUS_ORDER.index(status)
    except ValueError:
        return None
    if index >= len(ACTION_ORDER):
        return None
    return ACTION_ORDER[index]


def _present(entry: dict[str, Any]) -> dict[str, Any]:
    """对外视图：展示用状态字段始终取内部权威状态，并带上下一动作与历史，

    保证列表、详情、动作结果看到同一口径，且不改写仓库里的原始行。
    """
    data = dict(entry)
    data[DISPLAY_STATUS_FIELD] = entry.get("status")
    data["next_action"] = _next_action(str(entry.get("status", "")))
    data["history"] = list(entry.get("history", []))
    return data


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
        return [_present(row) for row in rows[start:start + size]], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return _present(entry) if entry is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        entry["history"] = [{
            "time": _now(),
            "action": "登记泵站",
            "from": None,
            "to": STATUS_ORDER[0],
            "remark": None,
        }]
        rows.append(entry)
        return _present(entry), []

    def run_action(
        self, entry_id: int, action: str, remark: str | None = None
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"泵站 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于泵站设施可执行范围"

        label = str(entry.get("泵站编号") or entry_id)
        lock = _action_lock(entry_id)
        if not lock.acquire(blocking=False):
            return None, f"泵站「{label}」有动作正在提交，请勿重复操作"
        try:
            current = str(entry.get("status", ""))
            target = ACTION_RULES[action]
            try:
                current_index = STATUS_ORDER.index(current)
            except ValueError:
                return None, f"当前状态「{current}」不在允许的状态序列里，无法{action}"

            expected = _next_action(current)
            if expected is None:
                return None, f"泵站「{label}」已办结（{current}），不能再办理任何动作"
            if action != expected:
                target_index = STATUS_ORDER.index(target)
                if target_index <= current_index:
                    return (
                        None,
                        f"泵站「{label}」已{action}（当前状态：{current}），"
                        f"请勿重复办理；下一个可办动作是「{expected}」",
                    )
                return (
                    None,
                    f"动作越序：泵站「{label}」当前为「{current}」，"
                    f"请先「{expected}」，暂不能{action}",
                )

            # 校验通过：状态只允许向序列中的下一状态推进
            entry["status"] = target
            entry["pending"] = _is_pending(target)
            entry["abnormal"] = action in NEGATIVE_ACTIONS
            history = entry.setdefault("history", [])
            history.append({
                "time": _now(),
                "action": action,
                "from": current,
                "to": target,
                "remark": remark or None,
            })
            return _present(entry), f"泵站已{action}，当前状态「{target}」"
        finally:
            lock.release()
