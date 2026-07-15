<template>
  <div class="h5-history">
    <van-nav-bar
      title="练习记录"
      right-text="筛选"
      fixed
      safe-area-inset-top
      @click-right="filterVisible = true"
    />
    <div class="nav-spacer" />

    <div v-if="activeFilterText" class="active-filter-tip">
      <span>{{ activeFilterText }}</span>
      <span class="clear-link" @click="clearFilter">清除</span>
    </div>

    <van-pull-refresh v-model="refreshing" @refresh="onRefresh">
      <van-empty v-if="!loading && list.length === 0" description="暂无练习记录" />
      <van-list
        v-else
        v-model="listLoading"
        :finished="finished"
        finished-text="没有更多了"
        :immediate-check="false"
        @load="loadMore"
      >
        <div v-for="row in list" :key="row.session_id" class="record-card" @click="viewDetail(row)">
          <div class="record-card__score">
            <template v-if="Number(row.status) === 2 && row.total_score !== null && row.total_score !== undefined">
              <div :class="['score-num', gradeKey(row.total_score)]">{{ row.total_score }}</div>
              <div :class="['score-label', gradeKey(row.total_score)]">{{ gradeLabel(row.total_score) }}</div>
            </template>
            <template v-else-if="Number(row.status) === 1">
              <van-loading size="22" color="#6366F1" />
              <div class="score-label pending">评分中</div>
            </template>
            <template v-else-if="Number(row.status) === 3">
              <div class="score-num failed">--</div>
              <div class="score-label failed">评分失败</div>
            </template>
            <template v-else>
              <div class="score-num empty">--</div>
              <div class="score-label empty">未完成</div>
            </template>
          </div>
          <div class="record-card__main">
            <div class="record-card__title">
              <span>{{ row.scenario_name }}</span>
              <span :class="['tag', `tag-diff-${row.difficulty}`]">{{ difficultyLabel(row.difficulty) }}</span>
            </div>
            <div class="record-card__meta">
              <span>{{ formatTime(row.ended_at || row.created_at) }}</span>
              <span class="dot">·</span>
              <span>{{ formatDuration(row.duration_sec) }}</span>
              <span class="dot">·</span>
              <span>{{ Math.ceil((row.message_count || 0) / 2) }} 轮</span>
            </div>
            <div class="record-card__foot">
              <span v-if="!viewer.is_staff" class="seat-name">{{ row.user_name || '-' }}<span v-if="row.group_name" class="seat-group"> · {{ row.group_name }}</span></span>
              <span v-else class="seat-name">{{ row.user_name || '我' }}</span>
              <span class="detail-link">查看 ›</span>
            </div>
          </div>
        </div>
      </van-list>
    </van-pull-refresh>

    <!-- 筛选 -->
    <van-popup v-model="filterVisible" position="bottom" round closeable>
      <div class="filter-sheet">
        <div class="filter-sheet__title">筛选条件</div>

        <div class="filter-sheet__group">
          <div class="filter-sheet__label">时间</div>
          <div class="chips-row">
            <span :class="['chip', timePreset === 'all' ? 'active' : '']" @click="setTimePreset('all')">全部</span>
            <span :class="['chip', timePreset === '7d' ? 'active' : '']" @click="setTimePreset('7d')">近 7 天</span>
            <span :class="['chip', timePreset === '30d' ? 'active' : '']" @click="setTimePreset('30d')">近 30 天</span>
            <span :class="['chip', timePreset === 'month' ? 'active' : '']" @click="setTimePreset('month')">本月</span>
          </div>
        </div>

        <div class="filter-sheet__group">
          <div class="filter-sheet__label">场景</div>
          <div class="chips-row scenario-chips">
            <span :class="['chip', !draft.scenario_id ? 'active' : '']" @click="draft.scenario_id = ''">全部</span>
            <span v-for="s in scenarios" :key="s.id" :class="['chip', draft.scenario_id === s.id ? 'active' : '']" @click="draft.scenario_id = s.id">{{ s.name }}</span>
          </div>
        </div>

        <div v-if="canFilterGroup" class="filter-sheet__group">
          <div class="filter-sheet__label">分组</div>
          <div class="chips-row">
            <span :class="['chip', !draft.group_id ? 'active' : '']" @click="draft.group_id = ''">全部</span>
            <span v-for="g in groups" :key="g.id" :class="['chip', draft.group_id === g.id ? 'active' : '']" @click="draft.group_id = g.id">{{ g.name }}</span>
          </div>
        </div>

        <div class="filter-sheet__group">
          <div class="filter-sheet__label">关键词</div>
          <van-field v-model="draft.keyword" placeholder="搜索坐席或场景" clearable />
        </div>

        <div class="filter-sheet__actions">
          <button class="ghost-btn" @click="resetDraft">重置</button>
          <button class="h5-gradient-btn" @click="applyFilter">确定</button>
        </div>
      </div>
    </van-popup>
  </div>
</template>

<script>
import API from '@/api'

