# Talk Training Studio Development Rules

本文件是 Talk Training Studio 后续开发的项目级规则。后续 agent 进入本仓库工作时，应先读取本文件，并把这里的目标和流程视为默认开发约束，除非用户在当前任务中明确覆盖。

## 1. 北极星目标

Talk Training Studio 的长期目标不是继续堆一个自研 MVP，而是演进为一个基于成熟项目底座的多模态 AI 沟通训练产品。

最终形态：

- 文本侧优先对齐和迁移 LibreChat 的成熟能力。
- 实时语音/多模态侧优先对齐和迁移 Pipecat 的成熟能力。
- TalkWise 当前训练能力保留为产品差异化：训练目标、persona/stakeholder、scenario、dispatcher、evaluation、growth/report、live guidance、训练复盘和能力沉淀。
- TalkWise 当前核心不是绝对不可变。如果直接站在 LibreChat 或 Pipecat 之上改造更稳、更成熟、更利于长期扩展，可以重构、迁移或重建当前核心。
- 所有模式最终应服务同一套训练产品闭环：训练目标 -> 场景模拟 -> 多模态对话 -> 实时提示 -> 结束复盘 -> 改进计划 -> 针对弱点继续训练。

一句话判断标准：

> 先看 LibreChat / Pipecat 有没有成熟底座可以迁移或站上去改造；只有它们不适合时，才在 TalkWise 中自研。自研也要做成可接入成熟底座的扩展，而不是新的孤岛。

## 2. 成熟底座优先原则

用户给出的实现方式只是候选路径，不自动等于最佳路径。每次设计或实现前，必须先判断是否已有成熟方案可复用。

### LibreChat 优先承接的方向

优先评估 LibreChat 中更成熟、可迁移、未来可能用得上的能力：

- conversation / message tree / branch
- edit / retry / fork
- history / search / selected path
- 多模型 provider / endpoint / model spec
- auth / user / role / session 管理
- MCP / agent / tool calling 相关能力
- 成熟聊天 UI、交互、可访问性、错误反馈
- 通用聊天运行时与前端状态组织

当前项目已有 TalkWise 训练语义时，不要把 LibreChat 的通用聊天语义直接混进 evaluation/growth/report。message tree 分支默认是训练回放和选择上下文，不自动改写评分、完成状态或成长报告。

### Pipecat 优先承接的方向

优先评估 Pipecat 中更成熟、可直接使用或可迁移的能力：

- realtime pipeline
- STT / TTS / LLM 服务编排
- VAD / turn detection / interruption
- audio frame / event / transport
- WebSocket / WebRTC 相关实时链路
- provider-neutral realtime events
- pipeline lifecycle、错误分类、readiness/capability 检查
- 多模态、worker、transport、service adapter 等后续扩展能力

Pipecat 和当前项目语言栈一致时，可以优先直接使用其原生依赖或迁移其架构，而不是手写低成熟度替代品。

### TalkWise 保留和可变的部分

必须保留的不是当前实现形状，而是产品能力：

- 训练目标配置
- persona / stakeholder 行为
- scenario / difficulty / rubric
- dispatcher / turn strategy
- evaluation / scoring
- growth / report / progress
- live guidance
- training history / result review
- branch-aware replay / selected path review

如果这些能力更适合实现为 LibreChat/Pipecat 之上的 adapter、plugin、workflow 或扩展层，应优先调整 TalkWise 核心去适配成熟底座。

## 3. 架构边界

默认目标是形成三层：

1. 成熟运行底座
   - 文本聊天底座：LibreChat-style conversation runtime。
   - 语音/多模态底座：Pipecat realtime runtime。

2. TalkWise 训练语义层
   - TrainingCore 或等价核心只负责训练语义、适配器契约、session 语义、复盘上下文和评估边界。
   - 它不应无意中拥有完整聊天 runtime 或完整语音 runtime，除非经过明确迁移决策。

3. 产品体验层
   - Training Studio、ChatPage、TrainingResult、TrainingHistory、Live Coach 等页面负责把成熟底座能力转成训练产品体验。

不要让文本、语音、视频各自发展成三套训练逻辑。允许存在过渡期 adapter，但长期应收敛到同一训练语义核心。

## 4. 默认工作流

每次开发按下面顺序执行。

### 4.1 开始前

1. 读取本 `AGENTS.md`。
2. 运行或查看 `git status --short`，确认已有改动。
3. 不要 revert、覆盖或清理别人/其他 agent 的改动。
4. 先用 code-review-graph 理解影响面：
   - 增量更新图谱。
   - 检测 changed files、impact radius、affected flows 或 review context。
   - 对大范围改动先确认高风险文件和测试缺口。
5. 读取相关源码和测试，不凭记忆改。
6. 判断本轮是：
   - 迁移成熟底座能力
   - 补 adapter/边界
   - 保持现有功能产品化收口
   - 修 bug 或补测试
   - 架构清理

### 4.2 设计取舍

动手前先做成熟方案判断：

- LibreChat 是否已有成熟实现？
- Pipecat 是否已有原生依赖或成熟实现？
- 当前 TalkWise 核心是否需要保留、改造、迁移或替换？
- 是否能通过 adapter/plugin/workflow 接入，而不是新造一套？
- 本轮是否会破坏现有训练闭环？

如果决定不采用 LibreChat/Pipecat 的成熟能力，需要在最终说明中写出原因：太重、太耦合、当前范围不适合、审计成本太高、或会破坏训练目标。

