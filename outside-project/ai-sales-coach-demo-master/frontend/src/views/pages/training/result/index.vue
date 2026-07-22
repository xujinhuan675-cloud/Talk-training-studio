<template>
  <div class="training-result-page" v-loading="loading">
    <!-- 顶部 -->
    <div class="topbar">
      <div class="topbar-left">
        <h2 class="page-title">评分结果</h2>
        <div class="page-desc">本次闯关陪练已完成，以下为 AI 评分和改进建议。</div>
      </div>
      <div class="topbar-actions">
        <button v-if="canTrainAgain" class="ds-btn ds-btn--primary" @click="onTrainAgain">再练一次</button>
        <button class="ds-btn ds-btn--default" @click="onBack">返回列表</button>
      </div>
    </div>

    <template v-if="session.id">
      <!-- 主区双卡 -->
      <div class="main-row">
        <!-- 左：综合评分 -->
        <div class="card score-card">
          <template v-if="status === 2 && score">
            <div class="score-value">{{ score.total_score }}</div>
            <div class="score-grade">{{ gradeLabel(score.total_score) }}</div>
          </template>
          <template v-else-if="status === 1">
            <div class="score-card__title">综合评分</div>
            <div class="status-pending">AI 正在评分中…</div>
            <el-progress :percentage="pendingProgress" :show-text="false" class="pending-progress" />
            <div class="score-tip score-tip--pending">评分通常在 30 秒内完成</div>
          </template>
          <template v-else-if="status === 3">
            <div class="score-card__title">综合评分</div>
            <div class="status-failed">评分异常</div>
            <div class="score-tip">已自动重试多次仍失败，请联系管理员排查</div>
          </template>

          <div class="score-meta">
            <div class="score-meta__row" :title="session.scenario_name">
              <span class="score-meta__label">场景：</span>
              <span class="score-meta__value">{{ session.scenario_name }}</span>
            </div>
            <div class="score-meta__row"><span class="score-meta__label">难度：</span><span>{{ difficultyLabel(session.difficulty) }}</span></div>
            <div class="score-meta__row"><span class="score-meta__label">用时：</span><span>{{ formatDuration(session.duration_sec) }}</span></div>
            <div class="score-meta__row"><span class="score-meta__label">对话：</span><span>{{ Math.ceil((session.message_count || 0) / 2) }} 轮</span></div>
          </div>
        </div>

        <!-- 右：维度得分 -->
        <div class="card dim-card">
          <div class="card__title">维度得分</div>
          <template v-if="status === 2 && score && score.dimension_scores.length">
            <div v-for="d in score.dimension_scores" :key="d.dimension_id" class="dim-row">
              <span class="dim-row__name">{{ d.dimension_name }}</span>
              <div class="dim-row__bar">
                <div class="dim-row__bar-fill" :style="{ width: Math.min(100, d.score) + '%' }" />
              </div>
              <span class="dim-row__score">{{ d.score }}</span>
            </div>
          </template>
          <div v-else-if="status === 1" class="skeleton">评分中…</div>
          <div v-else-if="status === 3" class="skeleton danger">评分异常</div>
        </div>
      </div>

      <!-- 平均分提示文字 -->
      <div v-if="status === 2 && score" class="impact-tip">
        本次得分已作为「{{ session.scenario_name }}」场景的当前能力记录，将影响您在排行榜的平均分（每场景取最新一次评分）。
      </div>

      <!-- AI 总评 + 改进建议 -->
      <div class="dual-row">
        <div class="card">
          <div class="card__title">AI 总评</div>
          <template v-if="status === 2 && score">
            <p class="ai-summary">{{ score.summary || '-' }}</p>
          </template>
          <div v-else-if="status === 1" class="skeleton">评分中…</div>
          <div v-else-if="status === 3" class="skeleton danger">评分异常，请联系管理员</div>
        </div>
        <div class="card">
          <div class="card__title">改进建议</div>
          <ol v-if="status === 2 && score && score.suggestions.length" class="ordered">
            <li v-for="(s, i) in score.suggestions" :key="i">{{ s }}</li>
          </ol>
          <div v-else-if="status === 1" class="skeleton">评分中…</div>
          <div v-else-if="status === 3" class="skeleton danger">评分异常</div>
        </div>
      </div>

      <!-- 对话回放 -->
      <div class="card replay-card">
        <div class="replay-card__head">
          <div class="card__title" style="margin: 0">对话回放</div>
          <div class="replay-badges">
            <span class="badge">{{ Math.ceil(messages.length / 2) }} 轮对话</span>
            <span class="badge">用时 {{ formatDuration(session.duration_sec) }}</span>
          </div>
        </div>
        <div class="replay-list">
          <div v-if="messages.length === 0" class="empty">暂无对话</div>
          <div v-for="m in messages" :key="m.id || m.seq" :class="['msg-row', Number(m.role) === 2 ? 'role-seat' : 'role-customer']">
            <div v-if="Number(m.role) !== 2" class="msg-avatar msg-avatar--customer">客</div>
            <div class="msg-bubble">{{ m.content }}</div>
            <div v-if="Number(m.role) === 2" class="msg-avatar msg-avatar--seat">销</div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script>
