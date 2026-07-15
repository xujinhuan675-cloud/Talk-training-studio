<template>
  <div class="h5-leaderboard">
    <van-nav-bar title="排行榜" fixed safe-area-inset-top />
    <div class="nav-spacer" />

    <van-tabs v-model="activeTab" sticky offset-top="46px" color="#6366F1" line-width="24px" @change="onTabChange">
      <!-- ====== 团队视图 ====== -->
      <van-tab v-if="canViewTeam" title="团队" name="team">
        <div v-if="canFilterGroup && groups.length" class="group-row">
          <span :class="['chip', !teamFilter.group_id ? 'active' : '']" @click="setGroup('')">全部分组</span>
          <span v-for="g in groups" :key="g.id" :class="['chip', teamFilter.group_id === g.id ? 'active' : '']" @click="setGroup(g.id)">{{ g.name }}</span>
        </div>

        <div class="stat-grid">
          <div class="stat-mini">
            <div class="stat-mini__label">参与人数</div>
            <div class="stat-mini__value">{{ teamStats.participants }}</div>
          </div>
          <div class="stat-mini">
            <div class="stat-mini__label">达标入榜</div>
            <div class="stat-mini__value">{{ teamStats.ranked }}</div>
          </div>
          <div class="stat-mini">
            <div class="stat-mini__label">未完成</div>
            <div class="stat-mini__value warn">{{ teamStats.unfinishedActive }}</div>
          </div>
          <div class="stat-mini">
            <div class="stat-mini__label">团队均分</div>
            <div class="stat-mini__value">{{ teamStats.teamAvg !== null ? teamStats.teamAvg : '-' }}</div>
          </div>
        </div>

        <div class="h5-card">
          <div class="card-title">
            必练排行榜
            <span class="card-title__hint">仅必练 100% 入榜</span>
          </div>
          <div v-if="teamData && teamData.ranks.length === 0" class="empty">暂无符合入榜条件的坐席</div>
          <div v-for="(r, i) in (teamData && teamData.ranks) || []" :key="r.user_id" class="rank-row">
            <div :class="['rank-num', rankClass(i)]">{{ i + 1 }}</div>
            <span :class="['rank-avatar', `c-${avatarColor(r.user_name)}`]">{{ (r.user_name || '?').slice(0, 1) }}</span>
            <div class="rank-info">
              <div class="rank-name">{{ r.user_name }}</div>
              <div class="rank-sub">{{ groupMap[r.group_id] || '-' }} · {{ r.practice_count || 0 }} 次</div>
            </div>
            <div class="rank-score">{{ r.avg_score !== null && r.avg_score !== undefined ? r.avg_score : '-' }}</div>
          </div>
        </div>

        <div v-if="teamData && teamData.weak_dimensions && teamData.weak_dimensions.length" class="h5-card">
          <div class="card-title">薄弱维度</div>
          <div v-for="d in teamData.weak_dimensions.slice(0, 5)" :key="d.dimension_id" class="weak-row">
            <div class="weak-row__head">
              <span class="weak-name">{{ d.name }}</span>
              <span :class="['weak-score', d.is_weak ? 'alert' : '']">{{ d.avg_score }}</span>
            </div>
            <div class="bar"><div class="bar__fill" :style="{ width: Math.min(100, d.avg_score) + '%', background: d.is_weak ? '#F59E0B' : 'var(--h5-gradient)' }" /></div>
          </div>
        </div>

        <div v-if="unfinished.length" class="h5-card">
          <div class="card-title">未完成名单<span class="card-title__hint">{{ unfinished.length }} 人</span></div>
          <div v-for="u in unfinished.slice(0, 10)" :key="u.user_id" class="unfinished-row">
            <span :class="['rank-avatar', `c-${avatarColor(u.user_name)}`]">{{ (u.user_name || '?').slice(0, 1) }}</span>
            <div class="rank-info">
              <div class="rank-name">{{ u.user_name }}</div>
              <div class="rank-sub">{{ groupMap[u.group_id] || '-' }} · 完成 {{ u.required_finished }}/{{ u.required_total }}</div>
            </div>
            <div class="progress-mini">
              <div class="progress-mini__bar"><div class="progress-mini__fill" :style="{ width: Math.round((u.required_completion || 0) * 100) + '%' }" /></div>
            </div>
          </div>
        </div>
      </van-tab>

      <!-- ====== 个人视图 ====== -->
      <van-tab title="个人" name="personal">
        <template v-if="personal && personal.user">
          <!-- 身份卡 -->
          <div class="identity-hero">
            <div class="identity-info">
              <span :class="['identity-avatar', `c-${avatarColor(personal.user.name)}`]">{{ (personal.user.name || '?').slice(0, 1) }}</span>
              <div class="identity-text">
                <div class="identity-name">{{ personal.user.name }}</div>
                <div class="identity-meta">
                  <span class="identity-group">{{ groupMap[personal.user.group_id] || '-' }}</span>
                  <span :class="['identity-badge', `badge-${personal.status}`]">
                    <template v-if="personal.status === 'ranked'">已入榜 #{{ personal.rank || '-' }}</template>
                    <template v-else-if="personal.status === 'partial'">未入榜 {{ personal.required_finished }}/{{ personal.required_total }}</template>
                    <template v-else>未参与</template>
                  </span>
                </div>
              </div>
            </div>
            <div v-if="canSelectEmployee" class="employee-trigger" @click="showEmployeeSheet = true">
              切换 ▾
            </div>
          </div>

          <!-- 4 统计 -->
          <div class="stat-grid">
            <div class="stat-mini">
              <div class="stat-mini__label">我的排名</div>
              <div class="stat-mini__value">{{ personal.rank ? '#' + personal.rank : '—' }}</div>
            </div>
            <div class="stat-mini">
              <div class="stat-mini__label">平均分</div>
              <div class="stat-mini__value">{{ personal.avg_score !== null && personal.avg_score !== undefined ? personal.avg_score : '—' }}</div>
            </div>
            <div class="stat-mini">
              <div class="stat-mini__label">必练完成度</div>
              <div class="stat-mini__value">{{ personal.required_finished || 0 }}/{{ personal.required_total || 0 }}</div>
            </div>
            <div class="stat-mini">
              <div class="stat-mini__label">连续练习</div>
              <div class="stat-mini__value">{{ personal.streak_days || 0 }}<span class="stat-mini__unit">天</span></div>
            </div>
          </div>

          <!-- 部分完成提示 -->
          <div v-if="personal.status === 'partial'" class="banner-warn">
            还有 {{ personal.required_total - personal.required_finished }} 个必练场景未完成,完成后即可入榜
          </div>

          <!-- 能力画像(横向 bar 列表,跟 PC 同口径) -->
          <div v-if="personal.ability_profile && personal.ability_profile.length" class="h5-card">
            <div class="card-title">能力画像<span class="card-title__hint">按维度切片</span></div>
            <div v-for="d in personal.ability_profile" :key="d.dimension_id" class="ability-row">
              <div class="ability-row__head">
                <span class="ability-name">{{ d.name }}</span>
                <span :class="['ability-score', scoreLevel(d.avg_score)]">{{ d.avg_score }}</span>
              </div>
              <div class="bar">
                <div class="bar__fill" :style="{ width: Math.min(100, Number(d.avg_score) || 0) + '%', background: barColor(d.avg_score) }" />
              </div>
              <div v-if="weakestDimensionId === d.dimension_id" class="ability-row__tip">当前最低维度,建议加强</div>
            </div>
          </div>

          <!-- 场景训练数据 -->
          <div v-if="personal.scenario_stats && personal.scenario_stats.length" class="h5-card">
            <div class="card-title">场景训练数据</div>
            <div v-for="s in personal.scenario_stats" :key="s.scenario_id" class="scenario-row">
              <div class="scenario-row__head">
                <span class="scenario-name">{{ s.name }}</span>
                <span :class="['tag', `tag-diff-${s.difficulty}`]">{{ difficultyLabel(s.difficulty) }}</span>
                <span v-if="Number(s.is_required) === 1" class="tag tag-required-mini">必练</span>
                <span class="scenario-score">{{ s.my_score !== null && s.my_score !== undefined ? s.my_score : '—' }}</span>
              </div>
              <div class="bar">
                <div class="bar__fill" :style="{ width: Math.min(100, (s.my_score || 0)) + '%', background: barColor(s.my_score || 0) }" />
              </div>
              <div class="scenario-row__tip">
                <template v-if="s.my_score !== null && s.my_score !== undefined">
                  练 {{ s.practice_count }} 次
                  <template v-if="s.team_avg !== null && s.team_avg !== undefined">
                    · 团队均分 {{ s.team_avg }}
                    <span v-if="s.gap !== null && s.gap !== undefined" :class="['gap', s.gap >= 0 ? 'up' : 'down']">
                      {{ s.gap >= 0 ? '↑' : '↓' }}{{ Math.abs(s.gap) }}
                    </span>
                  </template>
                </template>
                <template v-else>该场景尚未练习</template>
              </div>
            </div>
          </div>

          <div v-if="personal.status === 'unstart'" class="empty-big">
            <div class="empty-icon">🎯</div>
            <div class="empty-title">本期暂无练习数据</div>
            <div class="empty-desc">完成一次练习后即可查看能力画像</div>
          </div>
        </template>
        <van-empty v-else-if="!personalLoading" description="暂无数据" />
      </van-tab>
    </van-tabs>

    <!-- 员工切换 sheet(管理员/组长可用) -->
    <van-popup v-model="showEmployeeSheet" position="bottom" round closeable>
      <div class="sheet">
        <div class="sheet__title">切换员工</div>
        <div class="employee-list">
          <div
            v-for="e in employees"
            :key="e.id"
            class="employee-row"
            :class="{ active: personalFilter.user_id === e.id }"
            @click="selectEmployee(e.id)"
          >
            <span :class="['rank-avatar', `c-${avatarColor(e.name)}`]">{{ (e.name || '?').slice(0, 1) }}</span>
            <div>
              <div class="employee-name">{{ e.name }}</div>
              <div class="employee-group">{{ groupMap[e.group_id] || '-' }}</div>
            </div>
            <van-icon v-if="personalFilter.user_id === e.id" name="success" color="#6366F1" />
          </div>
        </div>
      </div>
    </van-popup>
  </div>
