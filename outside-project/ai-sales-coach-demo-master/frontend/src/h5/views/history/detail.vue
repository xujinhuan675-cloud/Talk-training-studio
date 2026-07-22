<template>
  <div class="h5-history-detail">
    <van-nav-bar title="练习详情" left-arrow fixed safe-area-inset-top @click-left="onBack" />
    <div class="nav-spacer" />

    <template v-if="session.id">
      <!-- 总分卡 -->
      <div class="score-hero">
        <template v-if="status === 2 && score">
          <div class="score-hero__num">{{ score.total_score }}</div>
          <div class="score-hero__label">综合评分 · {{ gradeLabel(score.total_score) }}</div>
        </template>
        <template v-else-if="status === 1">
          <van-loading color="#fff" size="36" />
          <div class="score-hero__label">AI 正在评分中...</div>
          <van-progress
            :percentage="pendingProgress"
            :show-pivot="false"
            color="#FFFFFF"
            track-color="rgba(255,255,255,.2)"
            class="hero-progress"
          />
        </template>
        <template v-else-if="status === 3">
          <div class="score-hero__num failed">--</div>
          <div class="score-hero__label">评分异常,请联系管理员</div>
        </template>
        <template v-else>
          <div class="score-hero__num empty">--</div>
          <div class="score-hero__label">未完成</div>
        </template>
      </div>

      <!-- 元数据 -->
      <div class="meta-card h5-card">
        <div class="meta-card__row"><span>场景</span><b>{{ session.scenario_name }}</b></div>
        <div class="meta-card__row"><span>难度</span><b>{{ difficultyLabel(session.difficulty) }}</b></div>
        <div class="meta-card__row"><span>用时</span><b>{{ formatDuration(session.duration_sec) }}</b></div>
        <div class="meta-card__row"><span>对话</span><b>{{ Math.ceil((session.message_count || 0) / 2) }} 轮</b></div>
      </div>

      <!-- 维度评分 -->
      <div v-if="status === 2 && score && score.dimension_scores && score.dimension_scores.length" class="h5-card">
        <div class="section-title">维度评分</div>
        <score-bar
          v-for="d in score.dimension_scores"
          :key="d.dimension_id"
          :name="d.dimension_name"
          :value="d.score"
          :comment="d.comment || ''"
        />
      </div>

      <!-- AI 总评 -->
      <div v-if="status === 2 && score && score.summary" class="h5-card">
        <div class="section-title">AI 总评</div>
        <p class="ai-summary">{{ score.summary }}</p>
      </div>

      <!-- 改进建议 -->
      <div v-if="status === 2 && score && score.suggestions && score.suggestions.length" class="h5-card">
        <div class="section-title">改进建议</div>
        <ol class="suggestions">
          <li v-for="(s, i) in score.suggestions" :key="i">{{ s }}</li>
        </ol>
      </div>

      <!-- 评分中/失败占位 -->
      <div v-if="status === 1" class="h5-card pending-tip">
        评分通常在 30 秒内完成,本页面自动刷新...
      </div>
      <div v-if="status === 3" class="h5-card failed-tip">
        评分失败。可能因 AI 服务异常或网络问题导致,请联系管理员。
      </div>

      <!-- 实战回放 -->
      <div class="replay-card">
        <div class="section-title with-badges">
          实战回放
          <span class="badges">
            <span class="badge">{{ Math.ceil(messages.length / 2) }} 轮</span>
            <span class="badge">{{ formatDuration(session.duration_sec) }}</span>
          </span>
        </div>
        <message-list :messages="messages" :ai-replying="false" class="replay-list" />
      </div>

      <!-- 底部按钮 -->
      <div v-if="canTrainAgain" class="bottom-bar">
        <button class="ghost-btn" @click="onBack">返回</button>
        <button class="h5-gradient-btn" :disabled="restarting" @click="onTrainAgain">
          <van-loading v-if="restarting" color="#fff" size="14" />
          <span v-else>再练一次</span>
        </button>
      </div>
    </template>

    <van-empty v-else-if="!loading" description="未找到该练习记录" />
  </div>
</template>

<script>
import API from '@/api'
import MessageList from '../../components/MessageList.vue'
import ScoreBar from '../../components/ScoreBar.vue'

const DIFFICULTY_LABELS = { 1: '简单', 2: '中等', 3: '困难', 4: '专家' }

