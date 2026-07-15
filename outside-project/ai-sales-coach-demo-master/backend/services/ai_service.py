# coding=utf-8
"""
AI 服务层 —— 直接同步调用 Qwen（不走 Celery）
JSON 解析和 schema 校验逻辑移植自 perception-ai/tasks/training_tasks.py
"""

import json
import re
from typing import Any, Dict, List, Tuple

import httpx
from openai import AsyncOpenAI

import config
from prompts.training import build_customer_reply_prompt, build_score_prompt

_FENCE_HEAD_RE = re.compile(r"^\s*```(?:json|JSON)?\s*\n?")
_FENCE_TAIL_RE = re.compile(r"\n?\s*```\s*$")


class ScoreParseError(Exception):
    def __init__(self, msg: str, raw: str = ""):
        super().__init__(msg)
        self.raw = raw


def _parse_score_json(raw: str) -> Dict[str, Any]:
    if not raw:
        raise ScoreParseError("LLM 输出为空")
    content = _FENCE_HEAD_RE.sub("", raw.strip())
    content = _FENCE_TAIL_RE.sub("", content)
    start, end = content.find("{"), content.rfind("}")
    if start == -1 or end <= start:
        raise ScoreParseError(f"未找到 JSON 块: head={content[:80]!r}", raw=raw)
    content = content[start:end + 1]
    try:
        obj = json.loads(content)
    except json.JSONDecodeError as e:
        raise ScoreParseError(f"JSON 解析失败: {e}", raw=raw) from e
    if not isinstance(obj, dict):
        raise ScoreParseError(f"JSON 顶层不是对象", raw=raw)
    return obj


def _validate_score_schema(
    parsed: Dict[str, Any],
    expected_dimensions: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], str, List[str], List[str]]:
    for field, typ in (("dimension_scores", list), ("summary", str), ("highlights", list), ("suggestions", list)):
        if field not in parsed:
            raise ScoreParseError(f"缺字段 {field}")
        if not isinstance(parsed[field], typ):
            raise ScoreParseError(f"字段 {field} 类型错误")

    dim_scores = parsed["dimension_scores"]
    if len(dim_scores) != len(expected_dimensions):
        raise ScoreParseError(f"dimension_scores 长度不匹配: 期望 {len(expected_dimensions)}, 实际 {len(dim_scores)}")

    got_by_id: Dict[Any, Dict[str, Any]] = {}
    for idx, got in enumerate(dim_scores):
        if not isinstance(got, dict):
            raise ScoreParseError(f"dimension_scores[{idx}] 不是对象")
        for k in ("dimension_id", "dimension_name", "score", "comment"):
            if k not in got:
                raise ScoreParseError(f"dimension_scores[{idx}] 缺字段 {k}")
        did = got["dimension_id"]
        if did in got_by_id:
            raise ScoreParseError(f"重复 dimension_id={did}")
        got_by_id[did] = got

    reordered: List[Dict[str, Any]] = []
    for exp in expected_dimensions:
        eid = exp["dimension_id"]
        if eid not in got_by_id:
            raise ScoreParseError(f"缺失维度 dimension_id={eid}")
        got = got_by_id[eid]
        if got["dimension_name"] != exp["dimension_name"]:
            raise ScoreParseError(f"dimension_id={eid} name 不一致")
        score = got["score"]
        if not isinstance(score, int) or score < 0 or score > 100:
            raise ScoreParseError(f"score 非法: {score!r}")
        reordered.append(got)

    return reordered, parsed["summary"], parsed["highlights"], parsed["suggestions"]


def _compute_total_score(dim_scores: List[Dict], expected: List[Dict]) -> int:
    weighted = sum(got["score"] * exp["weight"] / 100.0 for got, exp in zip(dim_scores, expected))
    return int(round(weighted))


def build_fallback_score(dimensions: List[dict], messages: List[dict]) -> Dict[str, Any]:
    """Build a deterministic local score so the demo remains usable without AI."""
    sales_turns = sum(1 for m in messages if m.get("role") == "sales")
    base_score = max(68, min(86, 72 + sales_turns * 3))
    dim_scores = []
    for idx, d in enumerate(dimensions):
        score = max(60, min(92, base_score + ((idx % 3) - 1) * 4))
        dim_scores.append({
            "dimension_id": d["dimension_id"],
            "dimension_name": d["dimension_name"],
            "score": score,
            "comment": f"证据：本轮对话已覆盖客户回应和基础推进；结论：{d['dimension_name']}表现基本达标，仍可继续强化细节。",
        })

    return {
        "total_score": _compute_total_score(dim_scores, dimensions),
        "dimension_scores": dim_scores,
        "summary": "本次练习完成了基本对话闭环，能够回应客户顾虑并推进沟通。后续可继续加强需求追问、价值证明和下一步行动设计。",
        "highlights": ["能够主动回应客户问题", "沟通结构基本清晰"],
        "suggestions": ["先复述客户核心顾虑，再给出有针对性的方案依据", "在客户态度松动时提出低压力的下一步行动"],
    }


def _make_client() -> AsyncOpenAI:
    if not config.OPENAI_API_KEY:
        raise RuntimeError("QWEN_API_KEY 未配置，无法调用真实 AI。")
    return AsyncOpenAI(
        api_key=config.OPENAI_API_KEY,
        base_url=config.OPENAI_BASE_URL,
        http_client=httpx.AsyncClient(timeout=120.0),
    )


async def get_customer_reply(
    persona: str,
    scene_desc: str,
    difficulty: int,
    messages: List[dict],
) -> str:
    """AI 扮演客户，返回客户回复文本"""
    if config.AI_MODE != "real":
        return "我理解你的意思，不过我还是有点担心效果和价格。你能不能结合我的情况，讲讲为什么这个方案更适合我？"

    system_prompt, user_prompt = build_customer_reply_prompt(persona, scene_desc, difficulty, messages)
    async with _make_client() as client:
        resp = await client.chat.completions.create(
            model=config.MODEL_CHAT,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            extra_body={"enable_thinking": False, "enable_search": False},
        )
    return (resp.choices[0].message.content or "").strip()


async def score_session(
    scenario_name: str,
    persona: str,
    scene_desc: str,
    difficulty: int,
    dimensions: List[dict],
    messages: List[dict],
) -> Dict[str, Any]:
    """评分，返回 {total_score, dimension_scores, summary, highlights, suggestions}"""
    if config.AI_MODE != "real" or not config.OPENAI_API_KEY:
        return build_fallback_score(dimensions, messages)

    max_retries = 3
    for retry in range(max_retries):
        system_prompt, user_prompt = build_score_prompt(
            scenario_name, persona, scene_desc, difficulty, dimensions, messages, retry_round=retry
        )
        async with _make_client() as client:
            resp = await client.chat.completions.create(
                model=config.MODEL_SCORE,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                response_format={"type": "json_object"},
                extra_body={"enable_thinking": True, "enable_search": False, "seed": 42},
            )
        raw = (resp.choices[0].message.content or "").strip()
        try:
            parsed = _parse_score_json(raw)
            dim_scores, summary, highlights, suggestions = _validate_score_schema(parsed, dimensions)
            total_score = _compute_total_score(dim_scores, dimensions)
            return {
                "total_score": total_score,
                "dimension_scores": dim_scores,
                "summary": summary,
                "highlights": highlights,
                "suggestions": suggestions,
            }
        except ScoreParseError:
            if retry == max_retries - 1:
                raise
    raise ScoreParseError("重试次数耗尽")
