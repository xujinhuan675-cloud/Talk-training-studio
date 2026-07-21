---
stage: plan
status: active
owner: codex
created_by: codex
created: 2026-07-17
related:
  - docs/plans/2026-07-13-training-studio-long-term-roadmap.md
  - AGENTS.md
---

# LibreChat / Pipecat 成熟底座适配审计

## 结论

Talk Training Studio 的目标不是继续扩大自研 MVP，而是把 TalkWise 的训练闭环站到两个成熟底座上：

- 文本、历史、分支、搜索、模型配置、认证、Agent/MCP 优先对齐 LibreChat。
- 实时语音、多模态、STT/TTS/LLM 编排、VAD、turn detection、interruption、transport 优先对齐 Pipecat。
- TalkWise 保留的是训练产品语义：training goal、scenario、persona/stakeholder、dispatcher、evaluation、growth/report/progress、live guidance、branch-aware review。
- 当前 TalkWise 核心可以重构、迁移或重建。判断标准是能否更稳地完成训练闭环，而不是保护当前实现形状。

当前代码已经有这个概念，但还没有完成系统性迁移。TrainingCore、conversation tree、realtime pipeline、branch-aware result/history、mock auth boundary 都已有雏形；缺口是 LibreChat 尚未成为文本底座，Pipecat 尚未成为唯一语音 runtime，认证/权限已经开始收口，但 MCP/Agent 还没有进入统一产品架构。

## 图谱快照

本轮使用三个 code-review graph 独立查看，避免当前仓库根目录下的 `outside-project` 污染当前项目判断。

| 仓库 | 文件 | 节点 | 边 | 关键热点 |
|:---|---:|---:|---:|:---|
| Talk Training Studio | 4843 | 54130 | 559795 | `App`、`startQuickSession`、`create_session`、`generate_report`、`start_training_session`、`list_scenario_progress` |
| LibreChat | 3312 | 35157 | 412967 | OAuth flow、MCP discovery/call、ChatRoute、SSE、AgentPanel、ConvoOptions、Search |
| Pipecat | 1163 | 14661 | 117462 | pipeline `start`、`process_frame`、interruption、turn callbacks、TTS/STT/LLM services、transports |

图谱结论：

- LibreChat 的成熟度集中在通用聊天平台能力，不应把它的通用语义直接塞进 TalkWise scoring/growth。
- Pipecat 的成熟度集中在实时 frame pipeline 和服务编排，适合作为 TalkWise voice/realtime 的运行层。
- TalkWise 的价值层应保持在训练语义，不继续自研完整 chat runtime 或完整 realtime runtime。

## 当前项目程度

整体判断：概念已经成立，工程迁移处于中段。

| 维度 | 当前完成度 | 判断 |
|:---|:---:|:---|
| 产品目标对齐 | 85% | `AGENTS.md` 已写入成熟底座优先规则，长期路线已明确。 |
| TalkWise 训练语义 | 75% | TrainingCore、session、scenario、report、live guidance 已有；文本 runtime contract 已明确 TrainingCore 只保存 conversation ref/metadata，正文和路径状态由 adapter/runtime 持有。 |
| 文本分支体验 | 75-80% | 已有 message tree action、edit/retry/fork、path/tail/fork point UI；文本 source-of-truth 已先定为 adapter-owned 过渡契约，离完整 LibreChat-style schema 迁移仍有距离。 |
| 训练复盘/历史 | 70% | 已展示 session/report/progress 来源、当前路径、最后回复和空状态，数据契约仍需继续收紧。 |
| Pipecat/realtime | 70-75% | 已切到 Pipecat-only runtime，独立 OpenAI realtime 路径已移除；runner 已有 provider-neutral telemetry summary，但仍缺真实浏览器音频链路验收和聚合 tracing。 |
| 认证/隔离 | 75-80% | conversation / session / report / guidance / realtime 的边界开始统一收口；legacy stakeholder room escape hatch 已绑定 TrainingSession ACL 和 room_id。完整真实 auth/ACL 形状还未迁完。 |
| MCP/Agent/Tool | 45-50% | capability registry 已区分 descriptor-only 与真实 dispatcher/runtime：Agent/Tool/MCP descriptor 可 configured，但 ready=false 并带 warning；仍未实现通用 dispatcher。 |
| 成熟部署/运维 | 25% | 本地开发和测试可用，管理面板、权限覆盖、token/usage、审计不足。 |

## 成熟底座迁移进度仪表盘

更新日期：2026-07-21。

本节用于给后续 AI 快速判断：当前 TalkWise 哪些核心部分已经迁到 LibreChat / Pipecat 的成熟底座思路上，哪些还只是概念或 inventory，哪些成熟项目能力未来可继续迁入。后续每轮迁移后应优先更新本节，再更新更细的功能域说明。

总体判断：当前不是“已迁完”，而是已经从概念对齐进入按成熟底座切块迁移的中期偏后。第一批边界已经落地；LibreChat 尚未成为文本唯一 source of truth，Pipecat 已成为 realtime voice 的当前 runtime source of truth。

### 2026-07-19 缺口分层更正

当下不再继续扩大“未来可迁移能力”的实现范围。后续工作分成两层：

- **当前要做**：只处理已经进入 TalkWise 训练闭环、会直接影响可用性/可信度/隔离性的缺口。
- **未来路线图**：LibreChat / Pipecat 中高价值但尚未进入当前闭环的能力，统一沉淀到长期路线图，不在当前切片里实现。

当前要做的缺口收敛为：