### 4.3 多智能体协作

任务较大时，可以创建多个子智能体并行，但必须明确 ownership，避免互相覆盖。

常见拆分：

- LibreChat/text branch agent：conversation tree、edit/retry/fork、ChatPage、MessageList、trainingConversation。
- Review/history agent：TrainingResult、TrainingHistory、trainingSession metadata。
- Pipecat/realtime agent：realtime pipeline、readiness、audio.output、transcript persistence。
- TrainingCore agent：training_core、training_conversation adapter、session semantics、boundary tests。
- API isolation agent：conversation/chat/training auth boundary tests 和最小 guard。

每个 agent 必须：

- 只处理自己负责文件。
- 先读当前文件和测试。
- 不 revert 他人改动。
- 完成后报告改动文件、验证命令、剩余风险。

主线程负责合并、二次审查、跑全量验证和最终暂存/提交。

### 4.4 修改中

- 优先小步、可测、可回退的变更。
- 不做无关重构。
- 不为短期功能复制大段成熟项目代码；先建立 adapter 或清晰迁移边界。
- 如果迁移成熟项目代码，保留来源、范围和适配理由。
- UI 以工具型、可扫描、稳定交互为主，不做营销式页面。
- 文本、语音、视频能力接入时，必须保持训练语义可追踪。
- branch/edit/retry/fork 的 metadata 必须能支撑复盘，但不能默认污染 scoring/growth/report。
- readiness/capability/error 信息必须结构化、可读、不可泄露密钥。
- API 边界优先覆盖 conversation/chat/training；在完整 auth 迁移前使用现有 mock user/role 机制补最小可测隔离。

## 5. 验证和 git 节奏

### 5.1 每轮验证

小范围改动先跑 focused tests。完成一轮稳定改动后，默认跑：

```powershell
# frontend
cd frontend
node --test tests\*.mjs
npm run build

# backend
cd backend
..\.venv-backend\Scripts\python.exe -m pytest tests

# repo root
git diff --check
```

如果只改了极小范围，可以先跑 focused test，但最终进入稳定提交前应跑上述全量验证。

### 5.2 暂存和提交

- 一轮功能完成并通过测试后，将本轮稳定改动进入 git 暂存区，便于下一轮继续开发时隔离状态。
- 如果用户明确要求提交，或任务说明写了“通过后提交”，则提交 git commit。
- 如果用户只要求写规则、分析或计划，不要擅自提交；可以说明未提交状态。
- 提交前确认：
  - `git status --short`
  - `git diff --cached --check`
  - staged files 只包含本轮范围

## 6. 前端开发规则

- 保持现有 UI 风格，优先工具型、紧凑、可扫描。
- 不做 landing page 式包装。
- message tree / branch 操作必须有清楚的 loading、disabled、success、error 状态。
- edit / retry / fork 失败时必须保留当前路径，不要让用户误以为已切换。
- 结果页/历史页必须区分 metadata 来源：session、report、progress。
- metadata 只有 ID 没有正文时，显示明确空状态，不伪造摘要。
- 可访问文本和按钮要稳定，便于 FlowGuide 或浏览器调试工具验收。
- 不使用 Playwright，除非用户明确要求；界面验收优先由主线程使用 FlowGuide MCP 或连接的 Chrome 调试工具。

## 7. 后端开发规则

- TrainingCore 或等价核心只承载训练语义，不无意中吞掉 LibreChat/Pipecat runtime。
- conversation tree metadata 要保护 persona/scenario/dispatcher/evaluation/growthReport/liveGuidance。
- selected branch/path/tail 是回放和复盘上下文，不是默认评分完成状态。
- Pipecat final transcript、audio.output、provider-neutral events 应接入 TalkWise training semantics。
- realtime binding、guidance stream、session access 必须保持当前用户 scope。
- 能用现有 mock user/role 机制验证访问边界时，优先补测试，不先重构完整 auth。
- 如果开始迁移 LibreChat auth 或 MCP/agent 能力，必须先写清迁移边界和兼容计划。

## 8. 文档和报告规则

- 仓库工程事实源写在仓库内，例如本文件、README、API、测试、迁移说明。
- 架构理解、阶段路线、跨会话推进和复盘可以沉淀到 AnchorOS，但仓库内规则仍以本 `AGENTS.md` 为开发入口。
- 任何新增长期约束，都应更新本文件，避免后续反复口头对齐。
- 最终回复必须包含：
  - 改动摘要
  - 关键文件
  - 验证命令和结果
  - git 暂存/提交状态
  - 剩余风险或下一步

## 9. 当前阶段判断

截至最近一轮对齐，项目处于从自研 MVP 向成熟底座迁移的中段：

- 已有 TrainingCore / training session / branch metadata 的雏形。
- 文本侧已开始接近 LibreChat-style message tree、edit/retry/fork。
- 语音侧已开始接近 Pipecat realtime pipeline、audio output、readiness diagnostics。
- 结果页/历史页开始支持 branch-aware review。
- API 已有小范围 conversation/chat/training 隔离测试。

但仍未完成：

- LibreChat 尚未成为系统性文本底座。
- Pipecat 尚未成为唯一稳定语音 runtime 抽象。
- TrainingCore 尚未完全统一文本/语音/视频训练编排。
- legacy stakeholder room、conversation tree、training session、realtime pipeline 仍处于过渡并存状态。

后续开发应围绕本文件继续推进，不再重复重新解释总体目标。
