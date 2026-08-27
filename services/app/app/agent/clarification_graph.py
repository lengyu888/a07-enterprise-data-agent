from __future__ import annotations

import re
import time
from typing import Any, Literal

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict


class UnsafeQuestionError(ValueError):
    pass


class ClarificationState(TypedDict, total=False):
    question: str
    status: Literal["ready", "needs_clarification"]
    detected_scene: str | None
    missing_fields: list[str]
    prompt: str
    options: list[dict[str, str]]
    trace: list[dict[str, Any]]


SCENE_TERMS = {
    "quality": ("质量", "良率", "合格率", "不良率", "缺陷率", "缺陷", "检验", "工序"),
    "equipment": ("设备", "停机", "宕机", "报警", "故障"),
    "production": ("生产", "产量", "完工", "计划达成", "计划完成", "产线"),
}

METRIC_TERMS = (
    "良率", "合格率", "不良率", "缺陷率", "缺陷数量", "缺陷类型", "缺陷",
    "停机时长", "停机时间", "停机次数", "停机", "宕机", "报警次数", "报警",
    "完工产量", "实际产量", "产量", "计划达成率", "计划完成率", "达成率", "完成率",
)
TIME_PATTERN = re.compile(r"本月|上月|本周|最近\s*\d+\s*天|今天|昨日|昨天|20\d{2}[年\-/]\d{1,2}")
GOAL_TERMS = ("排名", "找出", "最低", "最高", "分布", "趋势", "变化", "对比", "分析", "Pareto", "帕累托", "环比", "多少", "哪个", "哪条")
DIMENSION_TERMS = ("总体", "工序", "产品", "设备", "原因", "产线", "每日", "日期", "月份", "类型")
UNSAFE_TERMS = ("drop ", "delete ", "update ", "insert ", "truncate ", "alter ", "删除表", "修改数据库", "忽略安全规则")

SCENE_OPTIONS = {
    "quality": [
        {"label": "工序良率", "question": "分析本月各工序良率，找出良率最低的工序"},
        {"label": "缺陷 Pareto", "question": "本月缺陷类型 Pareto 分析"},
        {"label": "每日趋势", "question": "最近30天每日良率趋势"},
    ],
    "equipment": [
        {"label": "停机时长", "question": "本月各设备非计划停机时长排名"},
        {"label": "报警次数", "question": "本月各设备报警次数排名"},
        {"label": "停机趋势", "question": "最近30天设备停机时长趋势"},
    ],
    "production": [
        {"label": "完工产量", "question": "本月各产线完工产量排名"},
        {"label": "计划达成", "question": "本月各产线计划达成率"},
        {"label": "每日趋势", "question": "最近30天每日完工产量趋势"},
    ],
}

FIELD_LABELS = {
    "scene": "业务场景",
    "metric": "分析指标",
    "time_range": "时间范围",
    "dimension": "分析维度",
    "goal": "分析目标",
}


def _detect_scene(question: str) -> tuple[str | None, bool]:
    scores = {
        scene: sum(term.lower() in question.lower() for term in terms)
        for scene, terms in SCENE_TERMS.items()
    }
    matched = [scene for scene, score in scores.items() if score > 0]
    if not matched:
        return None, False
    ranked = sorted(matched, key=lambda scene: scores[scene], reverse=True)
    ambiguous = len(ranked) > 1 and scores[ranked[0]] == scores[ranked[1]]
    return (None if ambiguous else ranked[0]), ambiguous


def _default_options(scene: str | None) -> list[dict[str, str]]:
    if scene:
        return SCENE_OPTIONS[scene]
    return [
        SCENE_OPTIONS["quality"][0],
        SCENE_OPTIONS["equipment"][0],
        SCENE_OPTIONS["production"][1],
    ]


def _clarify_node(state: ClarificationState) -> dict[str, Any]:
    started = time.perf_counter()
    question = state["question"].strip()
    normalized = question.lower()
    if any(token in normalized for token in UNSAFE_TERMS):
        raise UnsafeQuestionError("比赛版仅支持分析型只读问题，已拒绝潜在的数据修改或提示词注入请求")

    scene, scene_ambiguous = _detect_scene(question)
    missing: list[str] = []
    if scene is None or scene_ambiguous:
        missing.append("scene")
    if not any(term.lower() in normalized for term in METRIC_TERMS):
        missing.append("metric")
    if not TIME_PATTERN.search(question):
        missing.append("time_range")
    if not any(term.lower() in normalized for term in GOAL_TERMS):
        missing.append("goal")
    has_dimension = any(term in question for term in DIMENSION_TERMS) or any(term in question for term in ("趋势", "分布", "环比", "Pareto", "帕累托"))
    if not has_dimension:
        missing.append("dimension")

    duration_ms = max(1, round((time.perf_counter() - started) * 1000))
    if not missing:
        return {
            "status": "ready",
            "detected_scene": scene,
            "missing_fields": [],
            "prompt": "",
            "options": [],
            "trace": [{
                "node_name": "clarify", "display_name": "问题完整性检查", "status": "completed",
                "duration_ms": duration_ms,
                "summary": f"场景、指标、时间、维度和分析目标完整，路由至 {scene} 问析链路",
                "payload": {"detected_scene": scene, "missing_fields": []},
            }],
        }

    labels = [FIELD_LABELS[field] for field in missing]
    prompt = f"这个问题还缺少{'、'.join(labels)}。请选择一个完整问法，或在原问题中补充后再次提交。"
    return {
        "status": "needs_clarification",
        "detected_scene": scene,
        "missing_fields": missing,
        "prompt": prompt,
        "options": _default_options(scene),
        "trace": [{
            "node_name": "clarify", "display_name": "问题歧义澄清", "status": "waiting",
            "duration_ms": duration_ms,
            "summary": prompt,
            "payload": {"detected_scene": scene, "missing_fields": missing},
        }],
    }


class ClarificationGraph:
    """A deterministic LangGraph gate that runs before any model request."""

    def __init__(self) -> None:
        builder = StateGraph(ClarificationState)
        builder.add_node("clarify", _clarify_node)
        builder.add_edge(START, "clarify")
        builder.add_edge("clarify", END)
        self.graph = builder.compile()

    def invoke(self, question: str) -> ClarificationState:
        return self.graph.invoke({"question": question.strip(), "trace": []})