import API from '@/api'

const DIFFICULTY_LABELS = { 1: '简单', 2: '中等', 3: '困难', 4: '专家' }
const DIFFICULTY_TAGS = { 1: 'success', 2: 'info', 3: 'warning', 4: 'danger' }

export default {
  name: 'TrainingResult',
  data() {
    return {
      loading: false,
      pollTimer: null,
      pendingProgress: 0,
      status: 0,
      session: {},
      score: null,
      messages: []
    }
  },
  computed: {
    sessionId() { return String(this.$route.query.session_id || '').trim() },
    from() { return this.$route.query.from || 'history' },
    canTrainAgain() { return this.status === 2 && !!this.session.scenario_id }
  },
  created() {
    if (!this.sessionId) {
      this.$message.warning('缺少 session_id')
      return
    }
    this.fetchDetail()
  },
  beforeDestroy() {
    this.stopPoll()
  },
  methods: {
    difficultyLabel(d) { return DIFFICULTY_LABELS[d] || '-' },
    difficultyTag(d) { return DIFFICULTY_TAGS[d] || '' },
    gradeLabel(score) {
      if (score >= 90) return '优秀'
      if (score >= 80) return '良好'
      if (score >= 70) return '合格'
      return '需加强'
    },
    scoreColor(score) {
      if (score >= 80) return '#16a34a'
      if (score >= 60) return '#f59e0b'
      return '#dc2626'
    },
    formatDuration(sec) {
      sec = Number(sec) || 0
      if (sec < 60) return `${sec} 秒`
      const m = Math.floor(sec / 60)
      const s = sec % 60
      return `${m} 分 ${s} 秒`
    },
    async fetchDetail() {
      this.loading = true
      try {
        const res = await API.trainingSessionDetail({ session_id: this.sessionId })
        const data = res.data || {}
        this.session = data.session || {}
        this.score = data.score || null
        this.messages = data.messages || []
        this.status = Number(this.session.status || 0)
        if (this.status === 1) this.startPoll()
      } finally {
        this.loading = false
      }
    },
    startPoll() {
      this.stopPoll()
      this.pendingProgress = 10
      this.pollTimer = setInterval(async () => {
        this.pendingProgress = Math.min(90, this.pendingProgress + 8)
        try {
          const res = await API.trainingSessionResult({ session_id: this.sessionId })
          const data = res.data || {}
          this.session = data.session || this.session
          this.score = data.score || null
          this.status = Number(this.session.status || 0)
          if (this.status === 2 || this.status === 3) {
            this.pendingProgress = 100
            this.stopPoll()
          }
        } catch (e) { /* 拦截器已处理 */ }
      }, 3000)
    },
    stopPoll() {
      if (this.pollTimer) {
        clearInterval(this.pollTimer)
        this.pollTimer = null
      }
    },
    onBack() {
      if (this.from === 'challenge') {
        this.$router.push('/training/challenge')
      } else {
        this.$router.push('/training/history')
      }
    },
    async onTrainAgain() {
      if (!this.session.scenario_id) return
      this.loading = true
      try {
        const res = await API.trainingStartSession({ scenario_id: this.session.scenario_id })
        const sid = res.data && res.data.session_id
        if (sid) {
          this.stopPoll()
          this.$router.push({ path: '/training/challenge', query: { session_id: sid } })
        }
      } finally {
        this.loading = false
      }
    }
  }
}
</script>

<style lang="scss" scoped>
.training-result-page {
  padding: 16px 20px 24px;
}

