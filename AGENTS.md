# Talk Training Studio Development Rules

本文件是 Talk Training Studio 后续开发的项目级规则。后续 agent 进入本仓库工作时，应先读取本文件，并把这里的目标和流程视为默认开发约束，除非用户在当前任务中明确覆盖。

## 1. 北极星目标

Talk Training Studio 的长期目标不是继续堆一个自研 MVP，而是演进为一个基于成熟项目底座的多模态 AI 沟通训练产品。

最终形态：

- 文本侧优先对齐和迁移 LibreChat 的成熟能力。
- 实时语音/多模态侧优先对齐和迁移 Pipecat 的成熟能力。
- 平台壳、账号、登录、用量、公告、计费和管理控制面由 NewAPI 承接；TalkWise 的已确认目标架构是成为 NewAPI web 内的一等训练产品模块，而不是长期维持独立前端或孤立 UI。
- 语音体验允许两条画像并存：低成本、低延迟的转写式近实时链路，以及基于 Pipecat 的真正实时语音链路；两者都应接入同一训练闭环。
- TalkWise 不以完整复制 Pipecat 平台为目标；目标是把语音、视频和多模态训练中不该自研的基础运行能力，优先站到 Pipecat 或同等级成熟方案上，必要时做 TalkWise 本地化适配。
- TalkWise 当前训练能力保留为产品差异化：训练目标、persona/stakeholder、scenario、dispatcher、evaluation、growth/report、live guidance、训练复盘和能力沉淀。
- TalkWise 当前核心不是绝对不可变。如果直接站在 LibreChat 或 Pipecat 之上改造更稳、更成熟、更利于长期扩展，可以重构、迁移或重建当前核心。
- 所有模式最终应服务同一套训练产品闭环：训练目标 -> 场景模拟 -> 多模态对话 -> 实时提示 -> 结束复盘 -> 改进计划 -> 针对弱点继续训练。

一句话判断标准：

> 先看 LibreChat / Pipecat 有没有成熟底座可以迁移或站上去改造；只有它们不适合时，才在 TalkWise 中自研。自研也要做成可接入成熟底座的扩展，而不是新的孤岛。

NewAPI 是账号、控制面、平台体验和最终前端宿主的默认来源。凡是登录、用户菜单、余额/用量、API Keys、公告、计费、系统设置、主题、导航壳和 admin console 相关需求，先看 NewAPI 已有实现，再决定直接扩展、复用或链接其原生能力。TalkWise 迁成 NewAPI 内的训练模块已是目标架构，不再作为每轮重新讨论的可选方向。

TalkWise 前台产品界面不暴露 NewAPI 品牌名。NewAPI 可以作为源码、账号桥、计费、用量、公告和控制面能力来源，但可见导航、页面标题、tabs、菜单、badge、公告标题和用户菜单必须使用 TalkWise 自己的信息架构或中性功能名，例如“配置”“账号控制台”“用量”“公告”，不要显示“NewAPI”。

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

同时不要把 Pipecat 视为必须替换所有语音链路的唯一答案。当前项目可以保留低成本、低延迟的转写式近实时链路；当它的体验满足训练目标时，优先把它作为经济型语音模式接入同一训练语义。Pipecat 主要承接需要真正实时语音、多模态、打断/turn detection 和更强 transport 能力的链路。

Pipecat 迁移的定位必须保持清楚：迁移目标不是完整抄 Pipecat Cloud、RTVI、电话、WebRTC、avatar、worker bus、全 provider marketplace 等平台能力；迁移目标是 TalkWise 语音/视频训练链路用得上的成熟 runtime、transport、frame/event、turn/interruption、provider adapter、observability 和验收能力。凡是语音、视频、多模态训练的基础设施能力，默认不在 TalkWise 中重新造轮子；除非成熟方案太重、不可审计、与训练闭环冲突或当前阶段成本明显不划算，才允许自研或延后。

后续推荐和排期应按这个顺序判断：

- 先补齐当前两条 TalkWise 语音训练链路相关的完整能力：browser E2E、音频输入/输出、turn/interruption、transcript persistence、live guidance、latency/cost/error 诊断。
- 再按训练产品需要迁入 WebRTC、视频、avatar、更多 provider、RTVI 事件子集或 Pipecat Cloud/worker 能力。
- 不因为 Pipecat 有某项平台能力就直接加入核心路径；只有它能服务当前或明确下一阶段的训练闭环，才进入迁移范围。

### NewAPI 优先承接的方向

NewAPI 是 TalkWise 短中期平台化的首选底座，优先承接：

