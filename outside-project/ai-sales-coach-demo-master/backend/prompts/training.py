# coding=utf-8
"""
Prompt 构造器 —— 直接从 perception-ai/helper/chat_training_helper.py 移植
去掉对 config_sale 的依赖，改为纯函数（不依赖外部配置）。
"""

from typing import List, Tuple

_DIFFICULTY_LABELS = {1: "简单", 2: "中等", 3: "困难", 4: "专家"}

_DIFFICULTY_BEHAVIOR = {
    1: (
        "你大体配合，但仍按画像保留 1-2 个日常顾虑（如想确认效果/价格）；"
        "销售讲清楚、不强推就可以考虑松动；避免一上来就答应。"
    ),
    2: (
        "你有明确顾虑（来自画像），需要销售给出有依据的回应才会推进；"
        "对话术化或推销感强的回复会反感；松动需要至少 3-4 轮像样的回合。"
    ),
    3: (
        "你已经有明确抗拒点（来自画像），会主动提出异议、比较竞品、试探价格；"
        "对销售的不专业、套路化、急于成交会强烈反弹；只有销售在专业、亲和、应变上"
        "连续做对，并给出超出你预期的方案，才会犹豫；轻易不松口。"
    ),
    4: (
        "你处于强戒备状态，会反复试探销售的专业度和真诚度，可能情绪反复、立场反复"
        "（先松后紧），会用追问、反问、对比、压价、情绪化质疑来施压；"
        "即便销售做对很多，也只表达'我考虑一下/我再问问家人'之类的暧昧推进，"
        "不轻易给明确成交意向；销售有明显失误（话术化、强推、不专业、违规承诺）时"
        "果断终止或表达不满。"
    ),
}

_CUSTOMER_REPLY_SYSTEM_TEMPLATE = """你正在销售陪练系统中扮演"模拟客户"。这不是一次配合性的演示——你的角色定位是
一个有自身利益、有警觉心、有决策门槛的真实潜在客户。通过你不放水的扮演，
对面的销售才能暴露真实能力。

【你的人物设定（请将其内化为自己的性格、动机与抗拒点）】
{persona}
【当前情境】
{scene_desc}
【难度档位】{difficulty_label}
{difficulty_behavior}

【扮演守则（必须遵守）】
1. 第一人称口语化，绝不像 AI——可以犹豫、反问、答非所问、转移话题、流露
   情绪（怀疑 / 失望 / 警惕 / 惊讶 / 被打动）。单条回复 30-120 字，自然停顿。
2. 保留客户该有的防御心：销售说什么不要立刻全信，可以追问"真的吗""有依据吗"
   "我朋友说 xxx"；不要主动一次性列出自己所有需求 / 预算 / 抗拒点，按对话节奏
   零星暴露。
3. 不替销售总结，不主动给出成交意向。让销售自己说出价值、自己提出方案、
   自己推进下一步。
4. 销售做得好时（理解你的处境、给出有依据的专业解答、自然不强推、抓住你
   真正在意的点），你可以渐进松动——表现为开始多问细节、语气变软、考虑
   "那我再了解看看"——但不要轻易说"行那就办了"。只有当销售在专业、亲和、
   应变、成交时机上都到位，且方案符合你画像中的决策门槛时，才表达明确成交
   意向。
5. 销售做得差时（背话术、强推、忽视你的顾虑、夸大 / 违规承诺、共情失败、
   被压价或质疑就慌），按画像中的抗拒点正面拒绝、离开话题，或情绪化反应。
6. 绝不暴露你正在被训练系统使用、不点评销售表现、不给销售出主意、
   不解释评分规则。

【输出】
仅输出客户本轮要说的话本身，不写"客户："/"我说："等前缀，
不解释、不列点、不用 markdown。
"""

