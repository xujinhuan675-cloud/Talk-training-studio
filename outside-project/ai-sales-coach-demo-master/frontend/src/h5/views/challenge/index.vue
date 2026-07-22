<template>
  <div class="h5-challenge">
    <!-- ===== 场景列表 ===== -->
    <template v-if="view === 'list'">
      <van-nav-bar title="闯关陪练" fixed safe-area-inset-top />
      <div class="nav-spacer" />

      <div class="filter-bar">
        <div class="mini-search">
          <van-icon name="search" class="mini-search__icon" />
          <input
            v-model="filter.keyword"
            class="mini-search__input"
            placeholder="搜索场景"
            @keyup.enter="loadList"
          >
          <button v-if="filter.keyword" class="mini-search__btn" @click="loadList">搜索</button>
        </div>
        <button :class="['dd-token', filter.difficulty ? 'active' : '']" @click="diffSheetVisible = true">
          <span>{{ difficultyTokenLabel }}</span>
          <van-icon name="arrow-down" size="10" />
        </button>
        <button :class="['dd-token', filter.is_required !== '' ? 'active' : '']" @click="typeSheetVisible = true">
          <span>{{ typeTokenLabel }}</span>
          <van-icon name="arrow-down" size="10" />
        </button>
      </div>

      <van-pull-refresh v-model="refreshing" @refresh="onRefresh">
        <van-empty v-if="!loading && scenarios.length === 0" description="暂无可练习场景" />
        <div v-else class="scenario-list">
          <div v-for="sc in scenarios" :key="sc.id" class="scenario-card">
            <div class="card-head">
              <div class="card-title">{{ sc.name }}</div>
              <span :class="['tag', `tag-diff-${sc.difficulty}`]">{{ difficultyLabel(sc.difficulty) }}</span>
            </div>
            <div v-if="sc.scene_desc" class="card-desc">{{ sc.scene_desc }}</div>
            <div class="card-persona"><span class="persona-label">客户画像:</span>{{ sc.persona || '-' }}</div>
            <div class="card-chips">
              <span :class="['chip-mini', Number(sc.is_required) === 1 ? 'chip-required' : 'chip-optional']">
                {{ Number(sc.is_required) === 1 ? '必练' : '非必练' }}
              </span>
              <template v-if="Number(sc.my_practice_count) > 0">
                <span class="chip-mini chip-practice">已练 {{ sc.my_practice_count }} 次</span>
                <span v-if="sc.my_latest_score !== null && sc.my_latest_score !== undefined" class="chip-mini chip-score">最近 {{ sc.my_latest_score }}</span>
                <span v-else class="chip-mini chip-empty">暂无分数</span>
              </template>
              <template v-else>
                <span class="chip-mini chip-empty">未练习</span>
              </template>
            </div>
            <button class="h5-gradient-btn" :disabled="startingId === sc.id" @click="onStart(sc)">
              <van-loading v-if="startingId === sc.id" color="#fff" size="16" />
              <span v-else>开始练习</span>
            </button>
          </div>
        </div>
      </van-pull-refresh>

      <!-- 难度 sheet -->
      <van-popup v-model="diffSheetVisible" position="bottom" round>
        <div class="sheet">
          <div class="sheet__title">选择难度</div>
          <div class="sheet-row" :class="{ active: !filter.difficulty }" @click="setDifficulty('')">全部难度</div>
          <div v-for="d in difficulties" :key="d.v" class="sheet-row" :class="{ active: filter.difficulty === d.v }" @click="setDifficulty(d.v)">{{ d.label }}</div>
        </div>
      </van-popup>

      <!-- 类型 sheet -->
      <van-popup v-model="typeSheetVisible" position="bottom" round>
        <div class="sheet">
          <div class="sheet__title">选择类型</div>
          <div class="sheet-row" :class="{ active: filter.is_required === '' }" @click="setRequired('')">全部类型</div>
          <div class="sheet-row" :class="{ active: filter.is_required === 1 }" @click="setRequired(1)">必练</div>
          <div class="sheet-row" :class="{ active: filter.is_required === 0 }" @click="setRequired(0)">非必练</div>
        </div>
      </van-popup>
    </template>

    <!-- ===== 对话视图(独立一屏 fixed,顶栏/底部固定) ===== -->
    <div v-if="view === 'session'" class="session-mode">
      <div class="session-topbar">
        <van-icon name="arrow-left" class="back-btn" @click="onBack" />
        <div class="title-pill" @click="showFullTitle">{{ activeScenario.name }}</div>
        <button class="end-btn" :disabled="ending" @click="onEnd">
          <van-loading v-if="ending" color="#DC2626" size="14" />
          <span v-else>结束</span>
        </button>
      </div>

      <div class="scene-banner" @click="showFullTitle">
        <span class="tag tag-diff-banner">{{ difficultyLabel(activeScenario.difficulty) }}</span>
        <span v-if="Number(activeScenario.is_required) === 1" class="tag tag-required-banner">必练</span>
        <span class="persona-text">👤 {{ activeScenario.persona || '-' }}</span>
        <van-icon name="arrow" class="banner-arrow" />
      </div>

      <message-list :messages="messages" :ai-replying="aiReplying" class="session-msglist" />

      <div v-if="!hasOpening && messages.length === 0" class="opening-tip">
        请主动向客户开场,开启本次练习
      </div>

      <div class="composer">
        <button
          :class="['composer-mic', (recording || recognizing) ? 'active' : '', !speechSupported ? 'unsupported' : '']"
          :disabled="recognizing"
          @touchstart.prevent="onMicStart"
          @touchend.prevent="onMicEnd"
          @mousedown.prevent="onMicStart"
          @mouseup.prevent="onMicEnd"
        >
          <svg v-if="!recording" class="mic-svg" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
            <path d="M12 15a3 3 0 0 0 3-3V6a3 3 0 1 0-6 0v6a3 3 0 0 0 3 3z" />
            <path d="M19 12a1 1 0 1 0-2 0 5 5 0 0 1-10 0 1 1 0 1 0-2 0 7 7 0 0 0 6 6.92V21H8a1 1 0 1 0 0 2h8a1 1 0 1 0 0-2h-3v-2.08A7 7 0 0 0 19 12z" />
          </svg>
          <svg v-else class="mic-svg recording" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
            <rect x="6" y="6" width="12" height="12" rx="2" />
          </svg>
        </button>
        <div class="composer-input-wrap">
          <textarea
            ref="textarea"
            v-model="composerText"
            class="composer-input"
            placeholder="输入消息或按住麦克风说话"
            rows="1"
            :disabled="sending"
            @input="autoResize"
            @compositionstart="composing = true"
            @compositionend="composing = false"
          />
        </div>
        <button class="composer-send" :disabled="sending || !composerText.trim()" @click="sendText">
          <van-loading v-if="sending" color="#fff" size="14" />
          <span v-else>发送</span>
        </button>
      </div>
    </div>
  </div>
