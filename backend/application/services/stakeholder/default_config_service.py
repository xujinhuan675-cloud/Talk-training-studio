# input: UnitOfWork factory + persona_dir
# output: idempotent default stakeholder config seed for personas, organizations, teams, and room scenarios
# owner: wanhua.gu
# pos: 应用层服务 - 默认角色/组织/对话场景种子数据；一旦我被更新，务必更新我的开头注释以及所属文件夹的md
"""Default configuration seed for stakeholder training setup."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from domain.common.unit_of_work import AbstractUnitOfWork
from domain.stakeholder.organization_entity import Organization, Team
from domain.stakeholder.scenario_entity import Scenario

DEFAULT_CONFIG_SEED_VERSION = 1
DEFAULT_CONFIG_SEED_FILENAME = "default_config_seed.json"


@dataclass(frozen=True)
class DefaultPersonaPreset:
    id: str
    name: str
    role: str
    content: str
    organization_name: str | None = None
    team_name: str | None = None


@dataclass(frozen=True)
class DefaultTeamPreset:
    name: str
    description: str = ""


@dataclass(frozen=True)
class DefaultOrganizationPreset:
    name: str
    industry: str
    description: str
    context_prompt: str
    teams: tuple[DefaultTeamPreset, ...] = ()


@dataclass(frozen=True)
class DefaultScenarioPreset:
    name: str
    description: str
    context_prompt: str
    suggested_persona_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class DefaultConfigSeedResult:
    persona_files_created: int = 0
    organizations_created: int = 0
    teams_created: int = 0
    scenarios_created: int = 0

    @property
    def changed(self) -> bool:
        return any(
            (
                self.persona_files_created,
                self.organizations_created,
                self.teams_created,
                self.scenarios_created,
            )
        )


DEFAULT_ORGANIZATION_PRESETS: tuple[DefaultOrganizationPreset, ...] = (
    DefaultOrganizationPreset(
        name="星瀚科技",
        industry="B2B SaaS / AI",
        description="高速增长的企业智能协作平台，正在从单点工具转向平台化解决方案。",
        context_prompt=(
            "组织重视增长速度、客户留存、企业级安全和交付确定性。对话中应体现预算约束、"
            "跨部门依赖、上线风险和对可验证结果的要求。"
        ),
        teams=(
            DefaultTeamPreset("管理层", "CEO/CFO/业务负责人，关注战略收益、预算和风险。"),
            DefaultTeamPreset("产品与研发", "负责路线图、技术边界、稳定性和交付节奏。"),
            DefaultTeamPreset("销售增长", "负责收入目标、重点客户推进和续约扩容。"),
            DefaultTeamPreset("客户成功", "负责客户落地、满意度、投诉处理和续约风险。"),
        ),
    ),
    DefaultOrganizationPreset(
        name="澜舟零售",
        industry="连锁零售 / 本地生活",
        description="区域连锁服务品牌，门店增长快，但客户体验、人员培训和服务一致性波动明显。",
        context_prompt=(
            "组织看重门店转化、服务口碑、复购和投诉闭环。角色通常关注一线执行难度、"
            "客户情绪、价格敏感和标准化流程。"
        ),
        teams=(
            DefaultTeamPreset("门店运营", "负责一线服务、排班、服务质量和现场问题处理。"),
            DefaultTeamPreset("市场增长", "负责获客活动、转化、会员和促销策略。"),
            DefaultTeamPreset("客户服务", "负责投诉、退款、补救方案和高价值客户维护。"),
        ),
    ),
    DefaultOrganizationPreset(
        name="云杉企业服务",
        industry="企业服务 / 项目交付",
        description="为中大型企业提供咨询与系统集成服务，项目周期长，决策链复杂。",
        context_prompt=(
            "组织中的对话经常围绕采购评审、信息安全、项目范围、ROI 和上线责任展开。"
            "角色会要求清晰证据、阶段计划和风险预案。"
        ),
        teams=(
            DefaultTeamPreset("采购委员会", "负责价格、合同条款、供应商比较和审批节奏。"),
            DefaultTeamPreset("IT 与安全", "负责集成、权限、安全审查和运维风险。"),
            DefaultTeamPreset("业务部门", "负责业务目标、使用体验和结果验收。"),
        ),
    ),
)


DEFAULT_PERSONA_PRESETS: tuple[DefaultPersonaPreset, ...] = (
    DefaultPersonaPreset(
        id="tw-cfo-li-na",
        name="李娜",
        role="CFO / 预算守门人",
        organization_name="星瀚科技",
        team_name="管理层",
        content=(
            "## 角色画像\n"
            "李娜负责年度预算和现金流安全。她愿意支持能带来明确回报的方案，但会要求说明成本结构、"
            "投入节奏、风险预案和可衡量收益。\n\n"
            "## 对话风格\n"
            "- 先问数字和假设，再听愿景。\n"
            "- 对模糊承诺保持怀疑，会追问最坏情况。\n"
            "- 如果你能给出分阶段投入和退出机制，她会更愿意推进。\n\n"
            "## 典型追问\n"
            "- 这笔投入什么时候能看到结果？\n"
            "- 如果三个月后数据不达预期，损失如何控制？\n"
            "- 有没有比现在更低风险的试点方式？"
        ),
    ),
    DefaultPersonaPreset(
        id="tw-cto-zhang-wei",
        name="张伟",
        role="CTO / 技术可行性把关人",
        organization_name="星瀚科技",
        team_name="产品与研发",
        content=(
            "## 角色画像\n"
            "张伟关注架构稳定性、数据安全、集成成本和团队负载。他不排斥新方案，"
            "但会优先保护系统可靠性和工程节奏。\n\n"
            "## 对话风格\n"
            "- 直接指出技术风险，不喜欢绕圈子。\n"
            "- 要求拆清楚依赖、边界和验收标准。\n"
            "- 对没有 owner 的承诺非常敏感。\n\n"
            "## 典型追问\n"
            "- 这个方案和现有权限系统怎么集成？\n"
            "- 上线失败时如何回滚？\n"
            "- 谁负责后续维护，SLA 是什么？"
        ),
    ),
    DefaultPersonaPreset(
        id="tw-sales-vp-chen-yu",
        name="陈宇",
        role="销售副总裁 / 收入目标负责人",
        organization_name="星瀚科技",
        team_name="销售增长",
        content=(
            "## 角色画像\n"
            "陈宇背着季度收入目标，偏好能加速签单、续约和扩容的方案。"
            "他会推动优先级，但也担心承诺过度影响客户信任。\n\n"
            "## 对话风格\n"
            "- 节奏快，喜欢要结论和下一步。\n"
            "- 会用大客户压力挑战产品与交付边界。\n"
            "- 如果你能同时守住价值和交付风险，他会配合。\n\n"
            "## 典型追问\n"
            "- 这个客户本季度能不能推进？\n"
            "- 哪些需求可以先进合同，哪些必须后置？\n"
            "- 我对客户怎么承诺才不踩线？"
        ),
    ),
    DefaultPersonaPreset(
        id="tw-cs-director-wang-min",
        name="王敏",
        role="客户成功负责人 / 投诉升级处理人",
        organization_name="澜舟零售",
        team_name="客户服务",
        content=(
            "## 角色画像\n"
            "王敏负责服务质量、投诉闭环和重点客户满意度。她在意情绪承接，也在意补救方案是否能落地。\n\n"
            "## 对话风格\n"
            "- 会先判断你是否真正理解客户感受。\n"
            "- 对甩锅、空泛道歉和没有时间表的方案不耐烦。\n"
            "- 接受清楚的事实复盘和可追踪恢复计划。\n\n"
            "## 典型追问\n"
            "- 你准备先安抚客户还是先解释原因？\n"
            "- 这个补救动作谁负责，多久反馈？\n"
            "- 如何避免同类投诉再发生？"
        ),
    ),
    DefaultPersonaPreset(
        id="tw-hr-interviewer-lin-qiao",
        name="林乔",
        role="HR 面试官 / 动机与匹配度评估者",
        organization_name="云杉企业服务",
        team_name="业务部门",
        content=(
            "## 角色画像\n"
            "林乔负责候选人初筛和综合面试中的动机、沟通、稳定性评估。她希望候选人讲清事实和取舍，"
            "不喜欢背稿式回答。\n\n"
            "## 对话风格\n"
            "- 温和但会持续追问细节。\n"
            "- 关注真实动机、角色匹配和过往贡献边界。\n"
            "- 对夸大经历或回避失败很敏感。\n\n"
            "## 典型追问\n"
            "- 你为什么想做这个方向？\n"
            "- 这个项目里你本人具体负责什么？\n"
            "- 如果重新做一次，你会改哪里？"
        ),
    ),
    DefaultPersonaPreset(
        id="tw-product-lead-zhao-rui",
        name="赵睿",
        role="产品负责人 / 路线图取舍决策者",
        organization_name="星瀚科技",
        team_name="产品与研发",
        content=(
            "## 角色画像\n"
            "赵睿负责产品路线图和跨团队优先级。他会在客户需求、商业机会、技术债和用户价值之间做取舍。\n\n"
            "## 对话风格\n"
            "- 要求先讲目标和判断标准。\n"
            "- 喜欢用用户证据、指标和机会成本讨论优先级。\n"
            "- 不接受只说“重要”，必须解释为什么现在做。\n\n"
            "## 典型追问\n"
            "- 这个需求服务哪个用户问题？\n"
            "- 如果插队，原计划牺牲什么？\n"
            "- 成功指标和最小版本是什么？"
        ),
    ),
)


DEFAULT_SCENARIO_PRESETS: tuple[DefaultScenarioPreset, ...] = (
    DefaultScenarioPreset(
        name="季度预算评审会",
        description="向 CFO 和业务负责人争取下一季度试点预算，需要讲清收益、风险和阶段性投入。",
        context_prompt=(
            "你正在申请一个新训练项目的季度预算。对方会关注成本、ROI、现金流风险、"
            "试点范围和退出机制。练习目标是用结构化表达争取有条件通过。"
        ),
        suggested_persona_ids=("tw-cfo-li-na", "tw-sales-vp-chen-yu"),
    ),
    DefaultScenarioPreset(
        name="企业客户续约异议处理",
        description="重点客户准备用竞品压价，你需要守住价值、识别真实顾虑并推进下一步。",
        context_prompt=(
            "客户认为竞品价格更低，要求额外折扣。对话要避免单向让步，先确认使用价值、"
            "替代成本、续约风险和可交换条件。"
        ),
        suggested_persona_ids=("tw-sales-vp-chen-yu", "tw-cfo-li-na"),
    ),
    DefaultScenarioPreset(
        name="产品路线优先级冲突",
        description="销售要求插入大客户功能，研发担心打乱排期，产品需要促成可执行决定。",
        context_prompt=(
            "销售提出高收入客户的紧急需求，希望进入当前迭代；技术侧担心范围蔓延和质量风险。"
            "练习目标是澄清判断标准、暴露取舍并落下明确 owner 与下一步。"
        ),
        suggested_persona_ids=(
            "tw-product-lead-zhao-rui",
            "tw-cto-zhang-wei",
            "tw-sales-vp-chen-yu",
        ),
    ),
    DefaultScenarioPreset(
        name="高价值客户投诉升级",
        description="VIP 客户认为问题长期无人处理，要求立即升级优先级和补偿方案。",
        context_prompt=(
            "客户情绪强烈，认为服务承诺未兑现。练习目标是先承接情绪，再确认事实、责任人、"
            "恢复时间表和补救选项。"
        ),
        suggested_persona_ids=("tw-cs-director-wang-min",),
    ),
    DefaultScenarioPreset(
        name="产品经理行为面试复盘",
        description="围绕候选人的项目经历、冲突处理、失败复盘和岗位动机做高密度追问。",
        context_prompt=(
            "面试官会要求候选人用 STAR 讲清真实贡献、指标、协作冲突和反思。"
            "练习目标是避免泛泛描述，提升证据密度和边界感。"
        ),
        suggested_persona_ids=("tw-hr-interviewer-lin-qiao", "tw-product-lead-zhao-rui"),
    ),
    DefaultScenarioPreset(
        name="跨部门上线 Go/No-Go",
        description="版本临近上线，但安全、交付和客户沟通都存在不确定性，需要给出是否上线的建议。",
        context_prompt=(
            "你要在跨部门评审中给出 go/no-go 建议。对方会追问风险、缓解动作、"
            "责任分工、客户沟通和延期代价。"
        ),
        suggested_persona_ids=(
            "tw-cto-zhang-wei",
            "tw-product-lead-zhao-rui",
            "tw-cs-director-wang-min",
        ),
    ),
)


def _seed_marker_path(persona_dir: Path) -> Path:
    return persona_dir.parent / DEFAULT_CONFIG_SEED_FILENAME


def _has_current_seed_marker(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return False
    return payload.get("version") == DEFAULT_CONFIG_SEED_VERSION


def _write_seed_marker(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": DEFAULT_CONFIG_SEED_VERSION,
        "description": "TalkWise default personas, organizations, and room scenarios seeded.",
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _yaml_value(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _persona_markdown(
    preset: DefaultPersonaPreset,
    *,
    organization_id: int | None = None,
    team_id: int | None = None,
) -> str:
    lines = [
        "---",
        f"name: {_yaml_value(preset.name)}",
        f"role: {_yaml_value(preset.role)}",
    ]
    if organization_id is not None:
        lines.append(f"organization_id: {organization_id}")
    if team_id is not None:
        lines.append(f"team_id: {team_id}")
    lines.extend(["source: talkwise_default_seed", "---", "", preset.content.strip(), ""])
    return "\n".join(lines)


def ensure_default_persona_files(
    persona_dir: str | Path,
    *,
    org_ids_by_name: dict[str, int] | None = None,
    team_ids_by_org_and_name: dict[tuple[str, str], int] | None = None,
    force: bool = False,
) -> int:
    """Create missing default persona markdown files without overwriting user edits."""

    root = Path(persona_dir)
    root.mkdir(parents=True, exist_ok=True)
    created = 0
    org_ids_by_name = org_ids_by_name or {}
    team_ids_by_org_and_name = team_ids_by_org_and_name or {}

    for preset in DEFAULT_PERSONA_PRESETS:
        path = root / f"{preset.id}.md"
        if path.exists() and not force:
            continue
        organization_id = (
            org_ids_by_name.get(preset.organization_name)
            if preset.organization_name
            else None
        )
        team_id = (
            team_ids_by_org_and_name.get((preset.organization_name, preset.team_name))
            if preset.organization_name and preset.team_name
            else None
        )
        path.write_text(
            _persona_markdown(preset, organization_id=organization_id, team_id=team_id),
            encoding="utf-8",
        )
        created += 1
    return created


async def seed_default_stakeholder_config(
    *,
    uow_factory: Callable[..., AbstractUnitOfWork],
    persona_dir: str | Path,
    force: bool = False,
) -> DefaultConfigSeedResult:
    """Seed default configuration once per version and never overwrite existing rows/files."""

    persona_root = Path(persona_dir)
    marker_path = _seed_marker_path(persona_root)
    has_current_marker = _has_current_seed_marker(marker_path)
    should_seed = force or not has_current_marker

    organizations_created = 0
    teams_created = 0
    scenarios_created = 0
    org_ids_by_name: dict[str, int] = {}
    team_ids_by_org_and_name: dict[tuple[str, str], int] = {}

    async with uow_factory() as uow:
        organizations = await uow.organization_repository.list_all(skip=0, limit=500)
        scenarios = await uow.scenario_repository.list_all(skip=0, limit=500)
        should_seed_db = should_seed or not organizations or not scenarios

        if should_seed_db:
            orgs_by_name = {org.name: org for org in organizations}
            for preset in DEFAULT_ORGANIZATION_PRESETS:
                org = orgs_by_name.get(preset.name)
                if org is None:
                    org = await uow.organization_repository.create(
                        Organization(
                            id=None,
                            name=preset.name,
                            industry=preset.industry,
                            description=preset.description,
                            context_prompt=preset.context_prompt,
                        )
                    )
                    orgs_by_name[preset.name] = org
                    organizations_created += 1
                if org.id is None:
                    continue
                org_ids_by_name[preset.name] = org.id
                existing_teams = {
                    team.name: team
                    for team in await uow.team_repository.list_by_organization(org.id)
                }
                for team_preset in preset.teams:
                    team = existing_teams.get(team_preset.name)
                    if team is None:
                        team = await uow.team_repository.create(
                            Team(
                                id=None,
                                organization_id=org.id,
                                name=team_preset.name,
                                description=team_preset.description,
                            )
                        )
                        teams_created += 1
                    if team.id is not None:
                        team_ids_by_org_and_name[(preset.name, team_preset.name)] = team.id

            scenarios_by_name = {scenario.name: scenario for scenario in scenarios}
            for preset in DEFAULT_SCENARIO_PRESETS:
                if preset.name in scenarios_by_name:
                    continue
                await uow.scenario_repository.create(
                    Scenario(
                        id=None,
                        name=preset.name,
                        description=preset.description,
                        context_prompt=preset.context_prompt,
                        suggested_persona_ids=list(preset.suggested_persona_ids),
                    )
                )
                scenarios_created += 1
        else:
            for org in organizations:
                if org.id is None:
                    continue
                org_ids_by_name[org.name] = org.id
                for team in await uow.team_repository.list_by_organization(org.id):
                    if team.id is not None:
                        team_ids_by_org_and_name[(org.name, team.name)] = team.id

        await uow.commit()

    existing_persona_files = list(persona_root.glob("*.md")) if persona_root.exists() else []
    should_seed_personas = should_seed or not existing_persona_files
    persona_files_created = 0
    if should_seed_personas:
        persona_files_created = ensure_default_persona_files(
            persona_root,
            org_ids_by_name=org_ids_by_name,
            team_ids_by_org_and_name=team_ids_by_org_and_name,
            force=force,
        )

    if should_seed or organizations_created or teams_created or scenarios_created or persona_files_created:
        _write_seed_marker(marker_path)

    return DefaultConfigSeedResult(
        persona_files_created=persona_files_created,
        organizations_created=organizations_created,
        teams_created=teams_created,
        scenarios_created=scenarios_created,
    )