const DIFFICULTY_LABELS = { 1: '简单', 2: '中等', 3: '困难', 4: '专家' }
const PRESET_LABELS = { all: '全部', '7d': '近 7 天', '30d': '近 30 天', month: '本月' }

export default {
  name: 'H5History',
  data() {
    return {
      loading: false,
      listLoading: false,
      refreshing: false,
      finished: false,
      list: [],
      total: 0,
      pagination: { page: 1, limit: 20 },
      filter: { group_id: '', scenario_id: '', keyword: '', time_range: [] },
      draft: { group_id: '', scenario_id: '', keyword: '' },
      timePreset: 'all',
      draftTimePreset: 'all',
      scenarios: [],
      groups: [],
      viewer: { is_staff: 1, is_group_manager: 0, id: 0 },
      filterVisible: false
    }
  },
  computed: {
    canFilterGroup() {
      return !this.viewer.is_staff || this.viewer.is_group_manager == 1
    },
    activeFilterText() {
      const parts = []
      if (this.timePreset !== 'all') parts.push(PRESET_LABELS[this.timePreset])
      const sc = this.scenarios.find(s => s.id === this.filter.scenario_id)
      if (sc) parts.push(sc.name)
      const g = this.groups.find(x => x.id === this.filter.group_id)
      if (g) parts.push(g.name)
      if (this.filter.keyword) parts.push(`"${this.filter.keyword}"`)
      return parts.length ? '筛选: ' + parts.join(' · ') : ''
    }
  },
  async created() {
    await Promise.all([this.loadGroups(), this.loadScenarios()])
    await this.loadList(1)
  },
  async activated() {
    // 切回该 tab 时刷新最新状态(可能评分完成了)
    await this.loadList(1)
  },
  methods: {
    difficultyLabel(d) { return DIFFICULTY_LABELS[d] || '-' },
    gradeKey(s) {
      const n = Number(s)
      if (n >= 90) return 'excellent'
      if (n >= 80) return 'good'
      if (n >= 70) return 'pass'
      return 'weak'
    },
    gradeLabel(s) {
      const n = Number(s)
      if (n >= 90) return '优秀'
      if (n >= 80) return '良好'
      if (n >= 70) return '合格'
      return '需加强'
    },
    formatTime(ts) {
      if (!ts) return '-'
      let d
      if (typeof ts === 'number' || /^\d+$/.test(String(ts))) {
        const n = Number(ts)
        d = new Date(n > 100000000000 ? n : n * 1000)
      } else {
        d = new Date(String(ts).replace(' ', 'T'))
      }
      if (Number.isNaN(d.getTime())) return '-'
      const now = new Date()
      const pad = n => String(n).padStart(2, '0')
      const sameDay = d.toDateString() === now.toDateString()
      const yest = new Date(); yest.setDate(yest.getDate() - 1)
      const isYest = d.toDateString() === yest.toDateString()
      const clock = `${pad(d.getHours())}:${pad(d.getMinutes())}`
      if (sameDay) return `今天 ${clock}`
      if (isYest) return `昨天 ${clock}`
      return `${pad(d.getMonth() + 1)}/${pad(d.getDate())} ${clock}`
    },
    formatDuration(sec) {
      sec = Number(sec) || 0
      if (sec < 60) return `${sec} 秒`
      return `${Math.floor(sec / 60)} 分 ${String(sec % 60).padStart(2, '0')} 秒`
    },

    async loadGroups() {
      try {
        const res = await API.trainingGroupList()
        this.groups = res.data || []
        this.viewer = res.viewer || { is_staff: 1, is_group_manager: 0, id: 0 }
      } catch (e) { /* 忽略 */ }
    },
    async loadScenarios() {
      try {
        const res = await API.trainingScenarioListForUser({})
        this.scenarios = res.data || []
      } catch (e) { /* 忽略 */ }
    },
    computeTimeRange() {
      const preset = this.timePreset
      if (preset === 'all') return []
      const pad = n => String(n).padStart(2, '0')
      const fmt = d => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
      const end = new Date()
      const start = new Date()
      if (preset === '7d') start.setDate(end.getDate() - 6)
      else if (preset === '30d') start.setDate(end.getDate() - 29)
      else if (preset === 'month') start.setDate(1)
      return [fmt(start), fmt(end)]
    },

    async loadList(page) {
      if (page) {
        this.pagination.page = page
        this.finished = false
        this.list = []
      }
      this.loading = true
      // 进入加载就锁住 van-list 的 v-model,避免清空 list 时 van-list 误触发 @load 导致 page 跳 2
      this.listLoading = true
      try {
        const timeRange = this.computeTimeRange()
        const res = await API.trainingSessionHistory({
          page: this.pagination.page,
          limit: this.pagination.limit,
          group_id: this.filter.group_id,
          scenario_id: this.filter.scenario_id,
          keyword: this.filter.keyword,
          date_start: timeRange[0] || '',
          date_end: timeRange[1] || ''
        })
        const data = res.data || {}
        const rows = data.list || []
        if (this.pagination.page === 1) this.list = rows
        else this.list = this.list.concat(rows)
        this.total = data.total || 0
        if (this.list.length >= this.total) this.finished = true
        if (data.viewer) this.viewer = data.viewer
      } finally {
        this.loading = false
        this.listLoading = false
      }
    },
    async loadMore() {
      // 下拉刷新进行中、首次加载中、或已加载完,都不能再推进 page,防止 van-list 在 list 清空瞬间误触发 @load
      if (this.finished || this._refreshing || this.loading) return
      this.pagination.page++
      await this.loadList()
    },
    async onRefresh() {
      this._refreshing = true
      try {
        await this.loadList(1)
      } finally {
        this.refreshing = false
        this._refreshing = false
      }
    },

    setTimePreset(p) {
      // 直接在面板里改 draft,等"确定"才应用,但 timePreset 是 active 显示用
      this.draftTimePreset = p
      this.timePreset = p
    },
    resetDraft() {
      this.draft = { group_id: '', scenario_id: '', keyword: '' }
      this.timePreset = 'all'
    },
    applyFilter() {
      this.filter.group_id = this.draft.group_id
      this.filter.scenario_id = this.draft.scenario_id
      this.filter.keyword = this.draft.keyword
      this.filterVisible = false
      this.loadList(1)
    },
    clearFilter() {
      this.filter = { group_id: '', scenario_id: '', keyword: '', time_range: [] }
      this.draft = { group_id: '', scenario_id: '', keyword: '' }
      this.timePreset = 'all'
      this.loadList(1)
    },
    viewDetail(row) {
      this.$router.push({ path: '/m/history/detail', query: { session_id: row.session_id, from: 'history' } })
    }
  },
  watch: {
    filterVisible(v) {
      if (v) {
        // 打开时把 filter 灌到 draft
        this.draft.group_id = this.filter.group_id
        this.draft.scenario_id = this.filter.scenario_id
        this.draft.keyword = this.filter.keyword
        this.draftTimePreset = this.timePreset
      }
    }
  }
}
</script>