- 登录、session handoff、用户、团队、角色和 admin 控制面。
- 余额、用量、API Keys、订阅、钱包、模型/渠道和 OpenAI-compatible gateway 入口。
- 公告、系统状态、通知、系统设置和运营配置入口。
- 登录后平台 shell：header、sidebar、user menu、theme/customization、layout density、top nav 和移动端导航。
- 表格、弹层、tabs/segmented、badge、profile dropdown、notification popover 等可复用 UI 组件形态。

项目 owner 已说明对 NewAPI 源码复用有授权，AGPL 不作为本仓库迁移的阻塞项。后续 AI 应直接在 `outside-project/new-api-main` 的原组件、原路由和原模块注册机制上增加或修改 TalkWise 能力，并优先保留 TalkWise 训练语义。不要因为授权可用就整站搬迁或引入无关后台模块。

NewAPI UI 复用遵循“原实现优先”，不是只做风格模仿：

- NewAPI 已有对应页面、区块或组件时，默认复用其组件结构、排版、字号、字重、颜色、行高、间距、宽度、断点、响应式行为和交互状态，只替换 TalkWise 文案、数据、图标语义、路由、权限与业务动作。
- 例如公开落地页 hero 应保留 NewAPI 原标题组件的字号、颜色、字重、最大宽度和换行规则，只换成 TalkWise 标题、说明和 CTA；文案过长时优先压缩文案，不通过缩小字号、改色或局部 CSS 覆盖来迁就。
- authenticated shell、header/sidebar、profile menu、notification、theme、全局动画和通用 UI primitives 必须由 NewAPI host 直接共享。可见 UI 不允许在 Vite 或其他宿主中复制后再追求视觉一致；即使是迁移中间态，也只能通过原组件的 props、slot、adapter 和 route/module registration 扩展。
- 只有 NewAPI 缺失的训练专属结构才新增 UI；新增部分仍使用 NewAPI 的 primitives、tokens、密度和状态规范，不另建 TalkWise 私有设计系统。

当前默认路线：

- 旧 Vite + React Router 前端已在完成页面审计后退役并从当前源码移除；历史实现只通过 Git 历史和仓库归档文档追溯，不是运行时或回滚路径。
- 保留 TalkWise 后端训练语义和现有 NewAPI auth bridge。
- 先建立由 NewAPI 原生消费的 training adapter、host context、route/nav metadata 和 API contract；不再建立 NewAPI-like 平行组件层。
- 全局导航直接注册到 NewAPI 原侧栏/顶栏；业务页内部 tabs 保留训练语义，并直接使用 NewAPI 原生 Tabs/Segmented。
- 路由内类似结构也遵循同一原则：换壳和交互，不换 TalkWise 产品信息架构；不改 tab key、URL、权限、API、表单字段或训练状态。
- 复杂页面按风险逐页换肤：Home/Growth/History 优先，TrainingStudio 第二批，Settings/Chat/实时语音沉浸页最后处理。
- 迁移窗口内新增平台能力时，优先形成可被 NewAPI host 直接消费的 adapter、route metadata 和数据契约；不要继续扩展一套只服务独立 TalkWise shell 的平行基础设施。

目标架构路线：

- NewAPI web 是唯一长期前端宿主；TalkWise 以 `/training` 为根路径注册正式 sidebar/top-nav module，共享 NewAPI 的 authenticated layout、session、permissions、theme、notifications、billing/usage 和 admin console。
- 目标模块路径默认包括 `/training`、`/training/scenarios`、`/training/sessions`、`/training/growth`、`/training/settings`；实时训练可使用 `/training/live/:sessionId` 或等价沉浸式子路由。
- TalkWise 后端继续拥有训练 session、scenario、persona、evaluation、growth、live guidance 和媒体语义；前端迁入 NewAPI 不等于把训练业务数据或 TrainingCore 塞进 NewAPI 网关核心。
- 路由、API base/proxy、role mapping、gateway usage attribution、test matrix 和回滚计划以仓库工程事实文档为准；回滚单位是 NewAPI web/Go 与独立 TalkWise backend，不恢复旧 Vite shell。

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
   - 语音/多模态底座：低成本转写式 near-realtime voice pipeline + Pipecat true realtime voice/multimodal runtime。
   - 平台控制面底座：NewAPI account/session/billing/gateway/admin console。

2. TalkWise 训练语义层
   - TrainingCore 或等价核心只负责训练语义、适配器契约、session 语义、复盘上下文和评估边界。
   - 它不应无意中拥有完整聊天 runtime 或各条语音 runtime 的编排细节，除非经过明确迁移决策。

3. 产品体验层
   - Training Studio、ChatPage、TrainingResult、TrainingHistory、Live Coach 等页面负责把成熟底座能力转成训练产品体验。

