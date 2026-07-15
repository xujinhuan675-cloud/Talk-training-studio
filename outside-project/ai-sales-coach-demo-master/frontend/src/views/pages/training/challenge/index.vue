<template>
  <div class="training-challenge-page">
    <!-- ===== View: 场景选择 ===== -->
    <template v-if="view === 'list'">
      <page-header title="闯关陪练" desc="选择一个销售场景，与 AI 模拟客户完成对话演练。">
        <div class="header-filters">
          <el-select v-model="filter.difficulty" size="small" clearable placeholder="全部难度" class="filter-select" @change="loadList">
            <el-option label="简单" :value="1" />
            <el-option label="中等" :value="2" />
            <el-option label="困难" :value="3" />
            <el-option label="专家" :value="4" />
          </el-select>
          <el-select v-model="filter.is_required" size="small" clearable placeholder="全部类型" class="filter-select" @change="loadList">
            <el-option label="必练" :value="1" />
            <el-option label="非必练" :value="0" />
          </el-select>
          <el-input
            v-model="filter.keyword"
            size="small"
            placeholder="搜索场景"
            clearable
            class="search-input"
            @keyup.enter.native="loadList"
            @blur="loadList"
            @clear="loadList"
          />
        </div>
      </page-header>

      <div v-if="!loading && scenarios.length === 0" class="empty-state">
        <div class="empty-icon">🎯</div>
        <div class="empty-title">暂无可练习场景</div>
        <div class="empty-desc">请联系管理员在「陪练配置」中添加场景</div>
      </div>

      <div class="scenario-grid" v-loading="loading">
        <div v-for="sc in scenarios" :key="sc.id" class="scenario-card">
          <div class="scenario-card__head">
            <div class="scenario-name" :title="sc.name">{{ sc.name }}</div>
            <el-tag size="mini" :type="difficultyTag(sc.difficulty)" class="difficulty-tag">{{ difficultyLabel(sc.difficulty) }}</el-tag>
          </div>
          <div class="scenario-desc">{{ sc.scene_desc || '-' }}</div>
          <div class="scenario-persona"><span class="persona-label">客户画像：</span>{{ sc.persona || '-' }}</div>
          <div class="scenario-tags">
            <span :class="['ds-chip', Number(sc.is_required) === 1 ? 'ds-chip--required' : 'ds-chip--optional']">
              {{ Number(sc.is_required) === 1 ? '必练' : '非必练' }}
            </span>
            <template v-if="Number(sc.my_practice_count) > 0">
              <span class="ds-chip ds-chip--practice">已练 {{ sc.my_practice_count }} 次</span>
              <span v-if="sc.my_latest_score !== null" class="ds-chip ds-chip--score">最近 {{ sc.my_latest_score }}</span>
              <span v-else class="ds-chip ds-chip--score-empty">暂无分数</span>
            </template>
            <template v-else>
              <span class="ds-chip ds-chip--practice">未练习</span>
              <span class="ds-chip ds-chip--score-empty">暂无分数</span>
            </template>
          </div>
          <button class="ds-gradient-btn" :disabled="startingId === sc.id" @click="onStart(sc)">
            <i v-if="startingId === sc.id" class="el-icon-loading" />
            开始练习
          </button>
        </div>
      </div>
    </template>

    <!-- ===== View: 闯关对话 ===== -->
    <template v-else-if="view === 'session'">
      <div class="session-page">
        <!-- 顶栏 -->
        <div class="session-topbar">
          <a class="session-back" @click="onBack"><i class="el-icon-arrow-left" /> 返回</a>
          <div class="session-title-pill">{{ activeScenario.name }}</div>
          <button class="session-end-btn" :disabled="ending" @click="onEnd">
            <i v-if="ending" class="el-icon-loading" />
            结束练习
          </button>
        </div>

        <!-- 场景信息卡 -->
        <div class="scene-banner">
          <div class="banner-tags">
            <span :class="['scene-tag', `scene-tag--diff-${activeScenario.difficulty}`]">{{ difficultyLabel(activeScenario.difficulty) }}</span>
            <span v-if="Number(activeScenario.is_required) === 1" class="scene-tag scene-tag--required">必练</span>
          </div>
          <div class="banner-row">
            <span class="banner-label">客户画像：</span><span class="banner-text">{{ activeScenario.persona || '-' }}</span>
          </div>
          <div class="banner-row">
            <span class="banner-label">场景描述：</span><span class="banner-text">{{ activeScenario.scene_desc || '-' }}</span>
          </div>
        </div>

        <!-- 聊天区（消息流 + 输入框 整体外框卡片） -->
        <div class="chat-shell">
          <!-- 消息流 -->
          <div ref="msgList" class="msg-list">
            <div v-if="messages.length === 0" class="msg-empty">
              <div class="msg-empty__icon"><i class="el-icon-chat-dot-square" /></div>
              <div class="msg-empty__title">{{ hasOpening ? '客户已开口，请接住对话' : '本场景未配置客户开场白' }}</div>
              <div class="msg-empty__desc">{{ hasOpening ? '' : '请主动向客户开场，开启本次练习…' }}</div>
            </div>
            <div v-for="m in messages" :key="m.id || m.seq" :class="['msg-row', Number(m.role) === 2 ? 'role-seat' : 'role-customer']">
              <div class="msg-avatar" v-if="Number(m.role) !== 2">客</div>
              <div class="msg-bubble">{{ m.content }}</div>
            </div>
            <div v-if="aiReplying" class="msg-row role-customer ai-typing">
              <div class="msg-avatar">客</div>
              <div class="msg-bubble msg-bubble--typing">
                <span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span>
              </div>
            </div>
          </div>

        <!-- 输入框 -->
        <div class="composer">
          <div class="composer-input-wrap">
            <textarea
              ref="composer"
              v-model="composerText"
              class="composer-input"
              rows="3"
              placeholder="输入您想对客户说的话，Enter 发送，Shift+Enter 换行"
              @keydown.enter.exact.prevent.stop="onComposerEnter"
              @compositionstart="composing = true"
              @compositionend="composing = false"
            />
          </div>
          <div class="composer-actions">
            <button
              v-if="speechSupported"
              type="button"
              class="composer-btn composer-btn--voice"
              :class="{ 'is-active': recognizing }"
              :disabled="sending"
              @mousedown.prevent.stop
              @click.prevent.stop="toggleVoiceInput"
            >
              <i :class="recognizing ? 'el-icon-loading' : 'el-icon-microphone'" />
              <span class="composer-btn-text">{{ recognizing ? '识别中' : '语音' }}</span>
            </button>
              <button
                type="button"
                class="composer-btn composer-btn--send"
                :disabled="!canSend"
                @mousedown.prevent.stop
                @click.prevent.stop="sendText"
              >
                <i v-if="sending" class="el-icon-loading" />
                <i v-else class="el-icon-position" />
                <span class="composer-btn-text">发送</span>
              </button>
          </div>
        </div>
      </div>
      </div>
    </template>
  </div>