// 顶栏
.topbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 18px;
  gap: 12px;
  .page-title { margin: 0; font-size: 20px; font-weight: 700; color: #111827; }
  .page-desc { margin-top: 4px; font-size: 13px; color: #6b7280; }
}
.topbar-actions { display: flex; gap: 10px; flex-shrink: 0; }
.ds-btn {
  height: 32px;
  padding: 0 18px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: opacity 0.2s, background 0.2s;
  &--primary {
    background: linear-gradient(135deg, #6366f1, #9333ea);
    color: #fff;
    border: 0;
    &:hover { opacity: 0.92; }
  }
  &--default {
    background: #fff;
    border: 1px solid #e5e7eb;
    color: #374151;
    &:hover { background: #f9fafb; }
  }
}

// 卡片基础
.card {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: 18px 20px;
  margin-bottom: 12px;
  &__title { font-size: 14px; font-weight: 600; color: #111827; margin-bottom: 12px; }
}

// 上半：综合评分 + 维度得分
.main-row {
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: 14px;
  margin-bottom: 8px;
  .card { margin-bottom: 0; height: 100%; }
}
.score-card {
  text-align: center;
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
  align-items: stretch;
  padding-top: 22px;
  &__title { font-size: 13px; color: #6b7280; margin-bottom: 8px; }
  .score-value { font-size: 56px; font-weight: 700; color: #6366f1; line-height: 1; }
  .score-grade {
    display: inline-block;
    margin: 8px auto 18px;
    padding: 2px 10px;
    background: #dcfce7;
    color: #16a34a;
    border-radius: 4px;
    font-size: 13px;
    font-weight: 600;
  }
  .score-tip { font-size: 12px; color: #6b7280; }
  .score-tip--pending { margin-top: 10px; }
  .status-pending { font-size: 16px; color: #f59e0b; margin: 12px 0 14px; }
  .status-failed { font-size: 16px; color: #dc2626; margin: 16px 0; font-weight: 600; }
  .pending-progress { margin-bottom: 4px; }
}
.score-meta {
  margin-top: auto;
  text-align: left;
  padding-top: 8px;
  min-width: 0;
  &__row {
    display: flex;
    align-items: center;
    padding: 4px 0;
    font-size: 13px;
    color: #374151;
    min-width: 0;
  }
  &__label { color: #9ca3af; flex-shrink: 0; width: 50px; }
  &__value {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    word-break: break-all;
  }
}

// 维度卡（横向 progress + 数字）
.dim-card {
  padding: 18px 24px;
}
.dim-row {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 10px 0;
  &__name { width: 70px; font-size: 13px; color: #374151; flex-shrink: 0; }
  &__bar {
    flex: 1;
    height: 8px;
    background: #f3f4f6;
    border-radius: 4px;
    overflow: hidden;
  }
  &__bar-fill {
    height: 100%;
    background: linear-gradient(90deg, #6366f1, #9333ea);
    border-radius: 4px;
    transition: width 0.3s ease-out;
  }
  &__score {
    width: 32px;
    text-align: right;
    font-size: 15px;
    font-weight: 700;
    color: #111827;
    flex-shrink: 0;
  }
}

// 平均分提示
.impact-tip {
  margin: 10px 0 14px;
  font-size: 12px;
  color: #6b7280;
}

// AI 总评 + 改进建议
.dual-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 12px;
  .card { margin-bottom: 0; }
}
.ai-summary { font-size: 13px; line-height: 1.8; color: #374151; margin: 0; }
.ai-highlights {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px dashed #e5e7eb;
  &__label { font-size: 13px; color: #6b7280; margin-bottom: 4px; }
}
.bullet { padding-left: 18px; margin: 0; font-size: 13px; line-height: 1.8; color: #374151; }
.ordered { padding-left: 22px; margin: 0; font-size: 13px; line-height: 1.9; color: #374151; }
.skeleton {
  padding: 14px;
  background: #f9fafb;
  border-radius: 6px;
  color: #9ca3af;
  text-align: center;
  font-size: 13px;
  &.danger { color: #dc2626; background: #fef2f2; }
}

// 对话回放
.replay-card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.replay-badges {
  display: flex;
  gap: 6px;
  .badge {
    background: #f3f4f6;
    color: #6b7280;
    font-size: 12px;
    padding: 2px 8px;
    border-radius: 4px;
  }
}
.replay-list {
  max-height: 560px;
  overflow-y: auto;
  padding: 4px 2px;
  .empty { text-align: center; color: #9ca3af; padding: 30px 0; }
  .msg-row {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    margin-bottom: 14px;
    &.role-seat { justify-content: flex-end; .msg-bubble { background: linear-gradient(135deg, #6366f1, #9333ea); color: #fff; } }
    &.role-customer { justify-content: flex-start; .msg-bubble { background: #fff; color: #111827; border: 1px solid #e5e7eb; } }
  }
  .msg-bubble {
    max-width: 72%;
    padding: 10px 14px;
    border-radius: 12px;
    line-height: 1.6;
    font-size: 13px;
    white-space: pre-wrap;
    word-break: break-word;
  }
  .msg-avatar {
    flex-shrink: 0;
    width: 36px;
    height: 36px;
    border-radius: 50%;
    display: grid;
    place-items: center;
    font-size: 13px;
    font-weight: 600;
    color: #fff;
    &--customer { background: #94a3b8; }
    &--seat { background: linear-gradient(135deg, #6366f1, #9333ea); }
  }
}

.muted { color: #9ca3af; }
.ml-8 { margin-left: 8px; }
</style>