不要让文本、语音、视频各自发展成三套训练逻辑。语音侧可以长期保留不同成本/延迟画像的 adapter，但它们必须收敛到同一训练语义核心，而不是各自维护 evaluation/growth/live guidance。

## 4. 默认工作流

每次开发按下面顺序执行。

### 4.1 开始前

1. 读取本 `AGENTS.md`。
2. 运行或查看 `git status --short`，确认已有改动。
3. 不要 revert、覆盖或清理别人/其他 agent 的改动。
4. 先用 code-review-graph 理解影响面：
   - `code-review-graph` 是本仓库唯一图谱工具，用于代码关系、项目内容检索、changed files、impact radius、affected flows 和 review context 分析。
   - TalkWise 根仓库与嵌套 NewAPI 仓库分别建图，只有图谱 HEAD 与当前仓库 HEAD 匹配时才视为有效快照。
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
- NewAPI 是否已有账号、控制面、计费、公告、主题或平台壳实现可以复制、改写或链接复用？
- 语音链路是否需要真正实时能力，还是低成本低延迟的转写式近实时已经满足场景？
- 当前 TalkWise 核心是否需要保留、改造、迁移或替换？
- 是否能通过 adapter/plugin/workflow 接入，而不是新造一套？
- 本轮是否会破坏现有训练闭环？

如果决定不采用 LibreChat/Pipecat/NewAPI 的成熟能力，需要在最终说明中写出原因：太重、太耦合、当前范围不适合、审计成本太高、或会破坏训练目标。
如果选择转写式近实时语音链路而不是 Pipecat，需要说明成本、延迟、质量和训练体验的取舍；只要指标满足目标，就不视为迁移链路不完整。

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
- 不为短期功能复制 NewAPI 可见 UI；在原组件和模块注册点上做小步扩展，并保持 adapter 或清晰迁移边界。
- 如果迁移 LibreChat/Pipecat 等其他成熟项目代码，保留来源、范围和适配理由。
- UI 以工具型、可扫描、稳定交互为主，不做营销式页面。
- 文本、语音、视频能力接入时，必须保持训练语义可追踪。
- branch/edit/retry/fork 的 metadata 必须能支撑复盘，但不能默认污染 scoring/growth/report。
- readiness/capability/error 信息必须结构化、可读、不可泄露密钥。
- API 边界优先覆盖 conversation/chat/training；在完整 auth 迁移前使用现有 mock user/role 机制补最小可测隔离。

### 4.5 配置优先与错误分级

- 已有后台配置、环境变量、渠道参数、模型价格或路由开关可以解决的问题，优先修改配置并验证，不通过改代码逻辑绕过配置。
- 发现报错时，低风险且局部明确的小错误可以在当前任务中直接修复，并补充最小验证；涉及公共运行时、计费、认证、协议、数据迁移、跨模块行为或可能破坏现有训练闭环的大问题，先汇报影响、证据、候选方案和回滚方式，单独处理。
- 新增 provider、渠道类型、计费规则或媒体协议前，先检查 NewAPI、LibreChat、Pipecat 及现有适配器是否已经具备可配置能力；能通过渠道参数、模型列表、代理、倍率或 endpoint 选择完成时，不新增平行实现。
- 配置密钥、访问令牌和数据库敏感字段只允许读取长度、格式和是否存在等非敏感信息；日志、报告、提交和最终回复不得回显密钥。
- 配置变更必须可回退：数据库直接修改前先创建带时间戳的备份，记录修改的非敏感字段和验证结果；没有有效凭据时，不创建伪装成可用的占位渠道。

## 5. 验证和 git 节奏

### 5.1 每轮验证

小范围改动先跑 focused tests。完成一轮稳定改动后，默认跑：

```powershell
# NewAPI web（唯一前端宿主）
cd outside-project\new-api-main\web
bun test src\features\training
bun run typecheck
bun run build

# backend
cd backend
..\.venv-backend\Scripts\python.exe -m pytest tests

# repo root
git diff --check
```

如果只改了极小范围，可以先跑 focused test，但最终进入稳定提交前应跑上述全量验证。

### 5.1.1 Windows 下的 Go 工具链

本项目的 Go 工具链统一使用 WSL 中的 `Ubuntu-22.04`。当 Windows 主机未提供 `go` 或 `gofmt` 时，直接通过 WSL 执行 Go 格式化、测试、构建和静态检查，不再重复寻找或安装 Windows 本机 Go。进入本仓库时使用对应的 `/mnt/f` 路径，例如：

```powershell
wsl -d Ubuntu-22.04 -- bash -lc "cd /mnt/f/AnchorOS/6-项目仓库/Talk-training-studio/outside-project/new-api-main && gofmt -w <files>"
wsl -d Ubuntu-22.04 -- bash -lc "cd /mnt/f/AnchorOS/6-项目仓库/Talk-training-studio/outside-project/new-api-main && go test ./..."
```