export default {
  name: 'H5HistoryDetail',
  components: { MessageList, ScoreBar },
  data() {
    return {
      loading: false,
      restarting: false,
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
      this.$toast('缺少 session_id')
      return
    }
    this.fetchDetail()
  },
  beforeDestroy() {
    this.stopPoll()
  },
  methods: {
    difficultyLabel(d) { return DIFFICULTY_LABELS[d] || '-' },
    gradeLabel(s) {
      const n = Number(s)
      if (n >= 90) return '优秀'
      if (n >= 80) return '良好'
      if (n >= 70) return '合格'
      return '需加强'
    },
    formatDuration(sec) {
      sec = Number(sec) || 0
      if (sec < 60) return `${sec} 秒`
      return `${Math.floor(sec / 60)} 分 ${String(sec % 60).padStart(2, '0')} 秒`
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
        } catch (e) { /* 拦截器处理 */ }
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
        this.$router.replace('/m/challenge')
      } else {
        this.$router.back()
      }
    },
    onTrainAgain() {
      if (!this.session.scenario_id) return
      // 不在 detail 预创建 session,交给 challenge 的 onStart 完整流程(避免 detail 接口对刚建会话兼容差)
      this.stopPoll()
      this.$router.replace({
        path: '/m/challenge',
        query: { scenario_id: this.session.scenario_id, action: 'restart' }
      })
    }
  }
}
</script>

<style lang="scss" scoped>
.h5-history-detail {
  min-height: 100vh;
  background: var(--h5-bg);
  padding-bottom: 80px;
}
.nav-spacer { height: 46px; }

.score-hero {
  background: var(--h5-gradient);
  color: #fff;
  padding: 24px 20px 28px;
  text-align: center;
  position: relative;
  &__num {
    font-size: 56px;
    font-weight: 700;
    line-height: 1;
    margin-bottom: 6px;
    &.failed, &.empty { color: rgba(255,255,255,.7); font-size: 36px; padding-top: 8px; }
  }
  &__label {
    font-size: 14px;
    color: rgba(255,255,255,.9);
    margin-top: 4px;
  }
}
.hero-progress {
  margin-top: 14px;
}

.meta-card {
  margin: 12px 12px 0;
  padding: 14px 16px;
  &__row {
    display: flex;
    justify-content: space-between;
    padding: 6px 0;
    font-size: 13px;
    span {
      color: var(--h5-text-3);
    }
    b {
      color: var(--h5-text-1);
      font-weight: 500;
      max-width: 60%;
      text-align: right;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
  }
}

.h5-card {
  margin: 12px 12px 0;
  padding: 14px 16px;
}

.section-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--h5-text-1);
  margin-bottom: 10px;
  &.with-badges {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
}
.badges {
  display: flex;
  gap: 6px;
  font-weight: 400;
}
.badge {
  font-size: 11px;
  color: var(--h5-text-3);
  background: #F3F4F6;
  padding: 2px 8px;
  border-radius: 4px;
}

.ai-summary {
  font-size: 13px;
  line-height: 1.6;
  color: var(--h5-text-2);
  white-space: pre-wrap;
  margin: 0;
}
.suggestions {
  margin: 0;
  padding-left: 20px;
  color: var(--h5-text-2);
  font-size: 13px;
  line-height: 1.7;
  li { margin-bottom: 4px; }
}

.pending-tip {
  text-align: center;
  color: var(--h5-primary);
  font-size: 13px;
}
.failed-tip {
  text-align: center;
  color: #DC2626;
  font-size: 13px;
  background: #FEF2F2;
  border: 1px solid #FECACA;
}

.replay-card {
  margin: 12px 12px 0;
  background: #fff;
  border-radius: var(--h5-radius);
  padding: 14px 0 0;
  box-shadow: var(--h5-shadow);
  overflow: hidden;
  .section-title { padding: 0 16px; }
  .replay-list {
    flex: none;
    max-height: 60vh;
    min-height: 200px;
  }
}

.bottom-bar {
  position: fixed;
  bottom: 0; left: 0; right: 0;
  background: #fff;
  padding: 10px 12px calc(10px + env(safe-area-inset-bottom));
  border-top: 1px solid var(--h5-border);
  display: flex;
  gap: 10px;
  z-index: 10;
  .ghost-btn {
    flex: 1;
    height: 44px;
    background: var(--h5-bg);
    color: var(--h5-text-2);
    border: 0;
    border-radius: 10px;
    font-size: 15px;
    font-weight: 500;
  }
  .h5-gradient-btn {
    flex: 2;
  }
}

::v-deep .van-nav-bar { background: #fff; .van-nav-bar__title { font-weight: 600; } }
</style>