| 当前缺口 | 为什么现在做 | 交付边界 |
|:---|:---|:---|
| Pipecat realtime 本机链路验收 | `readyForCall=true` 只能证明依赖和配置具备，还需要可重复 smoke/事件契约，才能判断真实语音链路是否值得进入浏览器 E2E。 | 已把 smoke contract 扩展为 `productionReadiness`、`contractCoverage`、事件顺序和错误分类；runner 新增 secret-safe telemetry summary，覆盖 `audio.output`、turn latency、interruption/silence、provider error taxonomy。真实浏览器麦克风权限验证仍单独排期。 |
| Text runtime / message-tree UI 验收 | 文字训练复盘依赖 selected path；edit/retry/fork/reload/search 不能污染评分和成长。 | 服务层 edit/retry/fork 已补测试矩阵，继续过滤 scoring/growth/report/completion metadata；本轮新增 text conversation runtime contract，明确正文、branch state、selected path、source path 由 adapter/runtime 持有。真实 UI reload/fork 操作 E2E 单独排期。 |
| Auth / ACL / resource scope 遗漏点 | 训练 session、report、guidance、file/material、agent config 不能跨用户/团队泄漏。 | conversation/chat 写路径、agent config、file asset repository 普通访问都要求显式 `OwnedMetadataScope`；legacy stakeholder room 读取已改为 `legacy_training_session_room_scope`，先验证当前用户可访问 session，再验证 bound `room_id`。下一步是真实 auth/ACL 迁移和 admin override 产品语义。 |
| Files / training material ownership | 素材进入 persona builder、复盘或 tool consumer 前必须先有权限边界。 | file asset 服务层和 repository 层都已收紧 scope；`key_exists_outside_metadata_scope` 也拒绝 `metadata_scope=None`。继续不先做通用 RAG。 |
| 训练相关窄 tool consumer | MCP/Agent 只有 inventory 还不能产生训练价值，但不能先做完整 marketplace/dispatcher。 | 已接入复盘助手前端，并新增只读素材对照接口；本轮 readiness registry 进一步声明 Agent/Tool/MCP 仍是 descriptor-only：`configured=true` 不代表 `ready=true`，不会启动 dispatcher、tool executor 或 MCP server。不做通用 dispatcher、RAG 正文检索或 Agent marketplace。 |

当前暂不做、只放路线图的能力：

- LibreChat 完整 OAuth/LDAP/2FA、admin panel、marketplace、通用分享、artifact/code interpreter。
- LibreChat 完整 MCP lifecycle、OAuth MCP、通用 tool dispatcher、Agent marketplace。
- LibreChat 完整 RAG、外部文件 picker、web search、usage/billing/moderation。
- Pipecat WebRTC/LiveKit/Daily、电话运营商、视频 avatar、多 provider 全量扩展、分布式 workers。
- Pipecat RTVI 全量客户端协议和完整 observability 平台。

2026-07-19 本轮已落地：

- Pipecat capabilities 增加本机 smoke contract：区分 `localRuntimeReady` 与 `browserE2EVerified=false`，并固化 WebSocket、PCM16、TalkWise realtime 事件契约。
- File asset 服务层把 `metadata_scope` 继续下沉到 `upsert_active_asset`、物理 purge by id/key，降低未来 tool/RAG 误用 legacy helper 的跨作用域风险。
- Training Studio 增加局部训练素材 tool consumer API，默认只返回当前用户/团队 scope 内 `training_material` 的安全 metadata excerpt，不暴露 MCP/Agent 主导航。
- 复盘助手前端接入训练素材 tool consumer，在训练结果页读取和展示有权限素材的安全摘要，并通过 `include_content_excerpt=true` opt-in 读取 text-like 素材的受控正文片段。
- 复盘助手新增 `POST /training-studio/tool-consumers/review-assistant/material-review` 窄接口，把当前训练 session/report/replay 与选中素材 snippet 做只读结构化对照，返回 matched_points、missed_points、suggested_rewrites、referenced_materials、source_state/limits；不写 scoring/growth/completion metadata。
- Conversation fork 完成后会 remap `selectedPath`、`currentBranchTail`、`messageTreeSelection` 中的 source message id，避免 fork 后 replay/reload 指向源会话分支。

2026-07-20 本轮已落地：

- 素材对照接口新增可替换 LLM adapter：有 stakeholder LLM 时只增强 `matched_points`、`missed_points`、`suggested_rewrites`，并继续保留 deterministic fallback、scoped material snippet、referenced_materials、source_state/limits 和后端受控字段；无 LLM、LLM 异常或响应无效时仍返回 fallback。
- ACL / resource scope 开始进入核心切片：`owned_metadata_scope_for_current_user` 对 admin 也返回显式 user/team scope；conversation update/delete、message action/edit/retry 和 chat 写入口改为 `allow_unscoped=false`，保留 legacy unscoped 的只读兼容边界。
- Training Studio guidance/realtime helper 去掉无用户 unscoped fallback；Pipecat realtime voice context 在启动 pipeline 前重新按当前用户 scope 读取 session，transcript persistence sink 在写入 room message 和 record_turns 前校验 training session room 与 binding 一致。

2026-07-21 本轮已落地：

