<template>
  <div class="training-leaderboard-page">
    <page-header title="排行榜" desc="排行榜仅展示完成全部启用必练场景的坐席。同一坐席同一场景多次练习时，主榜分数取最新一次已评分结果。" />

    <el-tabs v-model="activeTab" class="board-tabs" @tab-click="onTabChange">
      <!-- ====== 团队视图（普通坐席不可见） ====== -->
      <el-tab-pane v-if="canViewTeam" label="团队视图" name="team">
        <div class="filter-row">
          <div class="filter-left">
            <template v-if="canFilterGroup">
              <span class="filter-label">分组</span>
              <el-select v-model="teamFilter.group_id" size="small" clearable placeholder="全部分组" class="filter-select" @change="loadTeam">
                <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
              </el-select>
            </template>
          </div>
          <div class="filter-tip muted">仅展示必练完成度 100% 的坐席</div>
        </div>

        <!-- 4 张统计卡 -->
        <div class="stat-row">
          <div class="stat-card">
            <div class="stat-card__label">参与人数</div>
            <div class="stat-card__value stat-card__value--neutral">{{ teamStats.participants }}</div>
            <div class="stat-card__hint">{{ rangeLabel }}发起练习的坐席</div>
          </div>
          <div class="stat-card">
            <div class="stat-card__label">达标入榜</div>
            <div class="stat-card__value">{{ teamStats.ranked }}</div>
            <div class="stat-card__hint">必练完成度 100% 的坐席</div>
          </div>
          <div class="stat-card">
            <div class="stat-card__label">未完成</div>
            <div class="stat-card__value stat-card__value--warn">{{ teamStats.unfinishedActive }}</div>
            <div class="stat-card__hint stat-card__hint--warn">需提醒催办</div>
          </div>
          <div class="stat-card">
            <div class="stat-card__label">团队均分
              <el-tooltip placement="top">
                <div slot="content">入榜坐席（必练 100%）的必练均分</div>
                <i class="el-icon-info icon-help" />
              </el-tooltip>
            </div>
            <div class="stat-card__value">{{ teamStats.teamAvg !== null ? teamStats.teamAvg : '-' }}</div>
            <div class="stat-card__hint">入榜坐席必练均分</div>
          </div>
        </div>

        <!-- 主区双列：排行榜 + 团队洞察 -->
        <div class="team-main-row">
          <!-- 左：排行榜 -->
          <div class="card">
            <div class="card-head">
              <div class="card-title-wrap">
                <span class="card-title">排行榜</span>
                <el-tooltip placement="top">
                  <div slot="content">平均分 = 每个必练场景最新一次得分的算术平均</div>
                  <i class="el-icon-info icon-help" />
                </el-tooltip>
              </div>
              <span class="muted small">必练完成度 100% · 共 {{ teamStats.ranked }} 人</span>
            </div>
            <div v-if="teamData && teamData.ranks.length === 0" class="empty">暂无符合入榜条件的坐席</div>
            <div v-for="(r, i) in (teamData && teamData.ranks) || []" :key="r.user_id" class="rank-row">
              <div :class="['rank-badge', i + 1 <= 3 ? `rank-badge--${i + 1}` : 'rank-badge--default']">{{ i + 1 }}</div>
              <span :class="['rank-avatar', `rank-avatar--${avatarColor(r.user_name)}`]">{{ (r.user_name || '?').slice(0, 1) }}</span>
              <div class="rank-info">
                <div class="rank-name" :title="r.user_name">{{ r.user_name }}</div>
                <div class="rank-group muted" :title="groupMap[r.group_id] || ''">{{ groupMap[r.group_id] || '-' }}</div>
              </div>
              <div class="rank-score">{{ r.avg_score !== null ? r.avg_score : '-' }}</div>
              <div class="rank-count muted">{{ r.practice_count }} 次</div>
            </div>
          </div>

          <!-- 右：团队洞察（薄弱维度 / 场景均分 Tab） -->
          <div class="card">
            <div class="card-head">
              <div class="card-title-wrap">
                <span class="card-title">团队洞察</span>
              </div>
              <div class="mini-tabs">
                <span :class="['mini-tab', insightTab === 'weak' ? 'active' : '']" @click="insightTab = 'weak'">薄弱维度</span>
                <span :class="['mini-tab', insightTab === 'scenario' ? 'active' : '']" @click="insightTab = 'scenario'">场景均分</span>
              </div>
            </div>
            <div class="insight-desc muted small">
              {{ insightTab === 'weak' ? '维度均分升序 · 关注 < 70 分项' : '按团队均分升序 · 找出待加强场景' }}
            </div>

            <!-- 薄弱维度 -->
            <template v-if="insightTab === 'weak'">
              <div v-if="teamData && teamData.weak_dimensions.length === 0" class="empty">暂无评分数据</div>
              <div v-for="d in (teamData && teamData.weak_dimensions) || []" :key="d.dimension_id" class="insight-row">
                <div class="insight-row__head">
                  <span class="insight-name">{{ d.name }}</span>
                  <span :class="['insight-score', d.is_weak ? 'insight-score--alert' : '']">{{ d.avg_score }}</span>
                </div>
                <div class="insight-bar">
                  <div class="insight-bar__fill" :style="{ width: Math.min(100, d.avg_score) + '%', background: d.is_weak ? '#f59e0b' : '#16a34a' }" />
                </div>
                <div class="insight-row__tip muted">涉及场景：{{ (d.scenario_names || []).join('、') || '-' }}</div>
              </div>
            </template>

            <!-- 场景均分 -->
            <template v-else>
              <div v-if="teamData && teamData.scenario_avg.length === 0" class="empty">暂无场景评分数据</div>
              <div v-for="sc in (teamData && teamData.scenario_avg) || []" :key="sc.scenario_id" class="insight-row">
                <div class="insight-row__head">
                  <span class="insight-name">{{ sc.name }}</span>
                  <span :class="['difficulty-tag', `difficulty-tag--${sc.difficulty}`]">{{ difficultyLabel(sc.difficulty) }}</span>
                  <span :class="['insight-score', sc.avg_score < 70 ? 'insight-score--alert' : '']">{{ sc.avg_score }}</span>
                </div>
                <div class="insight-bar">
                  <div class="insight-bar__fill" :style="{ width: Math.min(100, sc.avg_score) + '%', background: sc.avg_score < 70 ? '#f59e0b' : '#16a34a' }" />
                </div>
                <div class="insight-row__tip muted">本期 {{ sc.participant_count }} 人次参与</div>
              </div>
            </template>
          </div>
        </div>

        <!-- 未完成名单 -->
        <div class="card">
          <div class="card-head">
            <div class="card-title-wrap">
              <span class="card-title">未完成名单</span>
              <span class="muted small ml-8">{{ unfinishedSplit.all.length }} 人</span>
            </div>
            <span class="muted small">不进入排行榜 · 按完成度倒序</span>
          </div>

          <div v-if="unfinishedSplit.all.length === 0" class="empty">全部坐席均已完成必练场景</div>

          <!-- 进行中分组 -->
          <template v-if="unfinishedSplit.inProgress.length > 0">
            <div class="unfinished-group-head">进行中 · {{ unfinishedSplit.inProgress.length }} 人</div>
            <div v-for="u in unfinishedSplit.inProgress" :key="'p-' + u.user_id" class="unfinished-row">
              <span :class="['rank-avatar', `rank-avatar--${avatarColor(u.user_name)}`]">{{ (u.user_name || '?').slice(0, 1) }}</span>
              <div class="unfinished-info">
                <div class="unfinished-name" :title="u.user_name">{{ u.user_name }}</div>
                <div class="unfinished-group muted" :title="groupMap[u.group_id] || ''">{{ groupMap[u.group_id] || '-' }}</div>
              </div>
              <div class="unfinished-progress-text">{{ u.required_finished }}/{{ u.required_total }}</div>
              <div class="unfinished-bar">
                <div class="unfinished-bar__fill" :style="{ width: Math.round((u.required_completion || 0) * 100) + '%', background: progressColor(u.required_completion) }" />
              </div>
              <div class="unfinished-score muted">已练 <b>{{ u.avg_score !== null ? u.avg_score : '-' }}</b></div>
              <div class="unfinished-missing muted" :title="(u.missing_scenarios || []).join('、')">
                <template v-if="u.missing_scenarios && u.missing_scenarios.length">缺失：{{ u.missing_scenarios.join('、') }}</template>
                <template v-else>—</template>
              </div>
            </div>
          </template>

          <!-- 未参与分组 -->
          <template v-if="unfinishedSplit.notStarted.length > 0">
            <div class="unfinished-group-head">未参与 · {{ unfinishedSplit.notStarted.length }} 人</div>
            <div v-for="u in unfinishedSplit.notStarted" :key="'n-' + u.user_id" class="unfinished-row unfinished-row--idle">
              <span :class="['rank-avatar', `rank-avatar--${avatarColor(u.user_name)}`]">{{ (u.user_name || '?').slice(0, 1) }}</span>
              <div class="unfinished-info">
                <div class="unfinished-name" :title="u.user_name">{{ u.user_name }}</div>
                <div class="unfinished-group muted" :title="groupMap[u.group_id] || ''">{{ groupMap[u.group_id] || '-' }}</div>
              </div>
              <div class="unfinished-progress-text muted">0/{{ u.required_total }}</div>
              <div class="unfinished-bar">
                <div class="unfinished-bar__fill" style="width: 0; background: #d1d5db" />
              </div>
              <div class="unfinished-score muted">—</div>
              <div class="unfinished-missing muted">未参与本期练习</div>
            </div>
          </template>
        </div>
      </el-tab-pane>

      <!-- ====== 个人视图 ====== -->
      <el-tab-pane label="个人视图" name="personal">
        <template v-if="personal && personal.user">
          <!-- 身份卡 + 筛选 -->
          <div class="identity-bar">
            <div class="identity-info">
              <span :class="['identity-avatar', `rank-avatar--${avatarColor(personal.user.name)}`]">{{ (personal.user.name || '?').slice(0, 1) }}</span>
              <div>
                <div class="identity-name">{{ personal.user.name }}</div>
                <div class="identity-meta">
                  <span class="identity-group">{{ groupMap[personal.user.group_id] || '-' }}</span>
                  <span :class="['identity-badge', `identity-badge--${personal.status}`]">
                    <template v-if="personal.status === 'ranked'">已入榜 #{{ personal.rank || '-' }}</template>
                    <template v-else-if="personal.status === 'partial'">未入榜 {{ personal.required_finished }}/{{ personal.required_total }}</template>
                    <template v-else>未参与</template>
                  </span>
                </div>
              </div>
            </div>
            <div v-if="canSelectEmployee" class="identity-filters">
              <span class="filter-label">员工</span>
              <el-select
                v-model="personalFilter.user_id"
                size="small"
                filterable
                placeholder="选择员工"
                class="filter-select wide"
                @change="loadPersonal"
              >
                <el-option v-for="e in employees" :key="e.id" :label="`${e.name}${groupMap[e.group_id] ? `（${groupMap[e.group_id]}）` : ''}`" :value="e.id" />
              </el-select>
            </div>
          </div>

          <!-- 部分完成 banner -->
          <div v-if="personal.status === 'partial'" class="banner banner-warn">
            <i class="el-icon-warning-outline" />
            <span>
              还有 {{ personal.required_total - personal.required_finished }} 个必练场景未完成
              <template v-if="personal.missing_required && personal.missing_required.length">
                ：{{ personal.missing_required.map(m => m.name).join('、') }}
              </template>
              ，完成全部必练后即可入榜
            </span>
          </div>

          <!-- 完全未参与 -->
          <div v-if="personal.status === 'unstart'" class="empty-big">
            <div class="empty-icon">🎯</div>
            <div class="empty-title">{{ personal.user.name }} 本期暂无练习数据</div>
            <div class="empty-desc">该员工尚未发起任何练习</div>
          </div>

          <template v-else>
            <!-- 4 张彩色图标统计卡 -->
            <div class="p-stat-row">
              <div class="p-stat">
                <div class="p-stat__icon p-stat__icon--rank">榜</div>
                <div class="p-stat__body">
                  <div class="p-stat__value">{{ personal.rank ? '#' + personal.rank : '—' }}</div>
                  <div class="p-stat__label">排名{{ !personal.rank ? ' · 未入榜' : '' }}</div>
                </div>
              </div>
              <div class="p-stat">
                <div class="p-stat__icon p-stat__icon--score">分</div>
                <div class="p-stat__body">
                  <div class="p-stat__value">{{ personal.avg_score !== null ? personal.avg_score : '—' }}</div>
                  <div class="p-stat__label">
                    平均分
                    <el-tooltip placement="top">
                      <div slot="content">每个必练场景最新一次得分的算术平均</div>
                      <i class="el-icon-info icon-help" />
                    </el-tooltip>
                  </div>
                </div>
              </div>
              <div class="p-stat">
                <div class="p-stat__icon p-stat__icon--practice">练</div>
                <div class="p-stat__body">
                  <div class="p-stat__value">{{ personal.required_finished }}<span class="p-stat__unit">/{{ personal.required_total }}</span></div>
                  <div class="p-stat__label">
                    必练完成度
                    <span :class="['p-stat__chip', personal.status === 'ranked' ? 'p-stat__chip--ok' : 'p-stat__chip--warn']">
                      {{ personal.status === 'ranked' ? '已达成' : '未达成' }}
                    </span>
                  </div>
                </div>
              </div>
              <div class="p-stat">
                <div class="p-stat__icon p-stat__icon--streak">续</div>
                <div class="p-stat__body">
                  <div class="p-stat__value">{{ personal.streak_days }}<span class="p-stat__unit">天</span></div>
                  <div class="p-stat__label">连续练习</div>
                </div>
              </div>
            </div>

            <!-- 能力画像 + 场景训练数据 -->
            <div class="dual-section">
              <div class="card with-accent">
                <div class="card-head">
                  <div class="card-title-wrap"><span class="card-title">能力画像</span></div>
                  <span class="muted small">按维度切片</span>
                </div>
                <div v-if="personal.ability_profile.length === 0" class="empty">暂无评分数据</div>
                <template v-else>
                  <div v-for="d in personal.ability_profile" :key="d.dimension_id" class="ability-row">
                    <div class="ability-row__head">
                      <span class="ability-name">{{ d.name }}</span>
                      <span :class="['ability-score', scoreLevel(d.avg_score)]">{{ d.avg_score }}</span>
                    </div>
                    <div class="ability-bar">
                      <div class="ability-bar__fill" :style="{ width: Math.min(100, d.avg_score) + '%', background: barColor(d.avg_score) }" />
                    </div>
                    <div v-if="weakestDimensionId === d.dimension_id" class="ability-row__tip">当前最低维度，建议加强</div>
                  </div>
                </template>
              </div>

              <div class="card with-accent">
                <div class="card-head">
                  <div class="card-title-wrap"><span class="card-title">不同场景训练数据</span></div>
                  <span class="muted small">按分数倒序</span>
                </div>
                <div v-for="s in personal.scenario_stats" :key="s.scenario_id" class="scenario-row">
                  <div class="scenario-row__head">
                    <span class="scenario-name">{{ s.name }}</span>
                    <span :class="['difficulty-tag', `difficulty-tag--${s.difficulty}`]">{{ difficultyLabel(s.difficulty) }}</span>
                    <span v-if="Number(s.is_required) === 1" class="difficulty-tag difficulty-tag--required ml-6">必练</span>
                    <span class="scenario-score">{{ s.my_score !== null ? s.my_score : '—' }}</span>
                  </div>
                  <div class="ability-bar">
                    <div class="ability-bar__fill" :style="{ width: Math.min(100, (s.my_score || 0)) + '%', background: barColor(s.my_score || 0) }" />
                  </div>
                  <div class="scenario-row__tip muted">
                    <template v-if="s.my_score !== null">
                      练习 {{ s.practice_count }} 次
                      <template v-if="s.team_avg !== null">
                        · 团队均分 {{ s.team_avg }}
                        <span v-if="s.gap !== null" :class="['gap', s.gap >= 0 ? 'gap--up' : 'gap--down']">
                          {{ s.gap >= 0 ? '领先' : '落后' }} <b>{{ s.gap >= 0 ? '+' : '' }}{{ s.gap }}</b>
                        </span>
                      </template>
                    </template>
                    <template v-else>该场景尚未练习</template>
                  </div>
                </div>
              </div>
            </div>
          </template>
        </template>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script>
