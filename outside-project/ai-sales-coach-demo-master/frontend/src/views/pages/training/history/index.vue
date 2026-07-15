<template>
  <div class="training-history-page">
    <page-header title="练习记录" desc="按角色权限查看陪练历史记录，可跳转评分详情" />

    <div class="filter-bar">
      <el-date-picker
        v-model="filter.time_range"
        type="daterange"
        size="small"
        value-format="yyyy-MM-dd"
        range-separator="-"
        start-placeholder="开始日期"
        end-placeholder="结束日期"
        class="date-picker"
        @change="loadList(1)"
      />
      <el-select
        v-if="canFilterGroup"
        v-model="filter.group_id"
        size="small"
        clearable
        placeholder="全部分组"
        class="filter-select"
        @change="loadList(1)"
      >
        <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
      </el-select>
      <el-select v-model="filter.scenario_id" size="small" clearable placeholder="全部场景" class="filter-select" @change="loadList(1)">
        <el-option v-for="s in scenarios" :key="s.id" :label="s.name" :value="s.id" />
      </el-select>
      <el-input
        v-model="filter.keyword"
        size="small"
        placeholder="搜索坐席或场景"
        clearable
        prefix-icon="el-icon-search"
        class="search-input"
        @keyup.enter.native="loadList(1)"
        @blur="loadList(1)"
        @clear="loadList(1)"
      />
    </div>

    <el-table :data="list" v-loading="loading" size="medium" class="history-table">
      <el-table-column label="练习时间" width="160">
        <template slot-scope="{ row }">
          <div class="time-date">{{ formatDate(row.ended_at) }}</div>
          <div class="time-clock">{{ formatClock(row.ended_at) }}</div>
        </template>
      </el-table-column>
      <el-table-column label="坐席" min-width="160">
        <template slot-scope="{ row }">
          <div class="seat-cell">
            <span :class="['seat-avatar', `seat-avatar--${avatarColor(row.user_name)}`]">{{ (row.user_name || '?').slice(0, 1) }}</span>
            <div class="seat-info">
              <div class="seat-name">{{ row.user_name || '-' }}</div>
              <div class="seat-group">{{ groupMap[row.group_id] || '' }}</div>
            </div>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="场景" min-width="220">
        <template slot-scope="{ row }">
          <span class="scenario-name">{{ row.scenario_name }}</span>
          <span :class="['difficulty-tag', `difficulty-tag--${row.difficulty}`]">{{ difficultyLabel(row.difficulty) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="综合评分" width="140" align="center">
        <template slot-scope="{ row }">
          <template v-if="Number(row.status) === 2 && row.total_score !== null">
            <div :class="['score-pill', `score-pill--${gradeKey(row.total_score)}`]">
              <span class="score-pill__num">{{ row.total_score }}</span><span class="score-pill__unit">/100</span>
            </div>
          </template>
          <template v-else>
            <div class="score-pill score-pill--empty"><span class="score-pill__num">— —</span></div>
            <div v-if="Number(row.status) === 1" class="status-chip status-chip--pending">评分中</div>
            <div v-else-if="Number(row.status) === 3" class="status-chip status-chip--failed">评分失败</div>
          </template>
        </template>
      </el-table-column>
      <el-table-column label="时长 · 轮次" width="140">
        <template slot-scope="{ row }">
          <div class="duration-line">{{ formatDuration(row.duration_sec) }}</div>
          <div class="rounds-line">{{ Math.ceil((row.message_count || 0) / 2) }} 轮对话</div>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="120" align="right">
        <template slot-scope="{ row }">
          <a class="detail-link" @click="viewDetail(row)">查看详情 →</a>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页 -->
    <div class="task-pagination">
      <el-pagination
        @current-change="handleCurrentChange"
        @size-change="handleSizeChange"
        layout="total, prev, pager, next, sizes, jumper"
        :page-sizes="[20, 50, 100, 300]"
        :total="total"
        :page-size="pagination.limit"
        :current-page.sync="pagination.page"
        :hide-on-single-page="total > 0 ? false : true"
        background
      />
    </div>
  </div>
</template>

<script>
import API from '@/api'
import PageHeader from '@/components/PageHeader/index.vue'

const DIFFICULTY_LABELS = { 1: '简单', 2: '中等', 3: '困难', 4: '专家' }
const DIFFICULTY_TAGS = { 1: 'success', 2: 'info', 3: 'warning', 4: 'danger' }

export default {
  name: 'TrainingHistory',
  components: { PageHeader },
  data() {
    return {
      loading: false,
      list: [],
      total: 0,
      filter: { time_range: [], group_id: '', scenario_id: '', keyword: '' },
      pagination: { page: 1, limit: 20 },
      groups: [],
      scenarios: [],
      viewer: { is_staff: 0, is_group_manager: 0, id: 0 }
    }
  },
  computed: {
    groupMap() {
      const m = {}
      this.groups.forEach(g => { m[g.id] = g.name })
      return m
    },
    canFilterGroup() {
      // 仅管理员展示「全部分组」筛选；组长/坐席数据已被后端按本组/本人收敛
      return !this.viewer.is_staff
    }
  },
  created() {
    this.loadGroups()
    this.loadScenarios()
    this.loadList()
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
    gradeKey(score) {
      if (score >= 90) return 'excellent'
      if (score >= 80) return 'good'
      if (score >= 70) return 'pass'
      return 'weak'
    },
    avatarColor(name) {
      const colors = ['indigo', 'pink', 'green', 'orange', 'cyan', 'rose']
      const code = (name || '?').charCodeAt(0) || 0
      return colors[code % colors.length]
    },
    parseTime(ts) {
      if (!ts) return null
      if (typeof ts === 'number' || /^\d+$/.test(String(ts))) {
        const n = Number(ts)
        return new Date(n > 100000000000 ? n : n * 1000)
      }
      return new Date(String(ts).replace(' ', 'T'))
    },
    formatDate(ts) {
      if (!ts) return '-'
      const d = this.parseTime(ts)
      if (!d || Number.isNaN(d.getTime())) return '-'
      const pad = n => String(n).padStart(2, '0')
      return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
    },
    formatClock(ts) {
      if (!ts) return ''
      const d = this.parseTime(ts)
      if (!d || Number.isNaN(d.getTime())) return ''
      const pad = n => String(n).padStart(2, '0')
      return `${pad(d.getHours())}:${pad(d.getMinutes())}`
    },
    formatDuration(sec) {
      sec = Number(sec) || 0
      if (sec < 60) return `${sec} 秒`
      return `${Math.floor(sec / 60)} 分 ${String(sec % 60).padStart(2, '0')} 秒`
    },
    async loadGroups() {
      const res = await API.trainingGroupList()
      this.groups = res.data || []
      this.viewer = res.viewer || { is_staff: 0, is_group_manager: 0, id: 0 }
    },
    async loadScenarios() {
      const res = await API.trainingScenarioList({ page: 1, limit: 200, status: 1 })
      const data = res.data || {}
      this.scenarios = data.list || []
    },
    async loadList(page) {
      if (page) this.pagination.page = page
      this.loading = true
      try {
        const timeRange = this.filter.time_range || []
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
        this.list = data.list || []
        this.total = data.total || 0
        this.viewer = data.viewer || this.viewer
      } finally {
        this.loading = false
      }
    },
    handleCurrentChange(val) {
      this.pagination.page = val
      this.loadList()
    },
    handleSizeChange(val) {
      this.pagination.limit = val
      this.pagination.page = 1
      this.loadList()
    },
    viewDetail(row) {
      this.$router.push({ path: '/training/result', query: { session_id: row.session_id, from: 'history' } })
    }
  }
}
</script>

<style lang="scss" scoped>
.training-history-page { padding: 16px 20px 24px; }
.filter-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}
.date-picker { width: 260px; }
.search-input { width: 240px; }
.filter-select { width: 160px; }

// 表格整体去边框
.history-table ::v-deep {
  border: 0;
  &::before { display: none; }
  .el-table__row { height: 60px; }
  td, th.is-leaf { border-bottom: 1px solid #f3f4f6; }
  td { padding: 6px 0; }
  th { background: #fafafa; color: #6b7280; font-weight: 500; padding: 6px 0; }
}

// 时间列
.time-date { font-size: 13px; color: #111827; font-weight: 600; line-height: 1.3; }
.time-clock { font-size: 12px; color: #9ca3af; line-height: 1.3; }

// 坐席
.seat-cell { display: flex; align-items: center; gap: 8px; }
.seat-avatar {
  width: 28px; height: 28px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  flex-shrink: 0;
  &--indigo { background: #6366f1; }
  &--pink   { background: #ec4899; }
  &--green  { background: #16a34a; }
  &--orange { background: #f59e0b; }
  &--cyan   { background: #06b6d4; }
  &--rose   { background: #be185d; }
}
.seat-info { line-height: 1.3; }
.seat-name { font-size: 13px; color: #111827; font-weight: 600; }
.seat-group { font-size: 11px; color: #9ca3af; }

// 场景
.scenario-name { font-size: 13px; color: #111827; font-weight: 600; margin-right: 8px; }
.difficulty-tag {
  display: inline-block;
  padding: 1px 8px;
  font-size: 12px;
  border-radius: 4px;
  font-weight: 500;
  vertical-align: middle;
  &--1 { background: #dbeafe; color: #2563eb; }
  &--2 { background: #e0f2fe; color: #0891b2; }
  &--3 { background: #fef3c7; color: #b45309; }
  &--4 { background: #fee2e2; color: #b91c1c; }
}

// 综合评分
.score-pill {
  display: inline-flex;
  align-items: baseline;
  padding: 3px 12px;
  border-radius: 5px;
  font-weight: 700;
  line-height: 1.3;
  &__num { font-size: 15px; }
  &__unit { font-size: 11px; opacity: 0.7; font-weight: 500; margin-left: 1px; }
  &--excellent { background: #dcfce7; color: #15803d; }
  &--good { background: #d1fae5; color: #047857; }
  &--pass { background: #fef3c7; color: #b45309; }
  &--weak { background: #fee2e2; color: #b91c1c; }
  &--empty { background: #f3f4f6; color: #9ca3af; }
}
.status-chip {
  display: inline-block;
  margin-top: 4px;
  padding: 1px 8px;
  font-size: 11px;
  border-radius: 4px;
  &--pending { background: #dbeafe; color: #2563eb; }
  &--failed { background: #fee2e2; color: #b91c1c; }
}

// 时长 · 轮次
.duration-line { font-size: 13px; color: #111827; font-weight: 600; line-height: 1.3; }
.rounds-line { font-size: 11px; color: #9ca3af; line-height: 1.3; }

// 查看详情
.detail-link {
  font-size: 13px;
  color: #6366f1;
  cursor: pointer;
  user-select: none;
  &:hover { color: #4f46e5; }
}

.muted { color: #9ca3af; font-size: 12px; }
.mt-2 { margin-top: 2px; }
.task-pagination {
  display: flex;
  justify-content: flex-start;
  margin-top: 16px;
}
</style>