</template>

<script>
import API from '@/api'
import PageHeader from '@/components/PageHeader/index.vue'

const DIFFICULTY_LABELS = { 1: '简单', 2: '中等', 3: '困难', 4: '专家' }
const DIFFICULTY_TAGS = { 1: 'success', 2: 'info', 3: 'warning', 4: 'danger' }

export default {
  name: 'TrainingChallenge',
  components: { PageHeader },
  data() {
    return {
      view: 'list',
      loading: false,
      filter: { keyword: '', difficulty: '', is_required: '' },
      scenarios: [],
      startingId: null,

      // Session 上下文
      activeScenario: {},
      sessionId: null,
      hasOpening: false,
      messages: [],
      composerText: '',
      composing: false,
      sending: false,
      ending: false,
      aiReplying: false,        // perception-ai 客户回复等待中
      _aiPollTimer: null,

      // 语音输入使用浏览器 Web Speech API；不支持时隐藏按钮，避免坏入口。
      speechSupported: typeof window !== 'undefined' && !!(window.SpeechRecognition || window.webkitSpeechRecognition),
      voiceRecognition: null,
      recognizing: false,
    }
  },
  async created() {
    await this.handleRouteEntry()
  },
  computed: {
    canSend() {
      return !!(this.composerText || '').trim() && !this.sending
    }
  },
  activated() {
    // 兼容 keep-alive 缓存：每次进入路由都尝试处理一次
    this.handleRouteEntry()
  },
  beforeDestroy() {
    this.stopVoiceInput()
    if (this._aiPollTimer) {
      clearInterval(this._aiPollTimer)
      this._aiPollTimer = null
    }
  },
  methods: {
    difficultyLabel(d) { return DIFFICULTY_LABELS[d] || '-' },
    difficultyTag(d) { return DIFFICULTY_TAGS[d] || '' },

    async handleRouteEntry() {
      const sessionIdQuery = String(this.$route.query.session_id || '').trim()
      // 评分页"再练一次" → 已带新 session_id，直接进入对话视图
      if (sessionIdQuery && (!this.sessionId || this.sessionId !== sessionIdQuery)) {
        await this.enterExistingSession(sessionIdQuery)
        return
      }
      // 默认场景列表流程
      if (this.scenarios.length === 0) await this.loadList()
    },

    async enterExistingSession(sid) {
      try {
        const res = await API.trainingSessionDetail({ session_id: sid })
        const data = res.data || {}
        if (!data.session) {
          await this.loadList()
          return
        }
        this.activeScenario = data.session
        this.sessionId = sid
        this.messages = (data.messages || []).map(m => ({
          id: m.id, seq: m.seq, role: m.role, content: m.content
        }))
        this.hasOpening = this.messages.length > 0
        this.composerText = ''
        this.view = 'session'
        // 清掉 query，刷新或返回时不会重复进入
        this.$router.replace({ path: this.$route.path }).catch(() => {})
        this.$nextTick(() => this.scrollToBottom())
      } catch (e) {
        await this.loadList()
      }
    },

    async loadList() {
      this.loading = true
      try {
        const res = await API.trainingScenarioListForUser({
          keyword: this.filter.keyword,
          difficulty: this.filter.difficulty,
          is_required: this.filter.is_required
        })
        this.scenarios = res.data || []
      } finally {
        this.loading = false
      }
    },

    async onStart(sc) {
      this.startingId = sc.id
      try {
        const res = await API.trainingStartSession({ scenario_id: sc.id })
        const payload = res.data || {}
        this.activeScenario = payload.scenario || sc
        this.sessionId = payload.session_id
        this.hasOpening = !!payload.has_opening
        this.messages = []
        if (payload.has_opening && payload.opening_message) {
          this.messages.push({ seq: 1, role: 1, content: payload.opening_message })
        }
        this.composerText = ''
        this.view = 'session'
        this.$nextTick(() => this.scrollToBottom())
      } finally {
        this.startingId = null
      }
    },

    onBack() {
      this.$confirm('演练尚未结束，确定要离开吗？返回后本次练习不会被保存。', '离开演练', { type: 'warning' })
        .then(() => {
          this.view = 'list'
          this.messages = []
          this.sessionId = null
          this.loadList()
        })
        .catch(() => {})
    },

    onComposerEnter(e) {
      if (this.composing) return
      if (e.shiftKey) return
      this.sendText()
    },

    async sendText() {
      const text = (this.composerText || '').trim()
      if (!text || this.sending) return
      if (!this.sessionId) {
        this.$message.warning('会话尚未创建，请重新选择场景开始练习')
        return
      }
      this.sending = true
      // 乐观加入坐席消息
      const tempSeq = (this.messages.length ? this.messages[this.messages.length - 1].seq + 1 : 1)
      this.messages.push({ seq: tempSeq, role: 2, content: text })
      this.composerText = ''
      this.$nextTick(() => this.scrollToBottom())
      try {
        const res = await API.trainingSendMessage({ session_id: this.sessionId, content: text })
        const data = res.data || {}
        // 替换为服务器返回（保证 seq / id 一致）
        if (data.seat_message) {
          this.messages.splice(this.messages.length - 1, 1, data.seat_message)
        }
        // 异步模式：后端立即返回 pending_customer_reply，AI 客户回复 3-10s 后通过回调写库
        // → 启动轮询 messageList 拉取新增的 customer 消息
        if (data.pending_customer_reply) {
          this.aiReplying = true
          this.$nextTick(() => this.scrollToBottom())
          this._pollAiReply()
        }
      } catch (e) {
        // 拦截器已弹窗；移除乐观消息
        this.messages.pop()
      } finally {
        this.sending = false
      }
    },

    toggleVoiceInput() {
      if (this.recognizing) {
        this.stopVoiceInput()
      } else {
        this.startVoiceInput()
      }
    },

    startVoiceInput() {
      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
      if (!SpeechRecognition) {
        this.$message.warning('当前浏览器不支持语音输入，请使用新版 Chrome 或 Edge')
        return
      }
      if (this.recognizing) return

      const recognition = new SpeechRecognition()
      recognition.lang = 'zh-CN'
      recognition.interimResults = true
      recognition.continuous = false

      const originalText = this.composerText || ''
      let finalText = ''
      recognition.onresult = event => {
        let interimText = ''
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const text = event.results[i][0].transcript
          if (event.results[i].isFinal) finalText += text
          else interimText += text
        }
        this.composerText = `${originalText}${finalText}${interimText}`.trim()
      }
      recognition.onerror = event => {
        this.recognizing = false
        this.voiceRecognition = null
        const msg = event && event.error === 'not-allowed'
          ? '麦克风权限未授权'
          : '语音输入失败，请改用键盘输入'
        this.$message.warning(msg)
      }
      recognition.onend = () => {
        this.recognizing = false
        this.voiceRecognition = null
      }

      this.voiceRecognition = recognition
      this.recognizing = true
      recognition.start()
    },

    stopVoiceInput() {
      if (this.voiceRecognition) {
        try { this.voiceRecognition.stop() } catch (e) {/* noop */}
      }
      this.recognizing = false
      this.voiceRecognition = null
    },

    /**
     * 轮询 messageList 拉取 AI 客户回复（perception-ai 异步回调写入后被拉到）
     * 每 1.5s 一次，最长 30s 超时
     */
    _pollAiReply() {
      if (this._aiPollTimer) clearInterval(this._aiPollTimer)
      const POLL_INTERVAL = 1500
      const TIMEOUT = 30000
      let elapsed = 0
      this._aiPollTimer = setInterval(async () => {
        elapsed += POLL_INTERVAL
        const lastSeq = this.messages.length ? this.messages[this.messages.length - 1].seq : 0
        try {
          const res = await API.trainingMessageList({ session_id: this.sessionId, last_seq: lastSeq })
          const newOnes = res.data || []
          const customerMsgs = newOnes.filter(m => Number(m.role) === 1)
          if (customerMsgs.length > 0) {
            customerMsgs.forEach(m => this.messages.push(m))
            this.aiReplying = false
            clearInterval(this._aiPollTimer)
            this._aiPollTimer = null
            this.$nextTick(() => this.scrollToBottom())
            return
          }
          if (elapsed >= TIMEOUT) {
            this.aiReplying = false
            clearInterval(this._aiPollTimer)
            this._aiPollTimer = null
            this.$message.warning('AI 客户回复超时，请重新发送或检查网络')
          }
        } catch (e) {/* 拦截器已处理 */}
      }, POLL_INTERVAL)
    },

    async onEnd() {
      if (this.ending) return
      // AI 评分服务要求消息 >= 2 条(至少 1 轮完整对话:销售发言 + 客户回应),前端先拦,避免直接报"评分异常"
      const seatCount = this.messages.filter(m => Number(m.role) === 2).length
      const customerCount = this.messages.filter(m => Number(m.role) === 1).length
      if (seatCount < 1 || customerCount < 1) {
        this.$message.warning('请至少完成一轮完整对话(销售发言 + AI 客户回应)后再结束')
        return
      }
      this.ending = true
      try {
        await API.trainingEndSession({ session_id: this.sessionId })
        const sid = this.sessionId
        this.view = 'list'
        this.$router.push({ path: '/training/result', query: { session_id: sid, from: 'challenge' } })
      } finally {
        this.ending = false
      }
    },

    scrollToBottom() {
      const el = this.$refs.msgList
      if (el) el.scrollTop = el.scrollHeight
    },

  }
}
</script>