- File asset repository 对齐 conversation / agent config 的 ACL 口径：普通 `get/update/delete/list/count` 不再接受 `metadata_scope=None`，全量读取只能走显式命名的 `get_by_id_for_maintenance` / `get_by_key_for_maintenance`。`key_exists_outside_metadata_scope` 也先拒绝空 scope，避免 scope-sensitive helper 变成新的 full-access 入口。
- LibreChat-style message tree 边界继续固化：edit/retry/fork 会过滤 `score`、report、completion、`affectsScoring` / `affectsCompletion` 及常见别名；fork 从源 conversation 复制 metadata 前先清理结果类字段，保留 TalkWise 训练语义中的 `evaluation` / `growthReport`，但不让通用分支 metadata 改写 scoring/growth/completion。
- Pipecat realtime capability 增加生产就绪分层：`readyForCall` 只代表本机依赖和配置可发起调用；`productionReady=false` 和 `productionReadiness.blockingReasons[]=BROWSER_AUDIO_E2E_NOT_VERIFIED` 明确保留真实浏览器麦克风、WebSocket 输入、音频播放、turn/interruption/silence、metrics/error taxonomy 的 E2E 验收缺口。
- Text runtime source-of-truth 缺口先以过渡 contract 收口：`conversationRuntimeContract` 标记当前 source of truth 是 conversation runtime adapter，TrainingCore 只保存 `conversation_ref` / `metadata`，message body、branch state、selected path、source path 不进入 TrainingCore 持久语义；`ConversationTrainingConversationAdapter` 会过滤 task metadata 里的 runtime-owned shadow keys。
- Training Studio legacy stakeholder room scope 缺口继续收口：report/guidance/material review 读取 room 时不再直接裸用 unrestricted scope，而是先校验当前用户可访问的 TrainingSession，再校验 session 绑定 room_id，最后生成带 `guarded_by_training_session_id` / `guarded_room_id` 的 legacy scope。
- MCP / Agent / Tool readiness 缺口从“容易误读为可运行”改为 descriptor-only contract：已注册的 Agent/Tool/MCP 可以是 `configured=true`，但 readiness 为 `warning` / `ready=false`，metadata 明确 `dispatcher_started=false`、`runtime_started=false`、无 tool executor、无 MCP runtime。
- Pipecat realtime observability 从事件透传推进到 session-level telemetry summary：runner 聚合 `audio.output` 次数/字节、turn started/completed/latency、interruption、silence 和 provider error taxonomy，并在摘要中继续做 secret redaction。
- 后端验证已从 focused tests 扩展到完整 suite：`..\\.venv-backend\\Scripts\\python.exe -m pytest tests` 通过 778 个测试。真实浏览器 E2E、完整 LibreChat schema 迁移、完整 MCP/Agent dispatcher 仍保留为后续架构切片。

2026-07-21 OpenRouter / Pipecat provider 缺口盘查与第一条迁移：

- code-review-graph 针对 `training_studio.py`、`realtime.py`、`realtime_pipeline.py` 和 realtime tests 的审查显示：当前高风险缺口不是 Pipecat pipeline 本身，而是 provider 选择被写死在 `stt=openai`、`tts=openai`、`llm=openai`，并且 `RealtimePipelineCapability` 没有显式 `llm` 字段，导致 LLM provider 只能藏在 metadata 里。
- 上游 Pipecat 当前可直接迁入的 OpenRouter 能力是 `pipecat.services.openrouter.llm.OpenRouterLLMService`，属于 LLM service；它不是 STT/TTS/transport 的完整 realtime speech-to-speech provider。
- 本轮先落地 OpenRouter LLM slice：Pipecat runtime 仍是 `provider=pipecat`，STT/TTS 仍保持 OpenAI，VAD 仍是 Silero，turn detection 仍归 Pipecat；只有内部 `llm.provider` 可为 `openrouter`，并通过 Pipecat 原生 `OpenRouterLLMService` 构建 LLM processor。
- readiness / capability 已区分 `llm:openrouter` 与 `llm:openai`，新增 OpenRouter key/base URL 缺口报告，避免把 OpenRouter key 静默当作 OpenAI STT/TTS key。
- API websocket 启动 metadata 会根据 `settings.llm.provider=openrouter` 或 OpenRouter base URL，把 `llm.provider` 标记为 `openrouter`，但外层 websocket provider 仍保持 `pipecat`。
- 不一次性迁入所有 Pipecat 上游 providers：不同 provider 的 STT/TTS/LLM settings、frame shape、sample rate、voice 参数、turn detection 和错误分类并不统一；在真实浏览器音频 E2E 未通过前，全量扩展会放大未验证路径。后续按 STT、TTS、LLM、transport 四类逐个迁移和验收。

### 当前项目核心部分对齐程度

| 核心域 | 对齐底座 | 当前程度 | 状态判断 |
|:---|:---|:---:|:---|
| TrainingCore / 训练语义 | TalkWise 自有 | 75% | 已有 session、scenario、persona/stakeholder、report、progress、live guidance。TrainingCore 已通过 text runtime contract 明确只保存 ref/metadata，不接管正文、路径和分支状态。 |
| 文本 conversation / message tree | LibreChat | 80% | 已有 conversation CRUD、message tree、edit/retry/fork、path/search/search path context 验收；分支动作继续过滤结果类 metadata，正文和 selected path 已由 adapter/runtime 作为 source of truth。完整 LibreChat-style schema 仍未迁入。 |
| branch-aware review / history | LibreChat 验收标准 + TalkWise 语义 | 78% | 已有当前路径、tail、fork metadata remap、结果/历史展示和 replay-only metadata 验收；还缺真实 UI reload/fork 操作 E2E。 |
| model/provider registry | LibreChat + Pipecat | 55-60% | 已有 LLM registry、model specs、capability readiness。Pipecat realtime 内部 LLM provider 已开始支持 OpenRouter slice，但 Agent/Tool/MCP descriptor 与真实 runtime readiness 仍未统一成完整 provider/preset/runtime registry。 |
| auth / ACL / resource scope | LibreChat | 75-80% | conversation / file asset / agent config 的普通 repository 访问都要求显式 user/team scope；legacy stakeholder room escape hatch 已绑定 TrainingSession ACL 和 room_id。仍需真实 auth、admin override 和 legacy stakeholder scope 产品语义继续审计。 |
| MCP / Agent / Tool | LibreChat | 45-50% | 已有 capability inventory、Agent config 绑定扫描、具体 MCP server readiness 校验，以及复盘助手训练素材窄 tool consumer。descriptor-only 已明确为 warning/ready=false；仍不做通用 dispatcher/marketplace。 |
| realtime websocket / transcript | Pipecat | 80% | 已有 RealtimePipelineAdapter、provider-neutral transcript、audio output、turn/interruption/silence 事件、live guidance trigger、smoke contract、error taxonomy 和 runner telemetry summary；内部 LLM provider 可切 OpenRouter。独立 OpenAI realtime 和客户端转写持久化入口已删除。 |
| Pipecat runtime source of truth | Pipecat | 80% | `/training-studio/realtime` 默认走 Pipecat，旧 `provider=openai` 返回不支持；本机 capability 可返回 `readyForCall=true`，生产就绪仍由 `productionReadiness` 标记。内部 provider 矩阵从 OpenAI-only 推进到 OpenAI STT/TTS + OpenRouter LLM 的第一条可测组合；仍缺真实浏览器麦克风 E2E、聚合 tracing 和更多 Pipecat provider 逐项迁移。 |
| files / RAG / training materials | LibreChat | 60% | file asset ownership、服务层 scope、repository scope 和 training material 安全摘要/受控片段已补强；复盘素材对照卡片和素材对照 LLM adapter 已接入。素材全文/RAG/persona builder 自动接入仍不进入当前切片。 |
| usage / moderation / admin ops | LibreChat | 10-20% | 当前不是重点，只适合 auth/ACL 稳定后再迁。 |