import API from '@/api'
import PageHeader from '@/components/PageHeader/index.vue'

const DIFFICULTY_LABELS = { 1: '简单', 2: '中等', 3: '困难', 4: '专家' }
const DIFFICULTY_TAGS = { 1: 'success', 2: 'info', 3: 'warning', 4: 'danger' }

export default {
  name: 'TrainingLeaderboard',
  components: { PageHeader },
  data() {
    return {
      activeTab: 'team',
      viewer: { is_staff: 0, is_group_manager: 0, id: 0 },
      groups: [],
      employees: [],

      // 团队(已去除时间筛选,后端走全部时间)
      teamFilter: { group_id: '' },
      teamData: null,
      insightTab: 'scenario',  // 'weak' / 'scenario'

      // 个人(已去除时间筛选)
      personalFilter: { user_id: null },
      personal: null
    }
  },
  computed: {
    groupMap() {
      const m = {}
      this.groups.forEach(g => { m[g.id] = g.name })
      return m
    },
    rangeLabel() { return '' },
    filterTipText() { return '全部时间' },
    teamStats() {
      const t = this.teamData || { ranks: [], unfinished: [] }
      const ranked = t.ranks.length
      const unfinishedActive = t.unfinished.filter(u => (u.practice_count || 0) > 0).length
      const unfinishedAll = t.unfinished.length
      const participants = ranked + unfinishedActive
      const teamAvg = ranked > 0
        ? Math.round((t.ranks.reduce((acc, r) => acc + (Number(r.avg_score) || 0), 0) / ranked) * 10) / 10
        : null
      return { participants, ranked, unfinishedActive, unfinishedAll, teamAvg }
    },
    unfinishedSplit() {
      const all = (this.teamData && this.teamData.unfinished) || []
      const inProgress = all.filter(u => (u.practice_count || 0) > 0)
      const notStarted = all.filter(u => (u.practice_count || 0) === 0)
      return { all, inProgress, notStarted }
    },
    canViewTeam() {
      // 管理员（is_staff=0）+ 组长（is_group_manager=1）可看团队视图，普通坐席不可
      return !this.viewer.is_staff || !!this.viewer.is_group_manager
    },
    canFilterGroup() {
      // 仅管理员展示分组筛选；组长视图已固定本组，无需切换
      return !this.viewer.is_staff
    },
    canSelectEmployee() {
      // 普通员工只能查看自己；管理员/组长可切换员工做辅导复盘。
      return !this.viewer.is_staff || !!this.viewer.is_group_manager
    },
    weakestDimensionId() {
      const dims = (this.personal && this.personal.ability_profile) || []
      if (dims.length === 0) return null
      let min = dims[0]
      dims.forEach(d => { if (d.avg_score < min.avg_score) min = d })
      return min.dimension_id
    }
  },
  async created() {
    this.loadGroups()
    await this.loadEmployees()
    if (this.canViewTeam) {
      this.activeTab = 'team'
      this.loadTeam()
    } else {
      // 普通坐席：默认落到个人视图
      this.activeTab = 'personal'
      this.loadPersonal()
    }
  },
  methods: {
    difficultyLabel(d) { return DIFFICULTY_LABELS[d] || '-' },
    difficultyTag(d) { return DIFFICULTY_TAGS[d] || '' },
    scoreColor(score) {
      score = Number(score) || 0
      if (score >= 80) return '#16a34a'
      if (score >= 70) return '#f59e0b'
      return '#dc2626'
    },

    async loadGroups() {
      const res = await API.trainingGroupList()
      this.groups = res.data || []
    },
    async loadEmployees() {
      const res = await API.trainingEmployeeList()
      const data = res.data || {}
      this.employees = data.list || []
      this.viewer = data.viewer || { is_staff: 1, is_group_manager: 0, id: 0 }
      // 默认选中当前登录人；管理员/组长第一次进入也是看自己
      if (!this.personalFilter.user_id) {
        const selfId = Number(this.viewer.id) || 0
        if (selfId && this.employees.some(e => Number(e.id) === selfId)) {
          this.personalFilter.user_id = selfId
        } else if (this.employees.length > 0) {
          this.personalFilter.user_id = this.employees[0].id
        }
      }
    },
    async loadTeam() {
      const res = await API.trainingLeaderboardTeam(this.teamFilter)
      this.teamData = res.data || { ranks: [], unfinished: [], weak_dimensions: [], scenario_avg: [], required_total: 0 }
    },
    async loadPersonal() {
      const params = { ...this.personalFilter }
      const res = await API.trainingLeaderboardPersonal(params)
      this.personal = res.data || null
      // 追加调用:把"不同场景训练数据"的 team_avg 替换为与团队视图同口径的均分
      await this.overrideScenarioTeamAvg()
    },
    async overrideScenarioTeamAvg() {
      if (!this.personal || !this.personal.scenario_stats || !this.personal.scenario_stats.length) return
      try {
        // 传被查看员工 user_id,后端按该员工的 group_id 算分组均分
        const uid = this.personal.user && this.personal.user.id
        const res = await API.trainingScenarioTeamAvg({ user_id: uid })
        const map = res.data || {}
        const newStats = this.personal.scenario_stats.map(s => {
          const newAvg = map[String(s.scenario_id)]
          const teamAvg = (newAvg !== undefined && newAvg !== null) ? Number(newAvg) : null
          const gap = (s.my_score !== null && s.my_score !== undefined && teamAvg !== null)
            ? Math.round((Number(s.my_score) - teamAvg) * 10) / 10
            : null
          return { ...s, team_avg: teamAvg, gap }
        })
        // 用 $set 强制触发响应式,避免直接赋值在某些情况下视图不刷新
        this.$set(this.personal, 'scenario_stats', newStats)
      } catch (e) { /* 忽略,保留原值 */ }
    },
    onTabChange(tab) {
      if (tab.name === 'personal' && !this.personal) {
        this.loadPersonal()
      }
    },
    avatarColor(name) {
      const colors = ['indigo', 'pink', 'green', 'orange', 'cyan', 'rose']
      const code = (name || '?').charCodeAt(0) || 0
      return colors[code % colors.length]
    },
    progressColor(ratio) {
      const v = Number(ratio) || 0
      if (v >= 0.7) return 'linear-gradient(90deg, #6366f1, #9333ea)'
      if (v >= 0.5) return '#ea580c'
      if (v > 0) return '#dc2626'
      return '#d1d5db'
    },
    scoreLevel(score) {
      const v = Number(score) || 0
      if (v >= 80) return 'score-level--good'
      if (v >= 70) return 'score-level--mid'
      return 'score-level--low'
    },
    barColor(score) {
      const v = Number(score) || 0
      if (v >= 80) return '#16a34a'
      if (v >= 70) return '#f59e0b'
      if (v > 0) return '#dc2626'
      return '#e5e7eb'
    },
    weekNum(date) {
      const start = new Date(date.getFullYear(), 0, 1)
      return Math.ceil(((date - start) / 86400000 + start.getDay() + 1) / 7)
    }
  }
}
</script>