后续 `go test`、`go vet`、`go build` 等 Go 命令默认遵循同一 WSL 工作目录和工具链。

### 5.2 暂存和提交

- 一轮功能完成并通过测试后，将本轮稳定改动进入 git 暂存区，便于下一轮继续开发时隔离状态。
- 如果用户明确要求提交，或任务说明写了“通过后提交”，则提交 git commit。
- 如果用户只要求写规则、分析或计划，不要擅自提交；可以说明未提交状态。
- 提交前确认：
  - `git status --short`
  - `git diff --cached --check`
  - staged files 只包含本轮范围

## 6. 前端开发规则

- 全局平台 shell 直接使用 NewAPI：header/sidebar/user menu/notification/quota/theme/navigation/global motion 以 NewAPI 原组件为唯一 UI 事实源。
- 业务训练页面保持工具型、紧凑、可扫描；不要回到 AI demo、营销页或一套孤立自研皮肤。
- 前台 UI 不显示 NewAPI 品牌名；只显示 TalkWise 品牌、TalkWise 业务命名或中性功能命名。
- 旧 Vite + React Router 前端已退役；所有可见 UI 只进入 NewAPI 的 Rsbuild + TanStack Router 宿主，不得恢复平行 shell。
- 全局导航直接扩展 NewAPI 原 shell；业务页内部 tabs 使用 NewAPI 原组件，但不改变训练状态、评分、复盘或配置语义。
- 登录后业务界面不做 landing page 式包装；公开落地页如需存在，优先原样复用 NewAPI 已有页面结构和视觉实现，只替换为 TalkWise 内容与动作。
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
- 转写式近实时语音链路和 Pipecat 真正实时语音链路可以并存；两者都要写入同一 session/transcript/review 语义，并在 adapter 层清楚标记 capability、latency profile 和成本画像。
- realtime binding、guidance stream、session access 必须保持当前用户 scope。
- 能用现有 mock user/role 机制验证访问边界时，优先补测试，不先重构完整 auth。
- 如果开始迁移 LibreChat auth 或 MCP/agent 能力，必须先写清迁移边界和兼容计划。

## 8. 文档和报告规则

- 仓库工程事实源写在仓库内，例如本文件、README、API、测试、迁移说明。
- 生产部署、服务器路径、PostgreSQL/Redis 接入、域名切换、验证和回滚流程以 `docs/development/server-deployment-runbook.md` 为快速入口；后续本地更新推送到服务器前先读该文档。
- 架构理解、阶段路线、跨会话推进和复盘可以沉淀到 AnchorOS，但仓库内规则仍以本 `AGENTS.md` 为开发入口。
- 任何新增长期约束，都应更新本文件，避免后续反复口头对齐。
- 最终回复必须包含：
  - 改动摘要
  - 关键文件
  - 验证命令和结果
  - git 暂存/提交状态
  - 剩余风险或下一步

## 9. 当前阶段判断

截至 2026-08-01，前端宿主迁移已经完成，项目进入训练运行底座和产品能力持续收口阶段：

- 已有 TrainingCore / training session / branch metadata 的雏形。
- 文本侧已开始接近 LibreChat-style message tree、edit/retry/fork。
- 语音侧已开始形成转写式 near-realtime voice pipeline 与 Pipecat realtime pipeline 两种链路画像，并接近 audio output、readiness diagnostics 等能力。
- 平台侧由 NewAPI web 作为唯一前端宿主，完整 `/training` 页面簇、受认证同源代理、身份桥、训练团队管理、成长积分和沟通名片均已进入原 TanStack Router、sidebar 与原生组件体系。
- 结果页/历史页开始支持 branch-aware review。
- API 已有小范围 conversation/chat/training 隔离测试。

当前仍需继续收口的边界：

- LibreChat 尚未成为系统性文本底座。
- Pipecat 不再被定义为必须成为唯一稳定语音 runtime；低成本、低延迟的转写式近实时链路可以与真正实时语音链路并存。
- NewAPI web 已承载 scenarios/sessions/review/growth/personas/multimodal/settings/team 等业务页簇；独立 Vite shell 已最终退场。后续新增前端能力不得重新建立独立宿主。
- TrainingCore 尚未完全统一文本/语音/视频训练编排。
- legacy stakeholder room、conversation tree、training session、转写式 near-realtime pipeline、Pipecat realtime pipeline 仍需收口 adapter 边界，但并存本身不是问题。

后续开发应围绕本文件继续推进，不再重复重新解释总体目标。