第一部分结论：

- TalkWise 自己的训练产品层已经有 70% 以上的形状。
- LibreChat 文本底座约 55-60%，已经开始落到 conversation、capability、resource scope、message-tree action contract 和 text runtime source-of-truth contract，但还不是统一 LibreChat-style schema runtime。
- Pipecat realtime 底座约 75-80%，Pipecat-only runtime 已落地并区分 local readiness 与 production readiness；runner 已有基础 telemetry summary，剩余主要是真实浏览器音频 E2E 和更完整 metrics/tracing。
- MCP/Agent 已从早期 inventory 推进到 descriptor-only readiness contract；生产级 auth/ACL 仍未完整迁入 OAuth/LDAP/admin panel/permission override。

当前已经落地的方向是“先修边界，再迁 runtime”：

- 文本侧开始对齐 LibreChat 的 ownership / capability / message-tree 思路。
- 语音侧开始对齐 Pipecat 的 provider-neutral event lifecycle。
- TrainingCore 保持为上层产品语义，不被通用 chat/realtime runtime 接管。
- 产品层训练/实时入口保留优先；已废弃的独立 runtime/provider API 可以直接删除或折叠。前端根据 capability、auth、runtime availability 决定展示、置灰、折叠或提供 fallback。
- MCP / Agent / Tool 不要求现在暴露独立产品入口：先做 registry、discovery、readiness 和窄 tool consumer，入口按具体训练/管理 workflow 需要再接。

### 成熟项目未来可迁移能力

| 成熟项目能力 | 未来用途 | 当前可迁移状态 | 下一步 |
|:---|:---|:---:|:---|
| LibreChat conversation/message schema | 文本训练底座 | 已先选 adapter-owned 过渡契约 | 当前保留现有 conversation schema，并用 adapter 声明正文/路径/分支状态的 source of truth；后续再决定是否迁到 LibreChat-style schema。 |
| LibreChat message tree 行为 | edit/retry/fork/branch review | 高价值，可作为验收标准 | 把 LibreChat message-tree E2E 行为转成 TalkWise 测试矩阵。 |
| LibreChat auth / ACL | 用户、团队、资源权限 | 概念已进入核心资源和 legacy room scope | 下一步迁真实 auth、admin override 和 resource action matrix；继续减少 legacy unrestricted helper。 |
| LibreChat MCP / Agent / tools | 教练工具、素材检索、企业系统接入 | descriptor-only readiness 已落地 | registry/discovery/readiness 先保持 secret-free warning contract；继续接训练相关窄 consumer，不先造通用 dispatcher。 |
| LibreChat files/RAG/uploads | 训练材料、会议纪要、案例导入 | 可用但未迁 | 先统一 file resource ownership，再接 RAG/tool。 |
| LibreChat import/export/share | 训练复盘导入导出、团队分享 | 后置 | auth/ACL 和 report contract 稳定后做。 |
| Pipecat frame pipeline | 实时语音主 runtime | 高价值，部分接入 | 让 `RealtimePipelineAdapter` 变成 Pipecat adapter 主路径。 |
| Pipecat STT/TTS/LLM services | 多 provider 语音训练 | 已开始迁入 | 当前已从 OpenAI-only 扩到 OpenAI STT/TTS + OpenRouter LLM 的窄切片。下一步按 provider 能力矩阵继续迁 Deepgram/Whisper STT、ElevenLabs/OpenAI TTS、更多 LLM service；每个 provider 必须有 readiness、secret-safe error taxonomy 和事件契约测试。 |
| Pipecat VAD/turn/interruption | 打断、沉默、轮次检测 | 已有事件映射和 telemetry summary，待真实音频验收 | 已产出 TalkWise 可读事件：user turn started/stopped、assistant speaking、interrupted、silence timeout，并在 runner summary 中聚合 turn/interruption/silence；下一步接真实浏览器 E2E 和训练压力/复盘指标。 |
| Pipecat transport / WebRTC | 视频/会议式训练 | 后置 | WebSocket 稳定后再考虑 WebRTC/LiveKit/Daily。 |
| Pipecat observability | latency、turn、provider error | 基础 session summary 已落地 | 下一步补跨 session 聚合 tracing、真实配置 smoke 和前端/后端联动诊断。 |

第二部分结论：

- LibreChat 未来主要提供平台化能力扩展面：auth、ACL、MCP、Agent、files、RAG、provider registry、message-tree 验收。
- Pipecat 未来主要提供实时能力扩展面：pipeline、STT/TTS/LLM services、VAD、turn/interruption、transport、observability。
- 当前可迁移能力已经分层识别清楚，但实际代码迁移仍处于前两层：capability inventory、resource scope、Pipecat transcript event。

后续更新规则：