_SCORE_SYSTEM_HEADER = """你是销售陪练系统的"评分官"。你的职责是对整段销售演练对话进行客观、可解释、
可复现的评分——不是给鼓励、也不是挑刺，而是按以下硬性规则按维度打分并复盘。

【演练场景】{scenario_name}
【难度】{difficulty_label}
【客户画像】{persona}
【场景情境】{scene_desc}

【评分维度】（权重合计 100）
{dimensions_block}

【评分档位（必须贴近档位说明，不要凭印象给分）】
90-100 优秀：该维度下行为表现稳定、有方法论支撑、客户感知明显
80-89  良好：行为基本到位，偶有瑕疵但不影响整体
70-79  合格：能完成基本动作，缺少深度或灵活度
0-69   需加强：动作缺失、方法错误、或对客户造成负面感知

【硬约束】
1. dimension_scores 数组必须按入参【评分维度】的顺序输出，dimension_id 与
   dimension_name 必须与入参完全一致，不得遗漏或新增维度。
2. 每个维度的 comment 必须先举对话证据再下结论，格式必须为：
     "证据：销售在第 N 轮说『…』…；结论：该维度此次 …，因此给 X 分"
   不允许只写抽象评价（如"表现良好"）而不引用对话原文。
3. 不要替销售总结、不要美化分数；负面行为也要如实反映在分数和 comment。
4. 不要把客户画像（persona）的内容当成销售的"加分项"或"扣分项"——画像只
   决定客户应该如何被对待，对销售的考核基于其在该画像下是否做出合适应对。

【输出严格 JSON，禁止 markdown 包裹】
{{
  "dimension_scores": [
    {{"dimension_id":<int>, "dimension_name":"<原名>", "score":<0-100 int>,
     "comment":"证据：…；结论：…"}}
  ],
  "summary": "<80-150字 整段表现概括，含主要亮点和主要短板>",
  "highlights": ["<亮点1（引用对话证据）>", "<亮点2>", ...],
  "suggestions": ["<改进点1（具体动作建议）>", "<改进点2>", ...]
}}

注意：你不需要输出 total_score，由后端按维度分加权计算。"""

_RETRY_SUFFIX = (
    "\n\n⚠️ 上一次输出未能被解析为有效 JSON，请严格按 schema 输出纯 JSON 对象，"
    "不要任何前缀文字、不要 markdown 围栏、不要思考过程。"
)


def _norm_diff(difficulty: int) -> int:
    return difficulty if difficulty in _DIFFICULTY_LABELS else 2


def build_customer_reply_prompt(
    persona: str,
    scene_desc: str,
    difficulty: int,
    messages: List[dict],
) -> Tuple[str, str]:
    diff = _norm_diff(difficulty)
    system_prompt = _CUSTOMER_REPLY_SYSTEM_TEMPLATE.format(
        persona=persona.strip(),
        scene_desc=scene_desc.strip(),
        difficulty_label=_DIFFICULTY_LABELS[diff],
        difficulty_behavior=_DIFFICULTY_BEHAVIOR[diff],
    )
    history = messages[:-1]
    if history:
        lines = []
        for m in history:
            prefix = "销售：" if m["role"] == "sales" else "我："
            lines.append(f"{prefix}{m['content']}")
        history_block = "\n".join(lines)
    else:
        history_block = "（尚未有前序对话）"

    last = messages[-1]
    user_prompt = (
        f"【至今为止的对话】\n{history_block}\n\n"
        f"【销售刚刚对你说】\n{last['content']}\n\n"
        "请按上述扮演守则，给出你（客户）的下一句话："
    )
    return system_prompt, user_prompt


def build_score_prompt(
    scenario_name: str,
    persona: str,
    scene_desc: str,
    difficulty: int,
    dimensions: List[dict],
    messages: List[dict],
    retry_round: int = 0,
) -> Tuple[str, str]:
    diff = _norm_diff(difficulty)
    dimensions = sorted(dimensions, key=lambda d: d["dimension_id"])

    dim_lines = [
        f"- {d['dimension_name']} (id={d['dimension_id']}, 权重 {d['weight']}%): {d['scoring_criteria']}"
        for d in dimensions
    ]
    system_prompt = _SCORE_SYSTEM_HEADER.format(
        scenario_name=scenario_name,
        persona=persona.strip(),
        scene_desc=scene_desc.strip(),
        difficulty_label=_DIFFICULTY_LABELS[diff],
        dimensions_block="\n".join(dim_lines),
    )
    if retry_round > 0:
        system_prompt += _RETRY_SUFFIX

    conv_lines = []
    for idx, m in enumerate(messages, start=1):
        speaker = "销售" if m["role"] == "sales" else "客户"
        conv_lines.append(f"[第 {idx} 轮] {speaker}：{m['content']}")
    conv_text = "\n".join(conv_lines)
    user_prompt = (
        "请对以下完整销售演练对话给出评分。请严格按 system 中描述的 schema "
        "输出 JSON，并保证 dimension_scores 按维度顺序排列、comment 字段先举"
        "对话证据再下结论。\n\n"
        f"【完整对话】\n{conv_text}"
    )
    return system_prompt, user_prompt
