from __future__ import annotations

import re
import time
from typing import Any


FOLLOW_UP_SUGGESTIONS = {
    "quality": ["换成上月", "按产品展开", "查看缺陷原因线索"],
    "equipment": ["换成上月", "按原因展开", "查看最近30天趋势"],
    "production": ["换成上月", "按产线展开", "查看最近30天趋势"],
}


def suggestions_for_scene(scene: str) -> list[str]:
    return FOLLOW_UP_SUGGESTIONS.get(scene, ["换成上月", "查看最近30天趋势", "进一步下钻"])


def _replace_time(question: str, follow_up: str) -> str | None:
    if "上月" in follow_up:
        replaced = re.sub(r"最近\s*\d+\s*天|本月|上月", "上月", question, count=1)
        return replaced if replaced != question else f"上月{question}"
    if "本月" in follow_up:
        replaced = re.sub(r"最近\s*\d+\s*天|本月|上月", "本月", question, count=1)
        return replaced if replaced != question else f"本月{question}"
    recent = re.search(r"最近\s*(\d+)\s*天", follow_up)
    if recent:
        window = f"最近{recent.group(1)}天"
        replaced = re.sub(r"最近\s*\d+\s*天|本月|上月", window, question, count=1)
        return replaced if replaced != question else f"{window}{question}"
    return None


def _replace_dimension(question: str, follow_up: str) -> str | None:
    dimension = next((term for term in ("工序", "产品", "设备", "原因", "产线", "每日") if term in follow_up), None)
    if dimension is None:
        return None
    dimensions = r"各工序|各产品|各设备|各产线|按工序|按产品|按设备|按原因|按产线|每日"
    replacement = "每日" if dimension == "每日" else f"各{dimension}"
    replaced = re.sub(dimensions, replacement, question, count=1)
    if replaced != question:
        return replaced
    suffix = "趋势" if dimension == "每日" else f"，按{dimension}展开"
    return f"{question}{suffix}"


def contextualize_follow_up(
    follow_up: str,
    *,
    parent_question: str,
    parent_scene: str,
    parent_answer: str | None,
) -> dict[str, Any]:
    started = time.perf_counter()
    follow_up = follow_up.strip()

    resolved = _replace_time(parent_question, follow_up)
    strategy = "time_override" if resolved else ""
    if resolved is None:
        resolved = _replace_dimension(parent_question, follow_up)
        strategy = "dimension_override" if resolved else ""
    if resolved is None and any(term in follow_up for term in ("为什么", "原因", "根因")):
        resolved = {
            "quality": "本月缺陷类型 Pareto 分析",
            "equipment": "本月非计划停机原因分布",
            "production": "本月各产线计划达成率",
        }.get(parent_scene, f"{parent_question}；进一步分析原因线索")
        strategy = "evidence_drill_down"
    if resolved is None:
        resolved = f"{parent_question}；进一步追问：{follow_up}"
        strategy = "context_merge"

    duration_ms = max(1, round((time.perf_counter() - started) * 1000))
    return {
        "resolved_question": resolved,
        "suggestions": suggestions_for_scene(parent_scene),
        "trace": [{
            "node_name": "contextualize",
            "display_name": "多轮上下文解析",
            "status": "completed",
            "duration_ms": duration_ms,
            "summary": f"继承上一轮 {parent_scene} 场景，使用 {strategy} 将追问改写为完整分析问题",
            "payload": {
                "strategy": strategy,
                "follow_up": follow_up,
                "parent_question": parent_question,
                "parent_answer_excerpt": (parent_answer or "")[:120],
                "resolved_question": resolved,
            },
        }],
    }