1. 每轮迁移后，先更新“当前项目核心部分对齐程度”的百分比和状态判断。
2. 如果某个能力从 inventory 进入 runtime，应同步更新“成熟项目未来可迁移能力”的当前状态。
3. 不把 TalkWise 训练语义迁给 LibreChat/Pipecat；只把通用底座、运行时、权限、工具、观测和验收标准迁入。
4. 若新增能力无法明确归入 LibreChat 或 Pipecat，应优先判断它是不是 TalkWise 产品语义；如果不是，再决定是否需要引入新的成熟底座。

## LibreChat 功能域适配

| 功能域 | LibreChat 成熟资产 | 适配等级 | TalkWise 落地方式 |
|:---|:---|:---|:---|
| conversation runtime | conversation/message 数据模型、ChatRoute、ConvoOptions、conversation management、search | 高 | 作为文本底座候选。先建立 TalkWise `TrainingConversationAdapter`，再决定迁移 schema 还是保留当前表加兼容层。 |
| message tree / branch | regenerate、sibling branch、edit save-and-submit、fork visible/branches/all target、reload retain branch 的 E2E 覆盖 | 高 | 直接作为文本分支验收标准。TalkWise 分支 metadata 只作为 replay context，不影响 scoring/completion。 |
| SSE / resumable streams | adaptive/resumable SSE、step handler、event handler、多 tab/恢复语义 | 高 | 替换或对齐当前文字流式回复，后续支撑训练过程中的稳定追问和断线恢复。 |
| provider/model endpoint | OpenAI、Anthropic、Azure、Google、Bedrock、custom endpoints、model specs、presets | 高 | 迁为统一模型注册/选择层。TalkWise training prompt/rubric 作为上层配置，不直接绑定单 provider。 |
| auth/session | OAuth2、LDAP、email login、2FA、JWT/session、social login | 高 | 中期迁入。短期继续 mock user/role，但 API 契约按未来真实用户/团队/权限设计。 |
| roles/groups/ACL/admin | user/group/role、permission override、admin panel、resource permissions | 高 | 优先迁认证边界思想和 ACL 数据形状；完整 UI 管理面板分阶段迁入。 |
| MCP/Agent/tools | MCP server 管理、OAuth MCP、tool discovery/call、Agent builder/marketplace、skills/subagents | 高 | 作为 TalkWise 教练工具、素材分析、外部资料检索、企业系统接入的扩展底座。不要先自研 MCP runtime。 |
| files/RAG/uploads | files、file search、SharePoint/Google picker、upload ownership、agent file ownership | 中高 | 用于训练素材、会议纪要、邮件/聊天记录导入。先迁文件权限和引用模型，再迁复杂 RAG。 |
| memory/projects/prompts/bookmarks | memory、projects、prompts、bookmarks、sharing | 中高 | 映射为用户训练档案、场景集合、可复用话术/训练模板。不要照搬通用收藏 UI。 |
| import/export/share | ChatGPT/LibreChat import、markdown/json/screenshot export、shared links | 中 | 用于训练记录导入、复盘导出、教练/团队分享。注意训练隐私默认更严格。 |
| artifacts/code interpreter/image | artifacts、code interpreter、image generation/editing | 中低 | 不是近期核心。仅在训练报告可视化、材料生成、案例演示需要时按工具迁入。 |
| web search | search + scraper + reranker | 中 | 可作为训练资料增强或 live coach 工具，不放入第一批训练闭环。 |
| token usage/moderation/balance | usage、token credits、moderation | 中 | 生产化需要，但在 auth/ACL 之后。 |
| i18n/a11y/UI polish | 多语言、可访问性、成熟聊天 UI 组件 | 中高 | 借鉴交互和验收，不整站搬皮肤。TalkWise 保持训练工具型界面。 |
| deployment/config | Docker、config yaml、CDN/S3、admin config override | 中 | 生产化阶段迁移配置思想，避免现阶段过早引入重量部署面。 |

LibreChat 不应迁入的方式：

- 不把 TalkWise 训练报告、评分、成长体系改成通用 chat history。
- 不为了“像 LibreChat”重写全部前端；先迁运行时、权限、分支、模型、Agent/MCP。
- 不先搬 Code Interpreter、image generation、marketplace UI 这类非训练闭环核心能力。

## Pipecat 功能域适配