</template>

<script>
import API from '@/api'
import MessageList from '../../components/MessageList.vue'
import voiceInput from '../../mixins/voiceInput'

const DIFFICULTY_LABELS = { 1: '简单', 2: '中等', 3: '困难', 4: '专家' }

export default {
  name: 'H5Challenge',
  components: { MessageList },
  mixins: [voiceInput],
  inject: { setTabVisible: { default: () => () => {} } },
  data() {
    return {
      view: 'list',
      loading: false,
      refreshing: false,
      filter: { keyword: '', difficulty: '', is_required: '' },
      scenarios: [],
      startingId: null,
      diffSheetVisible: false,
      typeSheetVisible: false,
      difficulties: [
        { v: 1, label: '简单' },
        { v: 2, label: '中等' },
        { v: 3, label: '困难' },
        { v: 4, label: '专家' }
      ],

      activeScenario: {},
      sessionId: null,
      hasOpening: false,
      messages: [],
      composerText: '',
      composing: false,
      sending: false,
      ending: false,
      aiReplying: false,
      _aiPollTimer: null
    }
  },
  computed: {
    difficultyTokenLabel() {
      const d = this.difficulties.find(x => x.v === this.filter.difficulty)
      return d ? d.label : '全部难度'
    },
    typeTokenLabel() {
      if (this.filter.is_required === 1) return '必练'
      if (this.filter.is_required === 0) return '非必练'
      return '全部类型'
    }
  },
  async created() {
    await this.handleRouteEntry()
  },
  async activated() {
    await this.handleRouteEntry()
    // 从其它 Tab 切回时,根据当前视图恢复 TabBar 状态
    this.setTabVisible(this.view !== 'session')
  },
  deactivated() {
    // 切走时还原 TabBar(避免别的 Tab 残留隐藏状态)
    this.setTabVisible(true)
  },
  beforeDestroy() {
    this.setTabVisible(true)
    if (this._aiPollTimer) {
      clearInterval(this._aiPollTimer)
      this._aiPollTimer = null
    }
  },
  watch: {
    view(v) {
      this.setTabVisible(v !== 'session')
    },
    // composerText 被外部赋值时(语音识别回填、清空)也要触发 resize
    composerText() { this.autoResize() },
    // 搜索关键词:从有值删空(搜索按钮已消失)时自动重新加载,避免列表停留在过滤态
    'filter.keyword'(val, old) {
      if (!val && old) this.loadList()
    }
  },
  methods: {
    difficultyLabel(d) { return DIFFICULTY_LABELS[d] || '-' },

    async handleRouteEntry() {
      const sessionIdQuery = String(this.$route.query.session_id || '').trim()
      const scenarioIdQuery = Number(this.$route.query.scenario_id || 0)
      const isRestart = this.$route.query.action === 'restart'

      // 1. 已有 session_id → 进入已有会话(场景:刷新页面)
      if (sessionIdQuery && (!this.sessionId || this.sessionId !== sessionIdQuery)) {
        await this.enterExistingSession(sessionIdQuery)
        return
      }
      // 2. 带 scenario_id 且 action=restart → 从 detail 的"再练一次"跳过来,直接发起新会话
      if (scenarioIdQuery && isRestart) {
        // 清掉 query,避免后续刷新重复触发
        this.$router.replace({ path: this.$route.path }).catch(() => {})
        // 复用 onStart 流程(和点击列表"开始练习"完全一致)
        await this.onStart({ id: scenarioIdQuery })
        return
      }
      // 3. 默认场景列表
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
        this.$router.replace({ path: this.$route.path }).catch(() => {})
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

    async onRefresh() {
      await this.loadList()
      this.refreshing = false
    },

    setDifficulty(v) {
      this.filter.difficulty = v
      this.diffSheetVisible = false
      this.loadList()
    },
    setRequired(v) {
      this.filter.is_required = v
      this.typeSheetVisible = false
      this.loadList()
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
      } finally {
        this.startingId = null
      }
    },

    onBack() {
      this.$dialog.confirm({
        title: '离开演练',
        message: '演练尚未结束,确定要离开吗?返回后本次练习不会被保存。',
        confirmButtonColor: '#6366F1'
      }).then(() => {
        this.view = 'list'
        this.messages = []
        this.sessionId = null
        this.loadList()
      }).catch(() => {})
    },

    async sendText() {
      const text = (this.composerText || '').trim()
      if (!text || this.sending) return
      if (!this.sessionId) {
        this.$toast({ message: '会话尚未创建，请重新选择场景开始练习', duration: 2500 })
        return
      }
      // 500ms 防抖:防止移动端 ghost click / 双触触发两次发送
      const now = Date.now()
      if (now - (this._lastSendAt || 0) < 500) return
      this._lastSendAt = now
      this.sending = true
      const tempSeq = (this.messages.length ? this.messages[this.messages.length - 1].seq + 1 : 1)
      this.messages.push({ seq: tempSeq, role: 2, content: text })
      this.composerText = ''
      try {
        const res = await API.trainingSendMessage({ session_id: this.sessionId, content: text })
        const data = res.data || {}
        if (data.seat_message) {
          this.messages.splice(this.messages.length - 1, 1, data.seat_message)
        }
        if (data.pending_customer_reply) {
          this.aiReplying = true
          this._pollAiReply()
        }
      } catch (e) {
        this.messages.pop()
      } finally {
        this.sending = false
      }
    },

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
            return
          }
          if (elapsed >= TIMEOUT) {
            this.aiReplying = false
            clearInterval(this._aiPollTimer)
            this._aiPollTimer = null
            this.$toast('AI 客户回复超时,请重新发送或检查网络')
          }
        } catch (e) { /* 拦截器处理 */ }
      }, POLL_INTERVAL)
    },

    async onEnd() {
      if (this.ending) return
      const seatCount = this.messages.filter(m => Number(m.role) === 2).length
      const customerCount = this.messages.filter(m => Number(m.role) === 1).length
      // AI 评分服务要求消息 >= 2 条(至少 1 轮完整对话),前端先拦,避免直接报"评分异常"
      if (seatCount < 1 || customerCount < 1) {
        this.$toast('请至少完成一轮完整对话(销售发言 + AI 客户回应)后再结束')
        return
      }
      this.ending = true
      try {
        await API.trainingEndSession({ session_id: this.sessionId })
        const sid = this.sessionId
        this.view = 'list'
        this.messages = []
        this.sessionId = null
        this.$router.push({ path: '/m/history/detail', query: { session_id: sid, from: 'challenge' } })
      } finally {
        this.ending = false
      }
    },

    showFullTitle() {
      if (!this.activeScenario || !this.activeScenario.name) return
      const sc = this.activeScenario
      const lines = []
      lines.push(sc.name)
      if (sc.scene_desc) lines.push('\n场景描述\n' + sc.scene_desc)
      if (sc.persona) lines.push('\n客户画像\n' + sc.persona)
      this.$dialog.alert({
        title: '场景信息',
        message: lines.join('\n'),
        messageAlign: 'left',
        confirmButtonColor: '#6366F1'
      })
    },
    onMicStart() {
      if (this.sending || this.recognizing) return
      this.startRecord()
    },
    onMicEnd() {
      if (this.recording) this.stopRecord()
    },
    autoResize() {
      this.$nextTick(() => {
        const el = this.$refs.textarea
        if (!el) return
        el.style.height = 'auto'
        // scrollHeight 是内容自然高度,封顶 84px(约 3-4 行)后内部可滚
        const next = Math.min(el.scrollHeight, 84)
        el.style.height = next + 'px'
      })
    }
  }
}
</script>