<style lang="scss" scoped>
.h5-history {
  min-height: 100vh;
  background: var(--h5-bg);
}
.nav-spacer { height: 46px; }

.active-filter-tip {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 14px;
  background: var(--h5-primary-soft);
  color: var(--h5-primary);
  font-size: 12px;
  .clear-link { color: var(--h5-text-2); font-weight: 500; }
}

.record-card {
  background: #fff;
  margin: 10px 12px 0;
  border-radius: var(--h5-radius);
  padding: 14px;
  display: flex;
  gap: 12px;
  box-shadow: var(--h5-shadow);
}
.record-card__score {
  width: 60px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border-right: 1px solid var(--h5-border);
  padding-right: 12px;

  .score-num {
    font-size: 28px;
    font-weight: 700;
    line-height: 1;
    &.excellent { color: var(--h5-success); }
    &.good { color: var(--h5-info); }
    &.pass { color: var(--h5-warning); }
    &.weak { color: #6B7280; }
    &.failed { color: #DC2626; }
    &.empty { color: #D1D5DB; }
  }
  .score-label {
    font-size: 11px;
    color: var(--h5-text-3);
    margin-top: 4px;
    &.excellent { color: var(--h5-success); }
    &.good { color: var(--h5-info); }
    &.pass { color: var(--h5-warning); }
    &.weak { color: #6B7280; }
    &.failed { color: #DC2626; }
    &.pending { color: var(--h5-primary); margin-top: 6px; }
  }
}
.record-card__main {
  flex: 1;
  min-width: 0;
}
.record-card__title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 600;
  color: var(--h5-text-1);
  margin-bottom: 6px;
  span:first-child {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
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
.record-card__meta {
  font-size: 12px;
  color: var(--h5-text-3);
  margin-bottom: 8px;
  .dot { margin: 0 4px; }
}
.record-card__foot {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
  .seat-name {
    color: var(--h5-text-2);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    .seat-group { color: var(--h5-text-3); }
  }
  .detail-link {
    color: var(--h5-primary);
    flex-shrink: 0;
  }
}

.filter-sheet {
  padding: 22px 16px 16px;
  max-height: 80vh;
  overflow-y: auto;

  &__title {
    font-size: 17px;
    font-weight: 600;
    color: var(--h5-text-1);
    margin-bottom: 18px;
    text-align: center;
  }
  &__group { margin-bottom: 18px; }
  &__label {
    font-size: 13px;
    color: var(--h5-text-2);
    margin-bottom: 10px;
  }
  &__actions {
    display: flex;
    gap: 10px;
    margin-top: 10px;
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
}
.chips-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.scenario-chips { max-height: 156px; overflow-y: auto; }
.chip {
  padding: 5px 12px;
  font-size: 12px;
  border-radius: 14px;
  background: var(--h5-bg);
  color: var(--h5-text-2);
  border: 1px solid var(--h5-border);
  white-space: nowrap;
  &.active {
    background: var(--h5-primary-soft);
    color: var(--h5-primary);
    border-color: transparent;
    font-weight: 500;
  }
}

::v-deep .van-nav-bar { background: #fff; .van-nav-bar__title { font-weight: 600; } }
</style>