| 功能域 | Pipecat 成熟资产 | 适配等级 | TalkWise 落地方式 |
|:---|:---|:---|:---|
| frame pipeline | `Pipeline`、`PipelineTask`、`FrameProcessor`、parallel/sync pipeline、service switcher | 高 | 作为 realtime voice 唯一运行抽象。当前 `RealtimePipelineAdapter` 应逐步变成 Pipecat adapter，而不是并存多个自研 runtime。 |
| STT/TTS/LLM services | OpenAI、Deepgram、ElevenLabs、MiniMax、Google、Azure、Whisper、Ollama、OpenRouter 等 | 高 | 第一批只启用 OpenAI STT/TTS/LLM + 当前已有 provider；其它作为配置扩展，不重复写 adapter。 |
| VAD/turn/interruption | Silero VAD、Krisp/AIC/RNNoise、smart turn、user turn start/stop、mute、idle、interruption | 高 | 直接支撑电话式训练：自动起止、打断、沉默、追问和压力升级。 |
| WebSocket/FastAPI transport | FastAPI websocket、client/server websocket、base input/output transport | 高 | 优先替换当前薄 websocket 语音链路。前端保持 TalkWise UI，后端运行 Pipecat transport。 |
| WebRTC/LiveKit/Daily | smallwebrtc、LiveKit、Daily、local transports | 中高 | WebSocket 先稳定；视频会议式训练进入 Phase 3/4 时再选 WebRTC/LiveKit/Daily。 |
| OpenAI realtime/S2S | OpenAI realtime STT/S2S、Responses、Grok/Gemini/Nova Sonic 等 | 高 | 只允许作为 Pipecat service/config 能力进入，不再维护独立 OpenAI websocket/SDP runtime 分支。 |
| RTVI | RTVI processor/observer/UI protocol | 中高 | 后续前端实时状态、配置、metrics 可对齐 RTVI；第一轮不强制引入完整客户端 SDK。 |
| audio processing | resamplers、mixers、filters、audio buffer、word timestamp | 中高 | 用于语音复盘指标：停顿、语速、重叠、输出同步、环境音。 |
| observability/metrics/tracing | latency observer、turn tracking、startup timing、OpenTelemetry、Sentry | 中高 | 进入 P1。实时训练必须有延迟、turn、错误原因和 provider 事件可观测。 |
| evals | speech/eval harness/judge/scenario | 中 | 可反向支撑 TalkWise 自己的训练质量评估，但不替代 TalkWise rubric。 |
| flows | structured conversations、stateful flow examples | 中 | 可参考训练回合/场景状态机，但 TalkWise scenario/dispatcher 是上层产品语义。 |
| workers/bus/distributed | worker、LLM worker、UI worker、bus、Redis/PGMQ | 中 | 后续多 agent/并行 coach/企业部署可迁；第一轮不引入分布式复杂度。 |
| phone/telephony serializers | Twilio、Vonage、Telnyx、Plivo、WhatsApp、Genesys | 低到中 | 只有当产品进入电话演练/客服场景时迁入。 |
| avatar/video services | HeyGen、Tavus、Simli、LemonSlice | 低到中 | 视频虚拟人后置，不进入当前成熟底座第一轮。 |
| CLI/project generation | `pipecat init`、service registry、template/tests | 中 | 可借鉴 readiness/service registry 和本地测试方式，不把 TalkWise 变成 Pipecat scaffold 项目。 |

Pipecat 不应迁入的方式：

- 不让 Pipecat 接管训练语义、评分、成长档案。
- 不在第一轮启用所有 services/transports；先形成一个可测 OpenAI/Pipecat realtime path。
- 不把视频虚拟人、电话运营商、分布式 workers 提前放进核心路径。

## TalkWise 应保留的产品层

以下能力是 TalkWise 的护城河，不从 LibreChat/Pipecat 通用能力中直接替代：

- 训练目标配置：场景、难度、表达框架、角色、等级、问题配比。
- persona/stakeholder：5-layer persona、组织关系、隐藏议程、压力风格。
- scenario/dispatcher：首问、追问、压力升级、结束条件、多人/多角色调度。
- evaluation/growth/report：六维评分、证据、建议、成长路径、复训计划。
- live guidance：风险提醒、下一句建议、行动项、实时教练事件沉淀。
- branch-aware review：当前路径、尾节点、分叉点、最后回复、metadata 来源、空状态。

这些能力应实现为 mature runtime 之上的 adapter/workflow/plugin，而不是和 runtime 混在一起。

## 目标架构

```text
LibreChat-style text runtime
  -> TrainingConversationAdapter
  -> TrainingCore / scenario / persona / dispatcher / evaluation
  -> result/history/growth

Pipecat realtime runtime
  -> RealtimePipelineAdapter / TrainingTranscriptSink
  -> TrainingCore / live guidance / transcript persistence
  -> result/history/growth

LibreChat auth/ACL/MCP/Agent
  -> TalkWise resource policy / coach tools / training material tools
  -> Training Studio product workflows
```

边界原则：

- `TrainingCore` 不拥有完整聊天 runtime。
- `TrainingCore` 不拥有完整语音 runtime。
- branch selected path 是复盘上下文，不是评分完成状态。
- realtime provider event 进入 TalkWise 前必须转成 provider-neutral event。
- auth/ACL 最终要保护 conversation、training session、report、guidance、file/material、agent/tool resource。

## 第一批落地优先级

### P0: 迁移边界和契约

1. 文本 runtime 的当前 source of truth 先落在 `TrainingConversationAdapter` / conversation runtime：TrainingCore 只保存 ref/metadata；后续再评估是否把底层 schema 迁到 LibreChat-style schema。
2. 固化 `TrainingConversationAdapter`：create conversation、append turn、recent turns、selected path、branch tail、fork metadata。
3. 固化 `RealtimePipelineAdapter`：Pipecat start/append/commit/events/close、audio output、final transcript、provider error。
4. 固化 resource scope：conversation/session/report/progress/guidance 都必须带 user/team scope。
5. 把 branch metadata schema 写成文档和测试 fixture，禁止 scoring/growth 被通用 branch metadata 覆盖。

### P1: 文本底座对齐 LibreChat

1. 用 LibreChat `message-tree.spec.ts` 的行为改写 TalkWise 文本分支验收：regenerate、edit branch、fork visible/direct/branch、reload 保留路径。
2. 对齐 search/history：搜索结果必须能带 path context。
3. 对齐 SSE：文字回复和重试不应因断线丢状态。
4. 引入 model/provider/preset registry，避免训练页直接绑定单一 LLM 配置。

### P1: Realtime 底座收敛 Pipecat

1. 当前 `/realtime/capabilities` 保留，前端按 capability / auth / runtime state 视情况展示；readiness 来源应优先来自 Pipecat adapter capability。
2. OpenAI realtime 独立 websocket/SDP 路径不再保留；OpenAI 只作为 Pipecat service/config 能力，旧 provider alias 返回不支持。
3. 接入 Pipecat VAD/turn/interruption，产生 TalkWise 可读事件：user_turn.started/stopped、assistant_speaking、interrupted、silence_timeout。
4. audio output、transcript.done、guidance trigger 必须都落到同一 Training Session，并能在 runner telemetry summary 中聚合。

### P1: API 鉴权/隔离