</template>

<script>
import API from '@/api'

const DIFFICULTY_LABELS = { 1: '简单', 2: '中等', 3: '困难', 4: '专家' }

export default {
  name: 'H5Leaderboard',
  data() {
    return {
      activeTab: 'team',
      viewer: { is_staff: 1, is_group_manager: 0, id: 0 },
      groups: [],
      employees: [],
      teamFilter: { group_id: '' },
      personalFilter: { user_id: null },
      teamData: null,
      personal: null,
      personalLoading: false,
      showEmployeeSheet: false
    }
  },
  computed: {
    canViewTeam() { return !this.viewer.is_staff || !!this.viewer.is_group_manager },
    canFilterGroup() { return !this.viewer.is_staff },
    canSelectEmployee() { return this.canViewTeam && this.employees.length > 1 },
    groupMap() {
      const m = {}
      this.groups.forEach(g => { m[g.id] = g.name })
      return m
    },
    teamStats() {
      const t = this.teamData || { ranks: [], unfinished: [] }
      const ranked = t.ranks.length
      const unfinishedActive = t.unfinished.filter(u => (u.practice_count || 0) > 0).length
      const participants = ranked + unfinishedActive
      const teamAvg = ranked > 0
        ? Math.round((t.ranks.reduce((acc, r) => acc + (Number(r.avg_score) || 0), 0) / ranked) * 10) / 10
        : null
      return { participants, ranked, unfinishedActive, teamAvg }
    },
    unfinished() {
      return (this.teamData && this.teamData.unfinished) || []
    },
    weakestDimensionId() {
      const dims = (this.personal && this.personal.ability_profile) || []
      if (dims.length === 0) return null
      let min = dims[0]
      dims.forEach(d => { if (Number(d.avg_score) < Number(min.avg_score)) min = d })
      return min.dimension_id
    }
  },
  async created() {
    await Promise.all([this.loadGroups(), this.loadEmployees()])
    if (this.canViewTeam) {
      this.activeTab = 'team'
      await this.loadTeam()
    } else {
      this.activeTab = 'personal'
      await this.loadPersonal()
    }
  },
  methods: {
    difficultyLabel(d) { return DIFFICULTY_LABELS[d] || '-' },
    avatarColor(name) {
      const code = (name || '?').charCodeAt(0) || 0
      const colors = ['indigo', 'pink', 'green', 'orange', 'cyan', 'rose']
      return colors[code % colors.length]
    },
    rankClass(i) {
      if (i === 0) return 'r1'
      if (i === 1) return 'r2'
      if (i === 2) return 'r3'
      return 'normal'
    },
    barColor(s) {
      const v = Number(s) || 0
      if (v >= 80) return '#16A34A'
      if (v >= 70) return '#F59E0B'
      if (v > 0) return '#DC2626'
      return '#E5E7EB'
    },
    scoreLevel(s) {
      const v = Number(s) || 0
      if (v >= 80) return 'score-level--good'
      if (v >= 70) return 'score-level--mid'
      return 'score-level--low'
    },

    async loadGroups() {
      try {
        const res = await API.trainingGroupList()
        this.groups = res.data || []
      } catch (e) { /* 忽略 */ }
    },
    async loadEmployees() {
      try {
        const res = await API.trainingEmployeeList()
        this.employees = res.data || []
        this.viewer = res.viewer || { is_staff: 1, is_group_manager: 0, id: 0 }
        if (!this.personalFilter.user_id) {
          const selfId = Number(this.viewer.id) || 0
          if (selfId && this.employees.some(e => Number(e.id) === selfId)) {
            this.personalFilter.user_id = selfId
          } else if (this.employees.length > 0) {
            this.personalFilter.user_id = this.employees[0].id
          }
        }
      } catch (e) { /* 忽略 */ }
    },
    async loadTeam() {
      const res = await API.trainingLeaderboardTeam(this.teamFilter)
      this.teamData = res.data || { ranks: [], unfinished: [], weak_dimensions: [], scenario_avg: [] }
    },
    async loadPersonal() {
      this.personalLoading = true
      try {
        const params = { ...this.personalFilter }
        const res = await API.trainingLeaderboardPersonal(params)
        this.personal = res.data || null
        // 追加调用:把"不同场景训练数据"的 team_avg 替换为与团队视图同口径的均分
        await this.overrideScenarioTeamAvg()
      } finally {
        this.personalLoading = false
      }
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
        // 用 $set 强制触发响应式
        this.$set(this.personal, 'scenario_stats', newStats)
      } catch (e) { /* 失败时保留原 team_avg,不影响其他展示 */ }
    },
    onTabChange(name) {
      if (name === 'personal' && !this.personal) {
        this.loadPersonal()
      }
    },
    setGroup(g) {
      this.teamFilter.group_id = g
      this.loadTeam()
    },
    selectEmployee(uid) {
      this.personalFilter.user_id = uid
      this.showEmployeeSheet = false
      this.loadPersonal()
    }
  }
}
</script>