<style lang="scss" scoped>
.training-challenge-page { padding: 16px 20px 24px; }

.header-filters {
  display: flex;
  align-items: center;
  gap: 10px;
}
.search-input { width: 220px; }
.filter-select { width: 140px; }

.scenario-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 16px;
}
.scenario-card {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: 18px 18px 16px;
  display: flex;
  flex-direction: column;
  box-shadow: 0 1px 6px rgba(0,0,0,0.03);
  transition: all 0.2s;
  &:hover { border-color: #c7d2fe; box-shadow: 0 6px 16px rgba(99,102,241,0.08); transform: translateY(-1px); }
  &__head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 8px;
    margin-bottom: 8px;
  }
  .scenario-name {
    font-weight: 700;
    font-size: 15px;
    color: #111827;
    flex: 1;
    min-width: 0;
    line-height: 1.4;
    overflow: hidden;
    text-overflow: ellipsis;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    word-break: break-all;
  }
  .difficulty-tag { flex-shrink: 0; }
}
.scenario-desc {
  font-size: 13px;
  color: #4b5563;
  line-height: 1.6;
  margin-bottom: 10px;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
.scenario-persona {
  font-size: 12px;
  color: #6b7280;
  line-height: 1.6;
  margin-bottom: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  .persona-label { color: #9ca3af; }
}
.scenario-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: auto;
  margin-bottom: 14px;
}
.ds-chip {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  font-size: 12px;
  border-radius: 4px;
  line-height: 1.6;
  &--required { background: #fef3c7; color: #b45309; }
  &--optional { background: #f3f4f6; color: #6b7280; }
  &--practice { background: #f3f4f6; color: #4b5563; }
  &--score { background: #dcfce7; color: #15803d; font-weight: 500; }
  &--score-empty { background: #f3f4f6; color: #9ca3af; }
}
.ds-gradient-btn {
  width: 100%;
  height: 38px;
  border: 0;
  border-radius: 8px;
  background: linear-gradient(135deg, #6366f1, #9333ea);
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.2s;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  &:hover:not(:disabled) { opacity: 0.92; }
  &:disabled { cursor: not-allowed; opacity: 0.7; }
}
.empty-state {
  padding: 80px 0;
  text-align: center;
  color: #9ca3af;
  .empty-icon { font-size: 40px; margin-bottom: 12px; }
  .empty-title { font-size: 16px; font-weight: 600; color: #374151; margin-bottom: 6px; }
  .empty-desc { font-size: 13px; }
}
.muted { color: #9ca3af; }
.ml-6 { margin-left: 6px; }

// session
.session-page {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 88px);
  background: #f8f9fc;
  overflow: hidden;
}
.session-topbar {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  padding: 12px 20px;
  background: transparent;
}
.session-back {
  font-size: 14px;
  color: #6366f1;
  cursor: pointer;
  user-select: none;
  &:hover { color: #4f46e5; }
}
.session-title-pill {
  justify-self: center;
  padding: 6px 18px;
  background: #f5f3ff;
  border: 1px solid #e0e7ff;
  border-radius: 999px;
  color: #4f46e5;
  font-size: 14px;
  font-weight: 600;
}
.session-end-btn {
  justify-self: end;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 16px;
  background: #fff;
  border: 1px solid #fca5a5;
  border-radius: 8px;
  color: #dc2626;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  &:hover:not(:disabled) { background: #fef2f2; border-color: #f87171; }
  &:disabled { cursor: not-allowed; opacity: 0.6; }
}

.scene-banner {
  margin: 0 20px 12px;
  padding: 14px 18px;
  border-radius: 10px;
  background: #faf5ff;
  border: 1px solid #ede9fe;
  font-size: 13px;
  color: #7c3aed;
  .banner-tags { display: flex; gap: 6px; margin-bottom: 10px; }
  .banner-row { display: flex; line-height: 1.7; }
  .banner-label { color: #7c3aed; font-weight: 600; flex-shrink: 0; }
  .banner-text { color: #7c3aed; }
}
.scene-tag {
  display: inline-block;
  padding: 2px 10px;
  font-size: 12px;
  border-radius: 4px;
  font-weight: 500;
  &--diff-1 { background: #dbeafe; color: #2563eb; }
  &--diff-2 { background: #e0f2fe; color: #0891b2; }
  &--diff-3 { background: #ffedd5; color: #ea580c; }
  &--diff-4 { background: #fee2e2; color: #dc2626; }
  &--required { background: #ede9fe; color: #7c3aed; }
}

.chat-shell {
  flex: 1;
  min-height: 0;
  margin: 0 20px 16px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.msg-list {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
  .msg-empty {
    height: 100%;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    color: #9ca3af;
    padding-bottom: 60px;
    &__icon {
      width: 60px;
      height: 60px;
      border-radius: 50%;
      background: #fff;
      display: grid;
      place-items: center;
      margin-bottom: 14px;
      box-shadow: 0 1px 4px rgba(0,0,0,0.04);
      i { font-size: 28px; color: #c7d2fe; }
    }
    &__title { font-size: 14px; color: #6b7280; margin-bottom: 4px; }
    &__desc { font-size: 13px; color: #9ca3af; }
  }
  .msg-row {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    margin-bottom: 14px;
    &.role-seat { justify-content: flex-end; .msg-bubble { background: linear-gradient(135deg, #6366f1, #9333ea); color: #fff; box-shadow: 0 1px 4px rgba(99,102,241,0.18); } }
    &.role-customer { justify-content: flex-start; .msg-bubble { background: #f3f4f6; color: #111827; } }
  }
  .msg-avatar {
    width: 32px;
    height: 32px;
    border-radius: 50%;
    background: #e5e7eb;
    color: #6b7280;
    display: grid;
    place-items: center;
    font-size: 12px;
    font-weight: 600;
    flex-shrink: 0;
  }
  .msg-bubble {
    max-width: 70%;
    padding: 10px 14px;
    border-radius: 10px;
    line-height: 1.6;
    font-size: 14px;
    white-space: pre-wrap;
    word-break: break-word;
  }
}
.composer {
  padding: 12px 16px 16px;
  border-top: 1px solid #f3f4f6;
  display: flex;
  align-items: flex-end;
  gap: 10px;
}
.composer-input-wrap {
  flex: 1;
  background: #fff;
  border: 1px solid #c4b5fd;
  border-radius: 10px;
  transition: border-color 0.2s, box-shadow 0.2s;
  &:focus-within { border-color: #6366f1; box-shadow: 0 0 0 3px rgba(99,102,241,0.12); }
}
.composer-input {
  width: 100%;
  resize: none;
  border: 0;
  background: transparent;
  padding: 12px 14px;
  font-size: 14px;
  line-height: 1.6;
  outline: none;
  color: #111827;
}
.composer-actions {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 8px;
}
.composer-btn {
  min-width: 72px;
  height: 36px;
  border: 0;
  border-radius: 18px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  transition: all 0.2s;
  i { font-size: 16px; }
  &:disabled { cursor: not-allowed; opacity: 0.5; }
  &--mic {
    background: #f3f4f6;
    color: #6b7280;
    &:hover:not(:disabled) { background: #ede9fe; color: #6366f1; }
  }
  &--send {
    background: linear-gradient(135deg, #6366f1, #9333ea);
    color: #fff;
    &:hover:not(:disabled) { opacity: 0.92; }
  }
  &--record {
    background: #fee2e2;
    color: #dc2626;
    animation: pulse 1.2s infinite;
  }
}
.composer-btn-text {
  font-size: 13px;
  font-weight: 600;
}
.msg-bubble--typing {
  display: inline-flex !important;
  align-items: center;
  gap: 4px;
  min-width: 50px;
  padding: 12px 14px !important;
}
.typing-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #9ca3af;
  animation: typingBounce 1.2s infinite ease-in-out;
}
.typing-dot:nth-child(2) { animation-delay: 0.15s; }
.typing-dot:nth-child(3) { animation-delay: 0.30s; }
@keyframes typingBounce {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.5; }
  30% { transform: translateY(-4px); opacity: 1; }
}

@keyframes pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(220, 38, 38, 0.5); }
  50% { box-shadow: 0 0 0 8px rgba(220, 38, 38, 0); }
}
</style>