<style lang="scss" scoped>
.training-leaderboard-page { padding: 16px 20px 24px; }
.board-tabs { margin-top: 8px; }

// 顶部筛选
.filter-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: 10px 16px;
  margin-bottom: 14px;
}
.filter-left { display: flex; align-items: center; gap: 8px; }
.filter-label { font-size: 12px; color: #6b7280; margin-left: 8px; &:first-child { margin-left: 0; } }
.filter-select { width: 140px; }
.filter-select.wide { width: 200px; }
.filter-tip { font-size: 12px; }

// 4 张统计卡
.stat-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 14px;
}
.stat-card {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: 16px 18px;
  &__label {
    font-size: 13px;
    color: #6b7280;
    display: flex;
    align-items: center;
    gap: 4px;
  }
  &__value {
    font-size: 30px;
    font-weight: 700;
    color: #111827;
    line-height: 1.2;
    margin: 8px 0 6px;
    &--neutral { color: #111827; }
    &--warn { color: #f59e0b; }
  }
  &__hint { font-size: 12px; color: #9ca3af; &--warn { color: #f59e0b; } }
}

// 卡片
.card {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: 16px 20px;
  margin-bottom: 12px;
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}
.card-title-wrap { display: flex; align-items: center; gap: 4px; }
.card-title { font-size: 15px; font-weight: 600; color: #111827; }

.muted { color: #9ca3af; }
.small { font-size: 12px; }
.ml-6 { margin-left: 6px; }
.ml-8 { margin-left: 8px; }
.mt-8 { margin-top: 8px; }
.empty { padding: 36px 0; text-align: center; color: #9ca3af; font-size: 13px; }
.icon-help { color: #9ca3af; cursor: help; font-size: 13px; }

// mini Tab（卡片右上角）
.mini-tabs {
  display: flex;
  background: #f3f4f6;
  border-radius: 6px;
  padding: 2px;
  font-size: 12px;
}
.mini-tab {
  padding: 4px 12px;
  cursor: pointer;
  color: #6b7280;
  border-radius: 4px;
  user-select: none;
  &.active { background: #fff; color: #111827; font-weight: 500; box-shadow: 0 1px 2px rgba(0,0,0,0.06); }
}

// 团队主区双列
.team-main-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

// 排行榜行
.rank-row {
  display: grid;
  grid-template-columns: 32px 36px 1fr auto auto;
  align-items: center;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid #f3f4f6;
  &:last-child { border-bottom: 0; }
}
.rank-badge {
  width: 26px;
  height: 26px;
  border-radius: 6px;
  display: grid;
  place-items: center;
  font-weight: 700;
  font-size: 13px;
  color: #fff;
  &--1 { background: linear-gradient(135deg, #fbbf24, #f59e0b); }
  &--2 { background: linear-gradient(135deg, #d1d5db, #9ca3af); }
  &--3 { background: linear-gradient(135deg, #fdba74, #fb923c); }
  &--default { background: #e5e7eb; color: #6b7280; }
}
.rank-avatar {
  width: 36px; height: 36px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  color: #fff;
  font-weight: 600;
  font-size: 14px;
  &--indigo { background: #6366f1; }
  &--pink   { background: #ec4899; }
  &--green  { background: #16a34a; }
  &--orange { background: #f59e0b; }
  &--cyan   { background: #06b6d4; }
  &--rose   { background: #be185d; }
}
.rank-info { min-width: 0; overflow: hidden; }
.rank-name {
  font-weight: 600;
  color: #111827;
  font-size: 14px;
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.rank-group {
  font-size: 12px;
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.rank-score { font-weight: 700; color: #6366f1; font-size: 20px; min-width: 64px; text-align: right; }
.rank-count { font-size: 12px; min-width: 50px; text-align: right; }

// 团队洞察行
.insight-desc { margin: -8px 0 12px; }
.insight-row {
  margin-bottom: 14px;
  &:last-child { margin-bottom: 0; }
  &__head {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 4px;
  }
  &__tip { font-size: 12px; color: #9ca3af; margin-top: 4px; }
  .insight-name { font-size: 14px; color: #111827; font-weight: 600; }
  .insight-score {
    margin-left: auto;
    font-weight: 700;
    color: #16a34a;
    font-size: 16px;
    &--alert { color: #f59e0b; }
  }
}
.insight-bar {
  width: 100%;
  height: 8px;
  background: #f3f4f6;
  border-radius: 4px;
  overflow: hidden;
  &__fill { height: 100%; border-radius: 4px; transition: width 0.3s; }
}

.difficulty-tag {
  display: inline-block;
  padding: 1px 8px;
  font-size: 11px;
  border-radius: 4px;
  font-weight: 500;
  &--1 { background: #dbeafe; color: #2563eb; }
  &--2 { background: #e0f2fe; color: #0891b2; }
  &--3 { background: #fef3c7; color: #b45309; }
  &--4 { background: #fee2e2; color: #b91c1c; }
}

// 未完成名单
.unfinished-group-head {
  font-size: 12px;
  color: #9ca3af;
  background: #f9fafb;
  padding: 6px 12px;
  border-radius: 4px;
  margin: 14px 0 4px;
  &::before {
    content: '·';
    margin-right: 6px;
    color: #9ca3af;
    font-weight: 700;
  }
  &:first-child { margin-top: 0; }
}
.unfinished-row {
  display: grid;
  grid-template-columns: 36px 130px 50px 1fr 100px 1.2fr;
  align-items: center;
  gap: 14px;
  padding: 10px 12px;
  border-bottom: 1px solid #f3f4f6;
  &:last-child { border-bottom: 0; }
  &--idle { opacity: 0.85; }
}
.unfinished-info { min-width: 0; line-height: 1.4; overflow: hidden; }
.unfinished-name {
  font-weight: 600;
  color: #111827;
  font-size: 14px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.unfinished-group {
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.unfinished-progress-text {
  font-size: 13px;
  font-weight: 600;
  color: #111827;
  text-align: center;
}
.unfinished-bar {
  height: 8px;
  background: #f3f4f6;
  border-radius: 4px;
  overflow: hidden;
  &__fill { height: 100%; border-radius: 4px; transition: width 0.3s; }
}
.unfinished-score {
  font-size: 12px;
  b { color: #374151; font-weight: 600; }
}
.unfinished-missing {
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

// 个人身份卡
.identity-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: 14px 18px;
  margin-bottom: 14px;
}
.identity-info { display: flex; align-items: center; gap: 14px; }
.identity-avatar {
  width: 44px; height: 44px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  color: #fff;
  font-weight: 600;
  font-size: 18px;
}
.identity-name { font-size: 16px; font-weight: 700; color: #111827; line-height: 1.4; }
.identity-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 2px;
  font-size: 12px;
}
.identity-group { color: #9ca3af; }
.identity-badge {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 4px;
  font-weight: 500;
  &--ranked { background: #dcfce7; color: #15803d; }
  &--partial { background: #fef3c7; color: #b45309; }
  &--unstart { background: #f3f4f6; color: #6b7280; }
}
.identity-filters {
  display: flex;
  align-items: center;
  gap: 8px;
  .filter-label { font-size: 12px; color: #9ca3af; margin-left: 6px; &:first-child { margin-left: 0; } }
}

.banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-radius: 8px;
  margin-bottom: 12px;
  font-size: 13px;
}
.banner-warn { background: #fff7ed; color: #c2410c; }
.empty-big {
  padding: 80px 0;
  text-align: center;
  color: #9ca3af;
  .empty-icon { font-size: 50px; margin-bottom: 14px; }
  .empty-title { font-size: 16px; color: #374151; font-weight: 600; margin-bottom: 6px; }
  .empty-desc { font-size: 13px; }
}

// 个人 4 张统计卡（带彩色圆形图标）
.p-stat-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 14px;
}
.p-stat {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: 16px 18px;
  display: flex;
  align-items: center;
  gap: 14px;
  &__icon {
    width: 40px; height: 40px;
    border-radius: 10px;
    display: grid;
    place-items: center;
    color: #fff;
    font-weight: 700;
    font-size: 16px;
    flex-shrink: 0;
    &--rank { background: #fef3c7; color: #b45309; }
    &--score { background: #dcfce7; color: #15803d; }
    &--practice { background: #ede9fe; color: #6d28d9; }
    &--streak { background: #ffedd5; color: #c2410c; }
  }
  &__body { line-height: 1.3; min-width: 0; }
  &__value {
    font-size: 28px;
    font-weight: 700;
    color: #111827;
  }
  &__unit { font-size: 14px; color: #9ca3af; margin-left: 2px; font-weight: 500; }
  &__label {
    font-size: 12px;
    color: #6b7280;
    margin-top: 2px;
    display: flex;
    align-items: center;
    gap: 4px;
  }
  &__chip {
    display: inline-block;
    padding: 0 6px;
    border-radius: 3px;
    font-size: 11px;
    &--ok { background: #dcfce7; color: #15803d; }
    &--warn { background: #fef3c7; color: #b45309; }
  }
}

// 双列：能力画像 + 场景训练
.dual-section {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.with-accent {
  // 装饰条已移除
}

// 能力画像行
.ability-row {
  margin-bottom: 14px;
  &:last-child { margin-bottom: 0; }
  &__head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    margin-bottom: 6px;
  }
  &__tip {
    font-size: 12px;
    color: #f59e0b;
    margin-top: 4px;
  }
  .ability-name { font-size: 14px; color: #111827; font-weight: 600; }
  .ability-score {
    font-weight: 700;
    font-size: 18px;
    &.score-level--good { color: #16a34a; }
    &.score-level--mid { color: #f59e0b; }
    &.score-level--low { color: #dc2626; }
  }
}
.ability-bar {
  height: 8px;
  background: #f3f4f6;
  border-radius: 4px;
  overflow: hidden;
  &__fill {
    height: 100%;
    border-radius: 4px;
    transition: width 0.3s;
  }
}

// 场景训练行
.scenario-row {
  margin-bottom: 14px;
  &:last-child { margin-bottom: 0; }
  &__head {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 6px;
  }
  &__tip { font-size: 12px; margin-top: 4px; }
  .scenario-name { font-size: 14px; color: #111827; font-weight: 600; }
  .scenario-score { font-weight: 700; color: #111827; font-size: 18px; margin-left: auto; }
  .gap {
    margin-left: 4px;
    b { font-weight: 700; }
    &--up { color: #16a34a; }
    &--down { color: #dc2626; }
  }
}
.difficulty-tag--required {
  background: #ede9fe;
  color: #7c3aed;
}
</style>