<style lang="scss" scoped>
.h5-leaderboard {
  min-height: 100vh;
  background: var(--h5-bg);
}
.nav-spacer { height: 46px; }

::v-deep .van-nav-bar { background: #fff; .van-nav-bar__title { font-weight: 600; } }
::v-deep .van-tabs__wrap { box-shadow: 0 1px 3px rgba(0,0,0,.03); }
::v-deep .van-tab { font-size: 14px; }
::v-deep .van-tab--active { font-weight: 600; }

.group-row {
  background: #fff;
  padding: 8px 12px;
  display: flex;
  gap: 8px;
  overflow-x: auto;
  border-bottom: 1px solid var(--h5-border);
  &::-webkit-scrollbar { display: none; }
}
.chip {
  flex-shrink: 0;
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

.stat-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  padding: 12px;
}
.stat-mini {
  background: #fff;
  border-radius: var(--h5-radius);
  padding: 12px;
  box-shadow: var(--h5-shadow);
  &__label { font-size: 12px; color: var(--h5-text-2); margin-bottom: 4px; }
  &__value {
    font-size: 22px;
    font-weight: 700;
    color: var(--h5-text-1);
    line-height: 1.2;
    &.warn { color: #DC2626; }
  }
  &__unit { font-size: 12px; color: var(--h5-text-3); margin-left: 2px; }
}

.h5-card {
  background: #fff;
  margin: 12px 12px 0;
  padding: 14px 16px;
  border-radius: var(--h5-radius);
  box-shadow: var(--h5-shadow);
}
.card-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--h5-text-1);
  margin-bottom: 10px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  &__hint {
    font-size: 11px;
    color: var(--h5-text-3);
    font-weight: 400;
  }
}