1. 扩展现有 mock user/role 测试，覆盖 conversation/chat/training/report/guidance/realtime binding。
2. 从 LibreChat ACL 迁概念：resource type、owner、group/team、role action。
3. 先做最小 guard，不重构完整 auth 系统。

### P2: Agent/MCP/工具层

1. 继续迁 LibreChat MCP server registry、OAuth flow、tool discovery/call 的最小子集；当前 readiness 仍只声明 descriptor-only，不启动 dispatcher/runtime。
2. 先落地训练相关工具：素材检索、会议纪要分析、persona builder、复盘报告生成、企业知识查询。
3. Agent marketplace、skills/subagents 作为后续扩展，不进入第一轮训练闭环，也不先暴露独立产品入口。

### P2: 文件/素材/RAG

1. 训练素材统一 file resource，带 owner/team/usage scope。
2. Persona Builder 和 scenario import 使用同一文件权限模型。
3. RAG/file search 接入 coach/agent，不直接污染核心训练 session。

## 建议的多智能体切片

后续一轮可以按下面拆：

| Agent | 只读/写范围 | 目标 |
|:---|:---|:---|
| LibreChat/text branch agent | `frontend/src/components/chat`、`frontend/src/services/trainingConversation.ts`、`backend/application/services/conversation_service.py`、相关测试 | 对齐 message tree 行为和验收差距。 |
| Review/history agent | `TrainingResultPage`、`TrainingHistoryPage`、`trainingSession.ts`、报告/进度测试 | 把 branch-aware review 固化为契约。 |
| Pipecat/realtime agent | `application/ports/realtime.py`、`training_studio/realtime_*`、`api/routes/training_studio.py`、realtime tests | 收敛 Pipecat readiness/runtime/audio output。 |
| API isolation agent | `api/conversation_scope.py`、`api/dependencies.py`、conversation/chat/training tests | 扩展 mock user/role 边界，不动完整 auth。 |
| MCP/Agent explorer | LibreChat `packages/api/src/mcp`、`oauth`、`agents`、`client/src/components/MCP` | 先产出迁移边界，不直接写业务代码。 |

主线程仍负责 code-review graph、合并、全量验证和暂存。

## 验收命令

每轮稳定改动后执行：

```powershell
cd frontend
node --test tests\*.mjs
npm run build

cd ..\backend
..\.venv-backend\Scripts\python.exe -m pytest tests

cd ..
git diff --check
```

文档或分析轮可只跑：

```powershell
git diff --check
git diff --cached --check
```

## 下一步

建议下一轮不是继续泛化讨论，而是做 P0 契约落地：

1. 写 `docs/adr` 或 `docs/plans` 的 `TrainingConversationAdapter` / `RealtimePipelineAdapter` 数据契约。
2. 用现有 tests 固化 branch metadata 不影响 scoring/growth/completion。
3. 用 Pipecat readiness/capability 做后端单一真源，前端只展示结构化结果。
4. 把下一批切片转到 MCP/Agent/Tool 和 file/resource ownership，优先做内部能力和 workflow 入口，不先做主导航暴露。

这四件事完成后，再进入 LibreChat text runtime 和 Pipecat runtime 的具体迁移会更稳。


## 2026-07-18 进度快照

本轮已落地:

- `POST /training-studio/sessions/{id}/complete` 现在支持 `metadata`，并把完成时的分支选择写回 `task_config.metadata`
- `ChatPage` 完成训练时会把当前 `messageTreeSelection` 序列化成 replay-only metadata
- 前后端测试已经覆盖 `complete -> session persistence -> branch info round-trip`

当前判断:

- 文本 conversation / message tree: 约 50-60%
- auth / ACL: 约 40-50%
- Pipecat realtime: 约 45-55%
- MCP / Agent: 约 15-20%

下一步建议:

1. 先把 realtime readiness / error 映射收敛成单一 helper
2. 再补 conversation child-route auth matrix
3. 之后再做 opt-in text runtime start path

## 2026-07-18 继续进度

本轮补上了 conversation child-route auth boundary 的统一覆盖：

- `backend/tests/test_conversation_auth_boundary.py` 新增参数化用例，覆盖 `/messages`、`/messages/{id}/path`、`/messages/{id}/locate`、`/messages/{id}/children`、`/messages/{id}/fork`、`/messages/{id}/edit`、`/messages/{id}/retry`、`/runs`
- 验证结果：
  - `frontend: node --test tests\\*.mjs`
  - `frontend: npm run build`
  - `backend: .\\.venv-backend\\Scripts\\python.exe -m pytest backend\\tests`
  - `git diff --check`

当前判断不变：

- `text runtime start path` 仍然是下一块更值钱的生产性切片
- `Pipecat readiness helper` 和纯 `API isolation` 先作为补强项保留
## 2026-07-18 text runtime start path

本轮已完成：
- `POST /training-studio/sessions/{id}/start` 在 `runtime=conversation_message_tree` / provider alias 下进入 `TrainingCoreOrchestrator.start_existing_session`
- `TrainingSessionService.start_session` 支持 `metadata`，可把 conversation branch / replay metadata 写回 `task_config.metadata`
- `ConversationTrainingConversationAdapter` 过滤 task_config 里的 owner/team 伪造字段，并用 session 的 `user_id/team_id` 重写 `ownerUserId` / `teamId` / `authScope`
- 相关覆盖已落在 session service、training core、conversation adapter 和 API start path

当前判断：
- 文本 conversation / message tree: 60-70%
- auth / ACL: 50-60%
- Pipecat realtime: 45-55%
- MCP / Agent: 15-20%

下一步：
1. 单独收敛 Pipecat readiness / error helper
2. 再补 conversation child-route auth matrix
3. 如有需要，再把前端启动入口显式切到 `runtime=conversation_message_tree`

## 2026-07-19 API isolation 收口

本轮已确认：

