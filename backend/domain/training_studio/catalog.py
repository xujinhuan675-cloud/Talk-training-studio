"""Pure domain models for the communication training studio catalog."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from domain.common.exceptions import DomainValidationException


class ScenarioCategory(StrEnum):
    INTERVIEW = "interview"
    SALES = "sales"
    NEGOTIATION = "negotiation"
    WORKPLACE = "workplace"
    PRODUCT_MANAGEMENT = "product_management"


class Difficulty(StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class ExpressionFramework(StrEnum):
    PREP = "prep"
    STAR = "star"
    SCQA = "scqa"
    PYRAMID = "pyramid"


class RubricDimension(StrEnum):
    SUBSTANCE = "substance"
    STRUCTURE = "structure"
    RELEVANCE = "relevance"
    CREDIBILITY = "credibility"
    DIFFERENTIATION = "differentiation"


DEFAULT_RUBRIC_VERSION = "interview-five-dimension-v1"

DEFAULT_RUBRIC_WEIGHTS: dict[ScenarioCategory, dict[RubricDimension, float]] = {
    ScenarioCategory.INTERVIEW: {
        RubricDimension.SUBSTANCE: 0.30,
        RubricDimension.STRUCTURE: 0.20,
        RubricDimension.RELEVANCE: 0.20,
        RubricDimension.CREDIBILITY: 0.15,
        RubricDimension.DIFFERENTIATION: 0.15,
    },
    ScenarioCategory.SALES: {
        RubricDimension.SUBSTANCE: 0.25,
        RubricDimension.STRUCTURE: 0.15,
        RubricDimension.RELEVANCE: 0.25,
        RubricDimension.CREDIBILITY: 0.20,
        RubricDimension.DIFFERENTIATION: 0.15,
    },
    ScenarioCategory.NEGOTIATION: {
        RubricDimension.SUBSTANCE: 0.25,
        RubricDimension.STRUCTURE: 0.20,
        RubricDimension.RELEVANCE: 0.20,
        RubricDimension.CREDIBILITY: 0.20,
        RubricDimension.DIFFERENTIATION: 0.15,
    },
    ScenarioCategory.WORKPLACE: {
        RubricDimension.SUBSTANCE: 0.25,
        RubricDimension.STRUCTURE: 0.20,
        RubricDimension.RELEVANCE: 0.25,
        RubricDimension.CREDIBILITY: 0.20,
        RubricDimension.DIFFERENTIATION: 0.10,
    },
    ScenarioCategory.PRODUCT_MANAGEMENT: {
        RubricDimension.SUBSTANCE: 0.22,
        RubricDimension.STRUCTURE: 0.18,
        RubricDimension.RELEVANCE: 0.25,
        RubricDimension.CREDIBILITY: 0.20,
        RubricDimension.DIFFERENTIATION: 0.15,
    },
}


@dataclass(frozen=True)
class RolePreset:
    value: str
    category: ScenarioCategory
    label: str
    description: str
    default_level: str
    default_focus: list[str]
    default_question_type_ratios: dict[str, float]


@dataclass(frozen=True)
class ScenarioPreset:
    value: str
    category: ScenarioCategory
    label: str
    description: str
    counterpart_role: str
    context_prompt: str
    suggested_role_values: list[str]
    default_framework: ExpressionFramework
    default_difficulty: Difficulty
    default_question_type_ratios: dict[str, float]


@dataclass(frozen=True)
class ScenarioTrainingPersona:
    name: str
    role: str
    style: str


@dataclass(frozen=True)
class ScenarioTrainingTemplate:
    id: str
    title: str
    description: str
    customer_profile: str
    difficulty: str
    category: str
    required: bool
    status: str
    opening_line: str
    persona: ScenarioTrainingPersona
    learner_role: str
    framework: ExpressionFramework
    training_points: list[str]
    score: int | None = None
    last_practiced_at: str | None = None


SCENARIO_TRAINING_TEMPLATES: tuple[ScenarioTrainingTemplate, ...] = (
    ScenarioTrainingTemplate(
        id="daily-upward-results-report",
        title="向上今日成果汇报",
        description="向主管用 3 分钟汇报今日关键进展、风险和明日计划，争取清晰反馈与资源支持。",
        customer_profile="时间有限的直属主管，关注结果、风险、优先级和是否需要介入。",
        difficulty="medium",
        category="workplace",
        required=False,
        status="not_started",
        opening_line="我现在只有几分钟，你直接说今天最重要的成果、风险，以及你明天准备怎么推进。",
        persona=ScenarioTrainingPersona(
            name="周经理",
            role="关注结果的直属主管",
            style="节奏快、追问重点，会要求用事实和数字说明影响，不接受泛泛汇报。",
        ),
        learner_role="Team Member",
        framework=ExpressionFramework.PYRAMID,
        training_points=["先给结论和成果", "用事实说明影响", "暴露风险并提出下一步请求"],
    ),
    ScenarioTrainingTemplate(
        id="new-customer-discount",
        title="新客优惠咨询",
        description="门店新客想了解价格、服务边界和是否值得当场下单。",
        customer_profile="首次到店客户，预算敏感，愿意尝试但担心被推销。",
        difficulty="easy",
        category="sales",
        required=True,
        status="not_started",
        opening_line="你好，我看到你们门口说有新客优惠，能介绍一下吗？",
        persona=ScenarioTrainingPersona(
            name="李女士",
            role="预算敏感的新客",
            style="友好但谨慎，会追问价格、隐性费用和是否马上决策。",
        ),
        learner_role="Salesperson",
        framework=ExpressionFramework.PREP,
        training_points=["快速建立信任", "清楚解释优惠边界", "用开放问题确认真实需求"],
    ),
    ScenarioTrainingTemplate(
        id="enterprise-demo-objection",
        title="企业客户 Demo 异议",
        description="客户认可价值，但担心上线周期、集成成本和团队采用率。",
        customer_profile="中型企业部门负责人，有预算但需要降低实施风险。",
        difficulty="medium",
        category="sales",
        required=True,
        status="in_progress",
        score=76,
        last_practiced_at="2026-07-12",
        opening_line="方案听起来不错，但我们之前导入工具都很慢，你们怎么保证不会拖住团队？",
        persona=ScenarioTrainingPersona(
            name="陈总",
            role="企业采购决策人",
            style="关注风险、落地成本和团队阻力，会要求具体案例与推进计划。",
        ),
        learner_role="Salesperson",
        framework=ExpressionFramework.SCQA,
        training_points=["识别真实反对点", "用证据化案例降低风险", "推进下一步共同计划"],
    ),
    ScenarioTrainingTemplate(
        id="refund-service-recovery",
        title="退款与服务补救",
        description="客户体验不佳要求退款，需要稳定情绪、确认事实并给出补救方案。",
        customer_profile="已购买客户，情绪不满，认为服务承诺没有兑现。",
        difficulty="hard",
        category="customer_service",
        required=True,
        status="not_started",
        opening_line="我上次体验很差，如果今天不给我一个说法，我就要求全额退款。",
        persona=ScenarioTrainingPersona(
            name="王先生",
            role="不满的已购客户",
            style="情绪强烈，容易打断，只有感到被理解后才愿意讨论方案。",
        ),
        learner_role="Customer Success Specialist",
        framework=ExpressionFramework.PREP,
        training_points=["先接住情绪", "复述事实并确认缺口", "给出可执行补救选项"],
    ),
    ScenarioTrainingTemplate(
        id="renewal-price-negotiation",
        title="续约价格谈判",
        description="老客户准备续约，但拿竞品价格压价，要求额外折扣。",
        customer_profile="年度续约客户，使用频率高，采购希望压低预算。",
        difficulty="expert",
        category="negotiation",
        required=False,
        status="completed",
        score=88,
        last_practiced_at="2026-07-10",
        opening_line="竞品给了我们更低的价格，如果你们不能再降 20%，我们很难续约。",
        persona=ScenarioTrainingPersona(
            name="赵经理",
            role="价格强势的采购经理",
            style="强势、关注让步空间，会用竞品和预算压力测试底线。",
        ),
        learner_role="Account Manager",
        framework=ExpressionFramework.PYRAMID,
        training_points=["守住价值锚点", "交换条件而不是单向让步", "明确 BATNA 和下一步"],
    ),
    ScenarioTrainingTemplate(
        id="recruiter-sales-interview",
        title="销售岗位初筛",
        description="候选人需要在短时间内讲清楚过往业绩、销售方法和动机。",
        customer_profile="招聘方初筛，关注表达结构、业绩真实性和岗位匹配。",
        difficulty="medium",
        category="interview",
        required=False,
        status="not_started",
        opening_line="请你先用一分钟介绍一下自己，重点讲讲最近一段销售经历。",
        persona=ScenarioTrainingPersona(
            name="周 HR",
            role="销售岗位招聘初筛官",
            style="时间紧、问题直接，会追问业绩数字、客户类型和离职动机。",
        ),
        learner_role="Sales Candidate",
        framework=ExpressionFramework.STAR,
        training_points=["用结果开场", "用 STAR 讲清楚关键案例", "解释动机和岗位匹配"],
    ),
    ScenarioTrainingTemplate(
        id="ai-web3-agent-pm-comprehensive-interview",
        title="AI Agent + Web3 产品经理综合面试",
        description=(
            "围绕 AI Agent 产品岗位进行一场完整综合面试，覆盖自我介绍、求职动机、"
            "XStable 真实工作经历、NOFX 项目边界、OpenEvolve Agent 机制理解、"
            "AI + Web3 交易产品判断和毕业一年超预期能力证明。"
        ),
        customer_profile=(
            "AI Agent / AI 产品方向招聘面试官，熟悉 Web3 交易、海外信息流和智能体产品，"
            "关注候选人的真实贡献、证据密度、技术边界、风险意识和岗位匹配度。"
        ),
        difficulty="hard",
        category="interview",
        required=False,
        status="not_started",
        opening_line="请你先用 90 秒介绍自己，重点说明为什么你适合 AI Agent / Web3 交易产品方向。",
        persona=ScenarioTrainingPersona(
            name="顾面试官",
            role="AI Agent 产品招聘面试官",
            style=(
                "结构化、证据导向、追问真实贡献和边界。按完整面试推进：先听自我介绍，"
                "再深挖 XStable、NOFX、OpenEvolve，随后用压力问题测试岗位匹配、"
                "交易产品理解、Agent 机制判断和毕业一年超预期表达。"
            ),
        ),
        learner_role="AI Agent Product Manager Candidate",
        framework=ExpressionFramework.STAR,
        training_points=[
            "用 AI Agent 为主线，清楚说明 Web3 交易、海外信息流和区块链经验如何形成差异化",
            "讲清 XStable 的岗位职责、产品模块、交易链路、链上数据、TG 场景和可脱敏结果",
            "把 NOFX 表达为基于开源项目的本地二次开发、产品拆解、联调验证和作品集包装",
            "用 OpenEvolve 证明对 Agent 记忆、技能晋升、失败回流、评测和治理机制的理解",
            "面对压力追问时，用具体案例说明毕业一年为什么已接近或达到超预期线",
            "在回答中保留风险边界，不夸大所有权、结果数据或无法公开的公司信息",
        ],
    ),
    ScenarioTrainingTemplate(
        id="angry-vip-priority",
        title="VIP 优先级升级",
        description="重点客户认为自己被忽视，要求立即升级优先级。",
        customer_profile="高价值客户负责人，业务影响大，对响应速度非常敏感。",
        difficulty="hard",
        category="customer_service",
        required=False,
        status="not_started",
        opening_line="我们是你们的大客户，这个问题拖了三天，为什么还没有优先处理？",
        persona=ScenarioTrainingPersona(
            name="沈总",
            role="高价值客户负责人",
            style="压迫感强，要求承诺明确时间表，不接受含糊解释。",
        ),
        learner_role="Customer Success Manager",
        framework=ExpressionFramework.SCQA,
        training_points=["承认影响而不甩锅", "澄清优先级与责任人", "给出可追踪的恢复计划"],
    ),
    ScenarioTrainingTemplate(
        id="budget-freeze-expansion",
        title="预算冻结下的扩容推进",
        description="客户认可价值，但财务宣布预算冻结，你需要找到低风险扩容或分阶段试点路径。",
        customer_profile="企业客户业务负责人和财务共同参与，认可痛点但对新增支出非常谨慎。",
        difficulty="hard",
        category="sales",
        required=False,
        status="not_started",
        opening_line="今年预算基本冻结了。除非你能证明这件事不做会损失更大，否则我很难追加采购。",
        persona=ScenarioTrainingPersona(
            name="李总",
            role="谨慎的企业预算负责人",
            style="理性、压成本、要求 ROI 和退出机制，会持续追问试点范围与失败成本。",
        ),
        learner_role="Account Executive",
        framework=ExpressionFramework.PYRAMID,
        training_points=["先确认业务损失", "把扩容拆成低风险阶段", "明确成功指标和退出机制"],
    ),
    ScenarioTrainingTemplate(
        id="cross-team-roadmap-tradeoff",
        title="跨团队路线图取舍",
        description="销售、研发和设计对路线优先级意见冲突，需要产品经理解释判断标准并促成决定。",
        customer_profile="跨部门评审会，多个角色各自带着收入、质量、体验和交付压力。",
        difficulty="hard",
        category="workplace",
        required=False,
        status="not_started",
        opening_line="销售说大客户功能必须插队，研发说排期已经满了。你作为产品负责人，准备怎么定优先级？",
        persona=ScenarioTrainingPersona(
            name="赵睿",
            role="跨部门路线图评审主持人",
            style="要求先给判断框架，再给取舍结论；会追问证据、机会成本和 owner。",
        ),
        learner_role="Product Manager",
        framework=ExpressionFramework.SCQA,
        training_points=["先对齐共同目标", "公开优先级判断标准", "给出取舍和补偿方案"],
    ),
    ScenarioTrainingTemplate(
        id="project-scope-creep-boundary",
        title="项目范围蔓延边界沟通",
        description="客户在项目中途持续追加需求，你需要守住范围边界，同时维护合作关系。",
        customer_profile="合作客户项目负责人，认为新增需求只是“小改动”，但实际会影响交付周期。",
        difficulty="medium",
        category="negotiation",
        required=False,
        status="not_started",
        opening_line="这个需求很小，你们顺手一起做了吧。我们上线时间不能再往后拖。",
        persona=ScenarioTrainingPersona(
            name="许经理",
            role="持续追加范围的客户项目负责人",
            style="表面合作但会施压，希望把新增需求塞进原交付范围。",
        ),
        learner_role="Project Lead",
        framework=ExpressionFramework.PREP,
        training_points=["承认需求价值", "解释范围/时间/质量三角", "提出变更单或替代路径"],
    ),
    ScenarioTrainingTemplate(
        id="service-apology-retention",
        title="投诉后的留存沟通",
        description="客户刚经历服务失误，准备取消合作，需要先修复信任再谈留存。",
        customer_profile="高价值客户，情绪不满，愿意听解释但不接受空泛道歉。",
        difficulty="hard",
        category="customer_service",
        required=False,
        status="not_started",
        opening_line="你们上次说会解决，结果还是没人跟进。现在我已经不想继续合作了。",
        persona=ScenarioTrainingPersona(
            name="唐女士",
            role="准备流失的高价值客户",
            style="失望、警惕，会要求明确补救动作和后续责任人。",
        ),
        learner_role="Customer Success Manager",
        framework=ExpressionFramework.SCQA,
        training_points=["先承认影响和责任", "给出具体恢复计划", "用后续机制重建信任"],
    ),
)


PRODUCT_MANAGEMENT_ROLE_PRESETS: tuple[RolePreset, ...] = (
    RolePreset(
        value="core_pm",
        category=ScenarioCategory.PRODUCT_MANAGEMENT,
        label="Product Manager",
        description="Owns discovery, roadmap trade-offs, and cross-functional alignment.",
        default_level="Mid-level",
        default_focus=["user research", "metrics", "roadmap", "PRD"],
        default_question_type_ratios={"behavioral": 30, "craft": 45, "pressure": 25},
    ),
    RolePreset(
        value="growth_pm",
        category=ScenarioCategory.PRODUCT_MANAGEMENT,
        label="Growth Product Manager",
        description="Frames activation, retention, experiments, and funnel decisions.",
        default_level="Senior",
        default_focus=["activation", "retention", "experimentation", "funnel analytics"],
        default_question_type_ratios={"behavioral": 25, "craft": 50, "pressure": 25},
    ),
    RolePreset(
        value="platform_pm",
        category=ScenarioCategory.PRODUCT_MANAGEMENT,
        label="Platform Product Manager",
        description="Balances developer experience, API contracts, reliability, and internal scale.",
        default_level="Senior",
        default_focus=["API platform", "developer experience", "reliability", "internal tools"],
        default_question_type_ratios={"behavioral": 25, "craft": 50, "pressure": 25},
    ),
    RolePreset(
        value="ai_pm",
        category=ScenarioCategory.PRODUCT_MANAGEMENT,
        label="AI Product Manager",
        description="Turns model capability, evals, privacy, and cost into shippable product bets.",
        default_level="Senior",
        default_focus=["LLM features", "evaluation", "privacy", "model cost"],
        default_question_type_ratios={"behavioral": 25, "craft": 45, "pressure": 30},
    ),
)


INTERVIEW_ROLE_PRESETS: tuple[RolePreset, ...] = (
    RolePreset(
        value="recruiter_screen",
        category=ScenarioCategory.INTERVIEW,
        label="Recruiter screen",
        description="Checks motivation, fit, salary range, timeline, and concise career story.",
        default_level="Mid-level",
        default_focus=["career story", "motivation", "role fit", "salary expectations"],
        default_question_type_ratios={"behavioral": 55, "craft": 20, "pressure": 25},
    ),
    RolePreset(
        value="hiring_manager",
        category=ScenarioCategory.INTERVIEW,
        label="Hiring manager",
        description="Tests product judgment, ownership, impact, and team fit.",
        default_level="Senior",
        default_focus=["product judgment", "ownership", "impact", "team fit"],
        default_question_type_ratios={"behavioral": 35, "craft": 40, "pressure": 25},
    ),
    RolePreset(
        value="product_case_interviewer",
        category=ScenarioCategory.INTERVIEW,
        label="Product case interviewer",
        description="Runs product sense, prioritization, metrics, and structured problem-solving cases.",
        default_level="Senior",
        default_focus=["product sense", "prioritization", "metrics", "problem solving"],
        default_question_type_ratios={"behavioral": 15, "craft": 60, "pressure": 25},
    ),
    RolePreset(
        value="cross_functional_interviewer",
        category=ScenarioCategory.INTERVIEW,
        label="Cross-functional interviewer",
        description="Looks for collaboration with engineering, design, data, sales, and operations.",
        default_level="Senior",
        default_focus=["collaboration", "conflict resolution", "technical trade-offs", "influence"],
        default_question_type_ratios={"behavioral": 40, "craft": 35, "pressure": 25},
    ),
    RolePreset(
        value="bar_raiser",
        category=ScenarioCategory.INTERVIEW,
        label="Bar raiser",
        description="Applies high-pressure follow-ups on ambiguity, leadership, and evidence quality.",
        default_level="Senior",
        default_focus=["leadership", "ambiguity", "evidence quality", "decision reasoning"],
        default_question_type_ratios={"behavioral": 35, "craft": 30, "pressure": 35},
    ),
)


PRODUCT_MANAGEMENT_SCENARIO_PRESETS: tuple[ScenarioPreset, ...] = (
    ScenarioPreset(
        value="roadmap_prioritization",
        category=ScenarioCategory.PRODUCT_MANAGEMENT,
        label="Roadmap prioritization",
        description="Say no, defend sequencing, and keep stakeholders aligned.",
        counterpart_role="Head of Sales pushing for a large enterprise request",
        context_prompt=(
            "The stakeholder wants a high-revenue customer request moved above committed roadmap "
            "items. Practice explaining prioritization criteria, trade-offs, and next steps."
        ),
        suggested_role_values=["core_pm", "growth_pm"],
        default_framework=ExpressionFramework.PYRAMID,
        default_difficulty=Difficulty.MEDIUM,
        default_question_type_ratios={"behavioral": 25, "craft": 45, "pressure": 30},
    ),
    ScenarioPreset(
        value="prd_review",
        category=ScenarioCategory.PRODUCT_MANAGEMENT,
        label="PRD review",
        description="Clarify scope, acceptance criteria, and engineering trade-offs.",
        counterpart_role="Engineering lead challenging feasibility and edge cases",
        context_prompt=(
            "A PRD is ready for review, but engineering is concerned about ambiguous scope, "
            "dependency risk, and missing acceptance criteria."
        ),
        suggested_role_values=["core_pm", "platform_pm", "ai_pm"],
        default_framework=ExpressionFramework.SCQA,
        default_difficulty=Difficulty.MEDIUM,
        default_question_type_ratios={"behavioral": 20, "craft": 55, "pressure": 25},
    ),
    ScenarioPreset(
        value="launch_risk_review",
        category=ScenarioCategory.PRODUCT_MANAGEMENT,
        label="Launch risk review",
        description="Make a go/no-go recommendation under imperfect information.",
        counterpart_role="Executive sponsor asking whether to launch this week",
        context_prompt=(
            "The release is close, but quality signals and operational readiness are mixed. "
            "Practice a crisp go/no-go recommendation with risks, mitigations, and ownership."
        ),
        suggested_role_values=["core_pm", "ai_pm", "platform_pm"],
        default_framework=ExpressionFramework.PREP,
        default_difficulty=Difficulty.HARD,
        default_question_type_ratios={"behavioral": 20, "craft": 45, "pressure": 35},
    ),
    ScenarioPreset(
        value="user_feedback_triage",
        category=ScenarioCategory.PRODUCT_MANAGEMENT,
        label="User feedback triage",
        description="Separate signal from anecdotes and turn feedback into action.",
        counterpart_role="Customer success lead escalating urgent user complaints",
        context_prompt=(
            "Customer success brings urgent feedback from several accounts. Practice asking "
            "diagnostic questions, separating severity from frequency, and proposing a follow-up plan."
        ),
        suggested_role_values=["core_pm", "growth_pm"],
        default_framework=ExpressionFramework.SCQA,
        default_difficulty=Difficulty.MEDIUM,
        default_question_type_ratios={"behavioral": 30, "craft": 45, "pressure": 25},
    ),
    ScenarioPreset(
        value="executive_update",
        category=ScenarioCategory.PRODUCT_MANAGEMENT,
        label="Executive update",
        description="Communicate progress, risk, asks, and decision options clearly.",
        counterpart_role="CEO asking for impact, risk, and why the plan changed",
        context_prompt=(
            "You need to update leadership on a product initiative whose timeline and scope have "
            "changed. Practice leading with the decision needed, evidence, and trade-off options."
        ),
        suggested_role_values=["core_pm", "growth_pm", "ai_pm"],
        default_framework=ExpressionFramework.PYRAMID,
        default_difficulty=Difficulty.HARD,
        default_question_type_ratios={"behavioral": 20, "craft": 40, "pressure": 40},
    ),
    ScenarioPreset(
        value="stakeholder_conflict",
        category=ScenarioCategory.PRODUCT_MANAGEMENT,
        label="Stakeholder conflict",
        description="Align design, engineering, and business when incentives diverge.",
        counterpart_role="Cross-functional stakeholder panel with conflicting priorities",
        context_prompt=(
            "Design wants quality, engineering wants scope control, and business wants speed. "
            "Practice reframing the shared goal, exposing constraints, and landing a decision."
        ),
        suggested_role_values=["core_pm", "platform_pm"],
        default_framework=ExpressionFramework.SCQA,
        default_difficulty=Difficulty.HARD,
        default_question_type_ratios={"behavioral": 35, "craft": 35, "pressure": 30},
    ),
)


INTERVIEW_SCENARIO_PRESETS: tuple[ScenarioPreset, ...] = (
    ScenarioPreset(
        value="self_intro_pitch",
        category=ScenarioCategory.INTERVIEW,
        label="Self-introduction pitch",
        description="Open with a crisp career story tailored to a PM role.",
        counterpart_role="Recruiter checking role fit, motivation, and communication clarity",
        context_prompt=(
            "Practice a 60-90 second product manager self-introduction. The interviewer should "
            "test motivation, role fit, career transitions, and whether the story is concise."
        ),
        suggested_role_values=["recruiter_screen", "hiring_manager"],
        default_framework=ExpressionFramework.PYRAMID,
        default_difficulty=Difficulty.EASY,
        default_question_type_ratios={"behavioral": 60, "craft": 15, "pressure": 25},
    ),
    ScenarioPreset(
        value="resume_deep_dive",
        category=ScenarioCategory.INTERVIEW,
        label="Resume deep dive",
        description="Defend project impact, scope, metrics, and your exact contribution.",
        counterpart_role="Hiring manager probing resume claims and product ownership",
        context_prompt=(
            "The interviewer picks one product project from the resume and drills into context, "
            "your role, trade-offs, impact metrics, and what you would do differently."
        ),
        suggested_role_values=["hiring_manager", "bar_raiser"],
        default_framework=ExpressionFramework.STAR,
        default_difficulty=Difficulty.MEDIUM,
        default_question_type_ratios={"behavioral": 40, "craft": 35, "pressure": 25},
    ),
    ScenarioPreset(
        value="product_sense_case",
        category=ScenarioCategory.INTERVIEW,
        label="Product sense case",
        description="Structure a product design or improvement case from user to metrics.",
        counterpart_role="Product case interviewer testing user insight, prioritization, and metrics",
        context_prompt=(
            "Run a product sense case for a PM candidate. Push for target users, problem framing, "
            "solution options, prioritization, success metrics, and risks."
        ),
        suggested_role_values=["product_case_interviewer", "hiring_manager"],
        default_framework=ExpressionFramework.SCQA,
        default_difficulty=Difficulty.MEDIUM,
        default_question_type_ratios={"behavioral": 15, "craft": 60, "pressure": 25},
    ),
    ScenarioPreset(
        value="metrics_growth_case",
        category=ScenarioCategory.INTERVIEW,
        label="Metrics and growth case",
        description="Diagnose metric movement and propose experiments with trade-offs.",
        counterpart_role="Growth-oriented product interviewer testing data reasoning",
        context_prompt=(
            "The interviewer gives a product metric change or growth problem. Practice clarifying "
            "the metric tree, diagnosing causes, proposing experiments, and naming guardrails."
        ),
        suggested_role_values=["product_case_interviewer", "bar_raiser"],
        default_framework=ExpressionFramework.SCQA,
        default_difficulty=Difficulty.HARD,
        default_question_type_ratios={"behavioral": 10, "craft": 65, "pressure": 25},
    ),
    ScenarioPreset(
        value="behavioral_leadership",
        category=ScenarioCategory.INTERVIEW,
        label="Behavioral leadership",
        description="Answer conflict, failure, influence, and ambiguity questions with STAR evidence.",
        counterpart_role="Bar raiser testing leadership, ownership, and evidence quality",
        context_prompt=(
            "Run a behavioral PM interview covering conflict, failure, influence without authority, "
            "ambiguity, and learning. Require concrete examples, metrics, and reflection."
        ),
        suggested_role_values=["bar_raiser", "cross_functional_interviewer"],
        default_framework=ExpressionFramework.STAR,
        default_difficulty=Difficulty.HARD,
        default_question_type_ratios={"behavioral": 65, "craft": 10, "pressure": 25},
    ),
    ScenarioPreset(
        value="cross_functional_round",
        category=ScenarioCategory.INTERVIEW,
        label="Cross-functional round",
        description="Show how you work with engineering, design, data, and business teams.",
        counterpart_role="Engineering and design interviewers testing collaboration patterns",
        context_prompt=(
            "Simulate a cross-functional PM round. Ask about technical trade-offs, design conflict, "
            "data uncertainty, stakeholder pressure, and how the candidate drives alignment."
        ),
        suggested_role_values=["cross_functional_interviewer", "hiring_manager"],
        default_framework=ExpressionFramework.PREP,
        default_difficulty=Difficulty.MEDIUM,
        default_question_type_ratios={"behavioral": 45, "craft": 30, "pressure": 25},
    ),
    ScenarioPreset(
        value="offer_negotiation",
        category=ScenarioCategory.INTERVIEW,
        label="Offer negotiation",
        description="Discuss compensation, level, scope, and timeline without losing goodwill.",
        counterpart_role="Recruiter negotiating compensation, level, and decision timeline",
        context_prompt=(
            "Practice an offer-stage conversation. The interviewer should probe salary expectations, "
            "competing processes, level concerns, timeline, and how the candidate frames requests."
        ),
        suggested_role_values=["recruiter_screen"],
        default_framework=ExpressionFramework.PREP,
        default_difficulty=Difficulty.MEDIUM,
        default_question_type_ratios={"behavioral": 35, "craft": 15, "pressure": 50},
    ),
)


def _coerce_enum(enum_type: type[StrEnum], value: StrEnum | str, field_name: str) -> StrEnum:
    if isinstance(value, enum_type):
        return value
    try:
        return enum_type(str(value).strip().lower())
    except ValueError as exc:
        raise DomainValidationException(
            f"Invalid {field_name}: {value}",
            field=field_name,
            details={"allowed": [item.value for item in enum_type]},
        ) from exc


def _normalize_strings(values: list[str], field_name: str) -> list[str]:
    normalized = [value.strip() for value in values if value and value.strip()]
    if not normalized:
        raise DomainValidationException(f"{field_name} cannot be empty", field=field_name)
    return normalized


@dataclass
class TrainingTaskConfig:
    role: str
    level: str
    tech_stack: list[str]
    question_type_ratios: dict[str, float]
    question_count: int
    framework: ExpressionFramework | str = ExpressionFramework.STAR
    difficulty: Difficulty | str = Difficulty.MEDIUM
    category: ScenarioCategory | str = ScenarioCategory.INTERVIEW
    rubric_version: str = DEFAULT_RUBRIC_VERSION
    rubric_weights: dict[RubricDimension | str, float] = field(default_factory=dict)
    metadata: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.role = self.role.strip()
        self.level = self.level.strip()
        if not self.role:
            raise DomainValidationException("role cannot be empty", field="role")
        if not self.level:
            raise DomainValidationException("level cannot be empty", field="level")
        if self.question_count < 1 or self.question_count > 100:
            raise DomainValidationException(
                "question_count must be between 1 and 100",
                field="question_count",
                details={"minimum": 1, "maximum": 100, "got": self.question_count},
            )

        self.category = _coerce_enum(ScenarioCategory, self.category, "category")
        self.difficulty = _coerce_enum(Difficulty, self.difficulty, "difficulty")
        self.framework = _coerce_enum(ExpressionFramework, self.framework, "framework")
        self.tech_stack = _normalize_strings(self.tech_stack, "tech_stack")
        self.question_type_ratios = self._normalize_ratios(self.question_type_ratios)

        weights = self.rubric_weights or DEFAULT_RUBRIC_WEIGHTS[self.category]
        self.rubric_weights = self._normalize_weights(weights)
        self.rubric_version = self.rubric_version.strip() or DEFAULT_RUBRIC_VERSION
        self.metadata = dict(self.metadata or {})

    def _normalize_ratios(self, ratios: dict[str, float]) -> dict[str, float]:
        cleaned = {key.strip(): float(value) for key, value in ratios.items() if key.strip()}
        if not cleaned:
            raise DomainValidationException(
                "question_type_ratios cannot be empty",
                field="question_type_ratios",
            )
        if any(value < 0 for value in cleaned.values()):
            raise DomainValidationException(
                "question_type_ratios cannot contain negative values",
                field="question_type_ratios",
            )
        total = sum(cleaned.values())
        if total <= 0:
            raise DomainValidationException(
                "question_type_ratios total must be greater than 0",
                field="question_type_ratios",
            )
        return {key: value / total for key, value in cleaned.items()}

    def _normalize_weights(
        self,
        weights: dict[RubricDimension | str, float],
    ) -> dict[RubricDimension, float]:
        cleaned: dict[RubricDimension, float] = {}
        for key, value in weights.items():
            dimension = _coerce_enum(RubricDimension, key, "rubric_weights")
            cleaned[dimension] = float(value)
        missing = [dimension for dimension in RubricDimension if dimension not in cleaned]
        if missing:
            raise DomainValidationException(
                "rubric_weights must include all rubric dimensions",
                field="rubric_weights",
                details={"missing": [dimension.value for dimension in missing]},
            )
        if any(value < 0 for value in cleaned.values()):
            raise DomainValidationException(
                "rubric_weights cannot contain negative values",
                field="rubric_weights",
            )
        total = sum(cleaned.values())
        if total <= 0:
            raise DomainValidationException(
                "rubric_weights total must be greater than 0",
                field="rubric_weights",
            )
        return {dimension: value / total for dimension, value in cleaned.items()}


def normalize_training_task_config(config: TrainingTaskConfig) -> TrainingTaskConfig:
    """Return a freshly validated config with normalized ratios and weights."""

    return TrainingTaskConfig(
        role=config.role,
        level=config.level,
        tech_stack=list(config.tech_stack),
        question_type_ratios=dict(config.question_type_ratios),
        question_count=config.question_count,
        framework=config.framework,
        difficulty=config.difficulty,
        category=config.category,
        rubric_version=config.rubric_version,
        rubric_weights=dict(config.rubric_weights),
        metadata=dict(config.metadata),
    )