.rank-row {
  display: flex;
  align-items: center;
  padding: 10px 0;
  gap: 10px;
  border-bottom: 1px dashed #F3F4F6;
  &:last-child { border-bottom: 0; }
}
.rank-num {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  color: #fff;
  flex-shrink: 0;
  &.r1 { background: #F59E0B; }
  &.r2 { background: #94A3B8; }
  &.r3 { background: #B45309; }
  &.normal { background: transparent; color: var(--h5-text-3); }
}
.rank-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 600;
  color: #fff;
  flex-shrink: 0;
  &.c-indigo { background: #6366F1; }
  &.c-pink { background: #EC4899; }
  &.c-green { background: #10B981; }
  &.c-orange { background: #F97316; }
  &.c-cyan { background: #06B6D4; }
  &.c-rose { background: #F43F5E; }
}
.rank-info {
  flex: 1;
  min-width: 0;
}
.rank-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--h5-text-1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.rank-sub {
  font-size: 11px;
  color: var(--h5-text-3);
  margin-top: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.rank-score {
  font-size: 18px;
  font-weight: 700;
  color: var(--h5-primary);
  flex-shrink: 0;
  font-variant-numeric: tabular-nums;
}

.bar {
  height: 6px;
  background: #F3F4F6;
  border-radius: 3px;
  overflow: hidden;
  margin-top: 4px;
}
.bar__fill {
  height: 100%;
  border-radius: 3px;
  transition: width .4s ease;
}

.weak-row {
  padding: 8px 0;
}
.weak-row__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  .weak-name { color: var(--h5-text-2); }
  .weak-score { font-weight: 600; color: var(--h5-text-1); &.alert { color: #F59E0B; } }
}

.unfinished-row {
  display: flex;
  align-items: center;
  padding: 8px 0;
  gap: 10px;
  border-bottom: 1px dashed #F3F4F6;
  &:last-child { border-bottom: 0; }
}
.progress-mini {
  width: 64px;
  flex-shrink: 0;
  &__bar {
    height: 6px;
    background: #F3F4F6;
    border-radius: 3px;
    overflow: hidden;
  }
  &__fill {
    height: 100%;
    background: var(--h5-gradient);
    border-radius: 3px;
  }
}

/* 个人视图 */
.identity-hero {
  background: var(--h5-gradient);
  color: #fff;
  padding: 16px;
  margin: 12px 12px 0;
  border-radius: var(--h5-radius);
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.identity-info {
  display: flex;
  gap: 12px;
  align-items: center;
  flex: 1;
  min-width: 0;
}
.identity-avatar {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  background: rgba(255,255,255,.2);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  font-weight: 700;
  flex-shrink: 0;
}
.identity-text { min-width: 0; }
.identity-name {
  font-size: 17px;
  font-weight: 700;
  color: #fff;
  margin-bottom: 4px;
}
.identity-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: rgba(255,255,255,.85);
}
.identity-badge {
  background: rgba(255,255,255,.2);
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 11px;
  &.badge-ranked { background: rgba(255,255,255,.25); }
  &.badge-partial { background: rgba(245,158,11,.4); }
  &.badge-unstart { background: rgba(220,38,38,.3); }
}
.employee-trigger {
  flex-shrink: 0;
  background: rgba(255,255,255,.2);
  padding: 6px 10px;
  border-radius: 12px;
  font-size: 12px;
  color: #fff;
}

.banner-warn {
  background: #FEF3C7;
  color: #92400E;
  margin: 10px 12px 0;
  padding: 10px 14px;
  border-radius: var(--h5-radius-sm);
  font-size: 12px;
  line-height: 1.5;
}

/* 能力画像横向 bar 列表 */
.ability-row {
  padding: 10px 0;
  &:not(:last-child) { border-bottom: 1px dashed #F3F4F6; }
  &__head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    margin-bottom: 6px;
    .ability-name {
      font-size: 13px;
      color: var(--h5-text-2);
      font-weight: 500;
    }
    .ability-score {
      font-size: 16px;
      font-weight: 700;
      &.score-level--good { color: var(--h5-success); }
      &.score-level--mid { color: var(--h5-warning); }
      &.score-level--low { color: #DC2626; }
    }
  }
  &__tip {
    margin-top: 6px;
    font-size: 11px;
    color: #DC2626;
    background: #FEF2F2;
    padding: 4px 8px;
    border-radius: 4px;
    display: inline-block;
  }
}

.scenario-row {
  padding: 10px 0;
  border-bottom: 1px dashed #F3F4F6;
  &:last-child { border-bottom: 0; }
  &__head {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 4px;
    .scenario-name {
      flex: 1;
      min-width: 0;
      font-size: 13px;
      font-weight: 500;
      color: var(--h5-text-1);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .scenario-score {
      flex-shrink: 0;
      font-size: 16px;
      font-weight: 700;
      color: var(--h5-text-1);
      margin-left: auto;
    }
  }
  &__tip {
    font-size: 11px;
    color: var(--h5-text-3);
    margin-top: 4px;
    .gap {
      margin-left: 4px;
      font-weight: 600;
      &.up { color: var(--h5-success); }
      &.down { color: #DC2626; }
    }
  }
}
.tag {
  flex-shrink: 0;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 500;
  &.tag-diff-1 { background: #DCFCE7; color: #15803D; }
  &.tag-diff-2 { background: #DBEAFE; color: #1D4ED8; }
  &.tag-diff-3 { background: #FEF3C7; color: #B45309; }
  &.tag-diff-4 { background: #FEE2E2; color: #B91C1C; }
  &.tag-required-mini { background: #FFEDD5; color: #C2410C; }
}

.empty {
  padding: 20px 0;
  text-align: center;
  color: var(--h5-text-3);
  font-size: 13px;
}
.empty-big {
  text-align: center;
  padding: 40px 20px;
  .empty-icon { font-size: 40px; margin-bottom: 10px; }
  .empty-title { font-size: 15px; font-weight: 600; color: var(--h5-text-1); margin-bottom: 4px; }
  .empty-desc { font-size: 12px; color: var(--h5-text-3); }
}

.sheet {
  padding: 16px;
  &__title {
    text-align: center;
    font-size: 15px;
    font-weight: 600;
    color: var(--h5-text-1);
    margin-bottom: 8px;
    padding-bottom: 12px;
    border-bottom: 1px solid var(--h5-border);
  }
}
.sheet-row {
  padding: 14px 0;
  text-align: center;
  font-size: 15px;
  color: var(--h5-text-1);
  border-bottom: 1px solid #F3F4F6;
  &:last-child { border-bottom: 0; }
  &.active { color: var(--h5-primary); font-weight: 600; }
}
.employee-list {
  max-height: 50vh;
  overflow-y: auto;
  padding: 4px 0 calc(8px + env(safe-area-inset-bottom));
}
.employee-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 4px;
  border-bottom: 1px solid #F3F4F6;
  &:last-child { border-bottom: 0; }
  &.active { background: var(--h5-primary-soft); }
  .employee-name { font-size: 14px; color: var(--h5-text-1); font-weight: 500; }
  .employee-group { font-size: 11px; color: var(--h5-text-3); margin-top: 2px; }
}
</style>