- API 侧的 conversation / session / report / guidance / realtime 边界已经进入统一收口阶段，不再只是单点 mock boundary。
- 文本启动路径、realtime 辅助分类、旧路由 alias 清理和训练启动 flow 抽取，都在把成熟底座切片落到同一条产品线。
- 训练语义继续保留在 TalkWise 层，下一批更值得做的是 Pipecat runtime source of truth 和 MCP/Agent/Tool 的最小子集。
- 训练/实时相关页面、菜单和路由入口先保留，前端只在 capability、权限和 runtime 可用时展示、置灰或折叠；MCP/Agent/Tool 先不做主导航暴露。

当前判断：

- 文本 conversation / message tree: 60-70%
- auth / ACL / resource scope: 70%
- Pipecat realtime: 55-60%
- MCP / Agent: 15-20%

下一步建议：

1. 继续把 Pipecat readiness / error / transcript 收束到单一 runtime source of truth。
2. 开始 MCP / Agent / Tool 的最小可迁移子集。
3. 再补 file / RAG / training material 的 resource ownership。

## 2026-07-19 MCP / Agent readiness 最小子集

本轮已落地：

- `/training-studio/llm-registry` 继续作为文本 runtime、Agent、Tool、MCP 的 secret-free readiness 入口。
- `settings.capability_inventory` 支持 descriptor-only `tool_configs`、`mcp_servers`，用于解析 agent `tool_ids` / `mcp_server_ids` 绑定状态。
- scoped agent config inventory 从单页读取改为受限分页扫描，默认最多扫描 200 条，避免创建多个 agent 后 readiness 漏报。
- MCP server 和 tool 配置只进入 capability registry，不启动 MCP server、不执行 tool、不引入通用 dispatcher。
- 前端不新增 MCP / Agent 主导航入口；继续在 Training Studio readiness 面板中按 capability 状态展示。

当前判断：

- MCP / Agent / Tool: 20-25%
- auth / ACL / resource scope: 60-70%
- model/provider registry: 50-60%

下一步建议：

1. 先接一个训练相关的窄 tool consumer，例如素材检索或 persona builder，不做完整通用 tool runtime。
2. 补 file / training material resource ownership，再让 tool consumer 只读取有权限的素材。
3. Pipecat 侧继续推进 runtime source of truth，把 OpenAI realtime 独立路径降为 Pipecat service/fallback。

## 2026-07-19 Pipecat-only realtime 收敛

本轮按“可以直接删除，直接走 Pipecat”的决策落地：

- 后端删除独立 OpenAI realtime adapter、`/training-studio/realtime/sdp` SDP 代理、`/training-studio/realtime/transcripts` 客户端转写持久化入口。
- 后端 `/training-studio/realtime` 默认 provider 改为 `pipecat`，旧 `provider=openai` 直接返回 `UNSUPPORTED_REALTIME_PROVIDER`。
- 后端 WebSocket 不再接受客户端直接发送 final transcript 事件；`transcript.done -> transcript.persisted -> training.live_guidance.triggered` 只从 Pipecat pipeline runner 事件流进入持久化。
- `realtime_runtime_for_provider` 将 legacy OpenAI realtime alias 折叠为 Pipecat runtime，OpenAI 仅作为 Pipecat STT/TTS/LLM 服务配置保留。
- 前端 `RealtimeVoiceRecorder` 从 WebRTC/SDP 改为 Pipecat WebSocket：浏览器采集麦克风，编码 PCM16，消费后端 `audio.output` 和 `transcript.persisted`。
- `/realtime/capabilities` 和 Training Studio readiness 面板不再把 OpenAI Realtime 当作可发起通话的 peer runtime；OpenAI key/model/voice 只作为 Pipecat OpenAI STT/TTS/LLM 服务配置。
- Settings 页移除已废弃的 Call URL，`REALTIME_OPENAI_CALL_URL` / `REALTIME_OPENAI_WS_URL` 只在配置层保留为 legacy `.env` 容忍字段。

focused 验证：

- `frontend: node --test tests\\realtimeSession.test.mjs`
- `frontend: node --test tests\\realtimeSession.test.mjs tests\\trainingConversation.test.mjs tests\\trainingStudio.test.mjs`
- `backend: ..\\.venv-backend\\Scripts\\python.exe -m pytest tests\\test_training_studio_realtime_api.py tests\\application\\test_training_studio_realtime_pipeline.py tests\\test_training_studio_api.py`

当前判断：

- Pipecat realtime: 65-70%。可见入口已切到 Pipecat，独立 OpenAI runtime 已移除；仍缺真实浏览器音频链路端到端验收、VAD/turn/interruption 更完整事件、metrics/tracing。
- auth / ACL / resource scope: 60-70%。realtime binding 仍走现有 user/team scope，旧 REST 转写逃逸入口已删除。
- MCP / Agent / Tool: 40-45%。训练素材窄 consumer 已从 inventory 进入复盘助手产品闭环，但仍不做通用 dispatcher/marketplace。

下一步建议：

1. 素材对照质量下一步只做 LLM 输出质量评估、提示词微调、异常观测和真实配置 smoke；继续保留 deterministic fallback 和 source_state/limits。
2. auth / ACL 已进入核心切片；下一步继续收口服务层 `metadata_scope=None` 的 full-access footgun、真实用户/团队 auth，以及 TrainingSession admin scope 的产品语义。
3. 再决定 persona builder 或报告辅助生成哪一个窄 consumer 值得继续；仍不做通用 RAG、Agent marketplace 或主导航入口。

延期待完成：

- 真实浏览器验证本轮不做。后续用连接浏览器或 FlowGuide 验证 Pipecat WebSocket 录音、音频输出和转写持久化的真实 UI 行为。
- Text runtime / message-tree 的真实 UI reload/fork 操作 E2E 单独排期靠后；当前测试矩阵先覆盖服务契约和 branch metadata 不污染 scoring/growth/completion。