<style lang="scss" scoped>
.h5-challenge {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--h5-bg);
}
.nav-spacer { height: 46px; }

::v-deep .van-nav-bar {
  background: #fff;
  .van-nav-bar__title { font-weight: 600; }
}

/* 顶部筛选条:搜索 + 难度 dropdown + 类型 dropdown 同一行 */
.filter-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  background: var(--h5-bg);
}
.mini-search {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 4px;
  background: #fff;
  border-radius: 18px;
  padding: 0 4px 0 12px;
  height: 32px;
  border: 1px solid var(--h5-border);
  &__icon { color: var(--h5-text-3); font-size: 14px; flex-shrink: 0; }
  &__input {
    flex: 1;
    min-width: 0;
    height: 100%;
    border: 0;
    outline: 0;
    background: transparent;
    font-size: 13px;
    color: var(--h5-text-1);
    &::placeholder { color: var(--h5-text-3); }
  }
  &__btn {
    flex-shrink: 0;
    height: 24px;
    padding: 0 10px;
    background: var(--h5-primary);
    color: #fff;
    border: 0;
    border-radius: 12px;
    font-size: 12px;
    font-weight: 500;
    &:active { opacity: .85; }
  }
}
.dd-token {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  gap: 3px;
  height: 32px;
  padding: 0 10px;
  background: #fff;
  color: var(--h5-text-1);
  border: 1px solid var(--h5-border);
  border-radius: 16px;
  font-size: 13px;
  font-weight: 500;
  max-width: 88px;
  > span {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  &.active {
    color: var(--h5-primary);
    border-color: var(--h5-primary);
    background: var(--h5-primary-soft);
  }
  &:active { opacity: .85; }
}

/* 难度/类型 sheet 行 */
.sheet {
  padding: 16px 0 calc(8px + env(safe-area-inset-bottom));
  &__title {
    text-align: center;
    font-size: 15px;
    font-weight: 600;
    color: var(--h5-text-1);
    padding-bottom: 12px;
    border-bottom: 1px solid var(--h5-border);
    margin: 0 16px 4px;
  }
}
.sheet-row {
  padding: 14px 16px;
  text-align: center;
  font-size: 15px;
  color: var(--h5-text-1);
  border-bottom: 1px solid #F3F4F6;
  &:last-child { border-bottom: 0; }
  &.active { color: var(--h5-primary); font-weight: 600; }
  &:active { background: #FAFAFB; }
}

.scenario-list { padding: 0 12px 16px; }
.scenario-card {
  background: #fff;
  border-radius: var(--h5-radius);
  padding: 14px;
  margin-bottom: 12px;
  box-shadow: var(--h5-shadow);
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}
.card-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--h5-text-1);
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-right: 8px;
}
.tag {
  flex-shrink: 0;
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
  &.tag-diff-1 { background: #DCFCE7; color: #15803D; }
  &.tag-diff-2 { background: #DBEAFE; color: #1D4ED8; }
  &.tag-diff-3 { background: #FEF3C7; color: #B45309; }
  &.tag-diff-4 { background: #FEE2E2; color: #B91C1C; }
}
.card-desc {
  color: var(--h5-text-2);
  font-size: 13px;
  line-height: 1.55;
  margin-bottom: 8px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.card-persona {
  font-size: 12px;
  color: var(--h5-text-3);
  margin-bottom: 10px;
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
  .persona-label { color: var(--h5-text-2); }
}
.card-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 12px;
}
.chip-mini {
  font-size: 11px;
  padding: 3px 8px;
  border-radius: 4px;
  background: #F3F4F6;
  color: var(--h5-text-2);
  &.chip-required { background: #FEF3C7; color: #B45309; font-weight: 500; }
  &.chip-optional { background: #F3F4F6; color: #6B7280; }
  &.chip-practice { background: #E0E7FF; color: #4338CA; }
  &.chip-score { background: var(--h5-primary-soft); color: var(--h5-primary); font-weight: 600; }
  &.chip-empty { color: #9CA3AF; }
}

/* ============ 对话视图(独立全屏 fixed 容器) ============ */
.session-mode {
  position: fixed;
  inset: 0;
  z-index: 100;
  display: flex;
  flex-direction: column;
  background: var(--h5-bg);
  overflow: hidden;
}
.session-msglist {
  flex: 1;
  min-height: 0;
}
.session-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: #fff;
  border-bottom: 1px solid var(--h5-border);
  flex-shrink: 0;
  padding-top: calc(8px + env(safe-area-inset-top));
  box-sizing: border-box;
  min-height: calc(50px + env(safe-area-inset-top));
}
.back-btn {
  font-size: 24px;
  color: var(--h5-text-2);
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.title-pill {
  flex: 1;
  text-align: center;
  margin: 0 8px;
  font-size: 14px;
  font-weight: 600;
  color: var(--h5-primary);
  background: var(--h5-primary-soft);
  border-radius: 14px;
  padding: 5px 12px;
  max-width: 65%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  align-self: center;
  cursor: pointer;
  &:active { opacity: .75; }
}
.end-btn {
  flex-shrink: 0;
  height: 28px;
  padding: 0 12px;
  border-radius: 14px;
  background: #fff;
  color: #DC2626;
  border: 1px solid #FECACA;
  font-size: 12px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 4px;
  &:disabled { opacity: .6; }
}

.scene-banner {
  background: linear-gradient(135deg, #F5F3FF 0%, #EDE9FE 100%);
  padding: 10px 14px;
  display: flex;
  gap: 6px;
  align-items: center;
  font-size: 12px;
  color: var(--h5-text-2);
  border-bottom: 1px solid #E0DAFB;
  flex-shrink: 0;
  cursor: pointer;
  &:active { background: linear-gradient(135deg, #EDE9FE 0%, #DDD6FE 100%); }
  .banner-arrow {
    color: var(--h5-primary);
    flex-shrink: 0;
    font-size: 14px;
    margin-left: 2px;
  }
  .tag-diff-banner {
    background: rgba(124,58,237,.15);
    color: #6B21A8;
    padding: 2px 8px;
    border-radius: 4px;
    font-weight: 500;
  }
  .tag-required-banner {
    background: #FEF3C7;
    color: #B45309;
    padding: 2px 8px;
    border-radius: 4px;
    font-weight: 500;
  }
  .persona-text {
    margin-left: auto;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    flex: 1;
    min-width: 0;
    text-align: right;
  }
}

.opening-tip {
  text-align: center;
  padding: 8px;
  font-size: 12px;
  color: var(--h5-text-3);
  background: #fff;
}

.composer {
  background: #fff;
  padding: 10px 12px calc(10px + env(safe-area-inset-bottom));
  border-top: 1px solid var(--h5-border);
  display: flex;
  gap: 8px;
  align-items: flex-end;
  flex-shrink: 0;
}
.composer-mic {
  width: 38px;
  height: 38px;
  border-radius: 50%;
  background: var(--h5-bg);
  color: var(--h5-text-2);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  border: 0;
  padding: 0;
  &.active {
    background: var(--h5-primary);
    color: #fff;
    box-shadow: 0 0 0 6px rgba(99,102,241,.18);
  }
  &.unsupported {
    color: var(--h5-text-3);
    opacity: 0.7;
  }
  .mic-svg {
    width: 20px;
    height: 20px;
    &.recording {
      animation: micPulse 1.1s ease-in-out infinite;
    }
  }
}
@keyframes micPulse {
  0%, 100% { transform: scale(1); opacity: 1; }
  50% { transform: scale(0.78); opacity: 0.7; }
}
.composer-input-wrap {
  flex: 1;
  min-width: 0;
  background: var(--h5-bg);
  border-radius: 19px;
  padding: 8px 14px;     /* 上下 8px,加上 textarea 22px = 38px,与按钮等高 */
  display: flex;
  align-items: flex-start;
}
.composer-input {
  flex: 1;
  width: 100%;
  border: 0;
  outline: 0;
  background: transparent;
  font-size: 14px;
  line-height: 22px;     /* 固定行高,单行精确等高按钮 */
  height: 22px;          /* 初始单行,JS 在 input 时按 scrollHeight 撑开 */
  max-height: 88px;      /* 约 4 行,超出滚动 */
  color: var(--h5-text-1);
  resize: none;
  overflow-y: auto;
  padding: 0;
  margin: 0;
  font-family: inherit;
  display: block;        /* 去掉 inline 残留行距 */
  vertical-align: top;
  &::placeholder { color: var(--h5-text-3); }
}
.composer-send {
  flex-shrink: 0;
  height: 38px;
  padding: 0 16px;
  background: var(--h5-gradient);
  color: #fff;
  border-radius: 19px;
  border: 0;
  font-size: 14px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4px 10px rgba(99,102,241,.22);
  &:disabled {
    opacity: .55;
    background: var(--h5-text-3);
    box-shadow: none;
  }
}

</style>
