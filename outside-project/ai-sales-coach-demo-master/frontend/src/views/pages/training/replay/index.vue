<template>
  <div class="page-container replay-page">
    <page-header title="实战回放" desc="审查AI真实回复质量，持续优化"></page-header>

    <!-- 统计卡片 -->
    <div class="ds-stat-grid ds-stat-grid--4">
      <div class="ds-stat-card">
        <div class="ds-stat-icon ds-stat-icon--orange">
          <i class="el-icon-document-checked"></i>
        </div>
        <div class="ds-stat-info">
          <div class="ds-stat-value">{{ stats.pendingCount }}</div>
          <div class="ds-stat-label">今日待审</div>
        </div>
      </div>
      <div class="ds-stat-card">
        <div class="ds-stat-icon ds-stat-icon--green">
          <i class="el-icon-circle-check"></i>
        </div>
        <div class="ds-stat-info">
          <div class="ds-stat-value">{{ stats.reviewedCount }}</div>
          <div class="ds-stat-label">已审核</div>
        </div>
      </div>
      <div class="ds-stat-card">
        <div class="ds-stat-icon ds-stat-icon--purple">
          <i class="el-icon-data-analysis"></i>
        </div>
        <div class="ds-stat-info">
          <div class="ds-stat-value">{{ stats.accuracy }}%</div>
          <div class="ds-stat-label">AI正确率</div>
        </div>
      </div>
      <div class="ds-stat-card">
        <div class="ds-stat-icon ds-stat-icon--blue">
          <i class="el-icon-s-data"></i>
        </div>
        <div class="ds-stat-info">
          <div class="ds-stat-value">{{ stats.totalCount }}</div>
          <div class="ds-stat-label">总记录</div>
        </div>
      </div>
    </div>

    <!-- Tabs -->
    <div class="ds-card">
      <el-tabs v-model="activeTab" class="replay-tabs">
        <!-- Tab 1: 待审核 -->
        <el-tab-pane label="待审核" name="pending">
          <template slot="label">
            <span>待审核</span>
            <span class="tab-badge tab-badge--orange">{{ pendingItems.length }}</span>
          </template>
          <div class="replay-list">
            <div
              v-for="item in pendingItems"
              :key="item.id"
              class="replay-card"
              :class="{
                'replay-card--approved': item._feedback === 'approved',
                'replay-card--rejected': item._feedback === 'rejected'
              }"
            >
              <!-- 消息对话区 -->
              <div class="replay-card__conversation">
                <div class="chat-bubble chat-bubble--customer">
                  <div class="chat-bubble__label">
                    <i class="el-icon-user"></i> 客户消息
                  </div>
                  <div class="chat-bubble__text">{{ item.customer }}</div>
                </div>
                <div class="chat-bubble chat-bubble--ai">
                  <div class="chat-bubble__label">
                    <i class="el-icon-s-custom"></i> AI回复
                  </div>
                  <div class="chat-bubble__text">{{ item.aiReply }}</div>
                </div>
              </div>

              <!-- 底部信息 -->
              <div class="replay-card__footer">
                <span
                  class="source-badge"
                  :style="{
                    background: sourceConfig[item.source].bg,
                    color: sourceConfig[item.source].color
                  }"
                >
                  {{ sourceConfig[item.source].emoji }} {{ sourceConfig[item.source].label }}
                </span>

                <div class="replay-card__actions" v-if="item.status === 'pending' && !item._feedback">
                  <el-button
                    size="small"
                    class="btn-approve"
                    @click="handleApprove(item)"
                  >
                    <i class="el-icon-check"></i> 审核通过
                  </el-button>
                  <el-button
                    size="small"
                    class="btn-reject"
                    @click="handleReject(item)"
                  >
                    <i class="el-icon-close"></i> 驳回
                  </el-button>
                </div>

                <div class="replay-card__result" v-if="item._feedback">
                  <span
                    class="ds-badge"
                    :class="item._feedback === 'approved' ? 'ds-badge--green' : 'ds-badge--red'"
                  >
                    <i :class="item._feedback === 'approved' ? 'el-icon-check' : 'el-icon-close'"></i>
                    {{ item._feedback === 'approved' ? '已通过' : '已驳回' }}
                  </span>
                </div>
              </div>
            </div>

            <div class="ds-empty" v-if="pendingItems.length === 0">
              <i class="el-icon-document-checked"></i>
              <p>暂无待审核记录</p>
            </div>
          </div>
        </el-tab-pane>

        <!-- Tab 2: 已审核 -->
        <el-tab-pane label="已审核" name="reviewed">
          <template slot="label">
            <span>已审核</span>
            <span class="tab-badge tab-badge--green">{{ reviewedItems.length }}</span>
          </template>
          <div class="reviewed-list">
            <div
              v-for="item in reviewedItems"
              :key="item.id"
              class="reviewed-item"
            >
              <div class="reviewed-item__icon" :class="item.status === 'correct' ? 'is-correct' : 'is-incorrect'">
                <i :class="item.status === 'correct' ? 'el-icon-check' : 'el-icon-close'"></i>
              </div>
              <div class="reviewed-item__content">
                <div class="reviewed-item__customer">
                  <span class="reviewed-label">客户:</span>
                  {{ item.customer }}
                </div>
                <div class="reviewed-item__reply">
                  <span class="reviewed-label">AI:</span>
                  {{ item.aiReply }}
                </div>
              </div>
              <span
                class="source-badge source-badge--sm"
                :style="{
                  background: sourceConfig[item.source].bg,
                  color: sourceConfig[item.source].color
                }"
              >
                {{ sourceConfig[item.source].emoji }} {{ sourceConfig[item.source].label }}
              </span>
              <span
                class="ds-badge"
                :class="statusBadgeClass(item.status)"
              >
                {{ statusLabel(item.status) }}
              </span>
            </div>

            <div class="ds-empty" v-if="reviewedItems.length === 0">
              <i class="el-icon-finished"></i>
              <p>暂无已审核记录</p>
            </div>
          </div>
        </el-tab-pane>

        <!-- Tab 3: 统计面板 -->
        <el-tab-pane label="统计面板" name="stats">
          <div class="stats-panel">
            <!-- 第一行: 趋势图 + 饼图 -->
            <div class="stats-row">
              <div class="ds-card stats-chart-card stats-chart-card--wide">
                <div class="ds-card-header">
                  <span class="ds-card-title"><i class="el-icon-data-line"></i>AI回复质量趋势</span>
                  <span class="ds-badge ds-badge--purple">近30天</span>
                </div>
                <div class="chart-container" ref="trendChart"></div>
              </div>
              <div class="ds-card stats-chart-card stats-chart-card--narrow">
                <div class="ds-card-header">
                  <span class="ds-card-title"><i class="el-icon-pie-chart"></i>回复来源分布</span>
                </div>
                <div class="chart-container" ref="pieChart"></div>
              </div>
            </div>

            <!-- 第二行: 差评TOP5 -->
            <div class="ds-card stats-chart-card" style="margin-top: 16px;">
              <div class="ds-card-header">
                <span class="ds-card-title"><i class="el-icon-warning-outline"></i>差评TOP5原因</span>
                <span class="ds-badge ds-badge--red">需关注</span>
              </div>
              <div class="chart-container chart-container--bar" ref="barChart"></div>
            </div>
          </div>
        </el-tab-pane>
      </el-tabs>
    </div>
  </div>
</template>

<script>
export default {
  name: 'BattleReplay',
  data() {
    return {
      activeTab: 'pending',
      stats: {
        pendingCount: 12,
        reviewedCount: 156,
        accuracy: 87.5,
        totalCount: 168
      },
      sourceConfig: {
        rule: { label: '话术规则', emoji: '\uD83C\uDFAF', color: '#ef4444', bg: '#fef2f2' },
        script: { label: '话术库', emoji: '\uD83D\uDCDD', color: '#3b82f6', bg: '#eff6ff' },
        knowledge: { label: '知识库', emoji: '\uD83D\uDCDA', color: '#22c55e', bg: '#f0fdf4' },
        ai_gen: { label: 'AI生成', emoji: '\uD83E\uDD16', color: '#8b5cf6', bg: '#f5f3ff' }
      },
      replayItems: [
        { id: '1', customer: '请问你们的课程多少钱？', aiReply: '我们的课程价格根据年级不同有所区别，一对一小学200元/课时起，初中260元/课时起，高中320元/课时起。首次可免费试听一节课！', source: 'script', status: 'pending', _feedback: null },
        { id: '2', customer: '孩子数学才考了50分怎么办', aiReply: '别担心！50分说明基础知识还有提升空间。建议先做一个免费学情诊断，找到薄弱知识点，然后针对性辅导。我们有很多类似情况的学生，经过系统辅导成绩都有明显提升。', source: 'knowledge', status: 'pending', _feedback: null },
        { id: '3', customer: '你们和学而思比怎么样？', aiReply: '每家机构都有各自的特色。我们的优势在于：1）小班精品教学，每班不超过8人；2）老师全部985/211毕业；3）独家研发的AI学情分析系统。建议您可以带孩子来试听对比感受一下。', source: 'ai_gen', status: 'pending', _feedback: null },
        { id: '4', customer: '课程能退费吗', aiReply: '完全可以！我们承诺：首节课不满意全额退款，课程中途不满意剩余课时随时退，退款3个工作日内到账。', source: 'rule', status: 'pending', _feedback: null },
        { id: '5', customer: '我想了解下暑假班', aiReply: '暑假班现在正在火热报名中！我们推出了三种班型：基础巩固班、能力提升班和冲刺拔高班。早鸟报名还有85折优惠，名额有限哦~', source: 'script', status: 'pending', _feedback: null },
        { id: '6', customer: '能退费吗？', aiReply: '当然可以！我们有完善的退费保障机制，随时可以申请退费。', source: 'rule', status: 'correct', _feedback: null },
        { id: '7', customer: '老师是哪里毕业的？', aiReply: '我们的老师均来自985/211高校，平均教龄5年以上，每位老师都经过严格的6轮面试和3个月岗前培训。', source: 'knowledge', status: 'correct', _feedback: null },
        { id: '8', customer: '怎么收费的啊', aiReply: '我们按课时收费，不同年级价格不同。小学200元起，初中260元起，高中320元起。还有多课时优惠包可以选择。', source: 'script', status: 'incorrect', _feedback: null },
        { id: '9', customer: '孩子不愿意补课怎么办', aiReply: '这个很正常！很多孩子一开始都有抵触心理。我们的老师非常擅长引导孩子的学习兴趣，会通过趣味教学和游戏化互动让孩子爱上学习。可以先来体验一节课试试。', source: 'ai_gen', status: 'pending', _feedback: null },
        { id: '10', customer: '有线上课吗', aiReply: '有的！我们提供线上和线下两种模式，线上课通过专属教学平台授课，效果和线下一样好，还能节省通勤时间。', source: 'knowledge', status: 'pending', _feedback: null }
      ],
      // Chart instances
      trendChartInstance: null,
      pieChartInstance: null,
      barChartInstance: null
    }
  },
  computed: {
    pendingItems() {
      return this.replayItems.filter(item => item.status === 'pending')
    },
    reviewedItems() {
      return this.replayItems.filter(item => item.status !== 'pending')
    }
  },
  watch: {
    activeTab(val) {
      if (val === 'stats') {
        this.$nextTick(() => {
          this.renderAllCharts()
        })
      }
    }
  },
  mounted() {
    window.addEventListener('resize', this.handleResize)
  },
  beforeDestroy() {
    window.removeEventListener('resize', this.handleResize)
    this.disposeCharts()
  },
  methods: {
    // ---- 审核操作 ----
    handleApprove(item) {
      this.$set(item, '_feedback', 'approved')
      this.stats.pendingCount = Math.max(0, this.stats.pendingCount - 1)
      this.stats.reviewedCount++

      this.$message({ message: '已标记为通过', type: 'success' })

      setTimeout(() => {
        item.status = 'correct'
      }, 500)
    },
    handleReject(item) {
      this.$set(item, '_feedback', 'rejected')
      this.stats.pendingCount = Math.max(0, this.stats.pendingCount - 1)
      this.stats.reviewedCount++

      this.$message({ message: '已标记为驳回', type: 'warning' })

      setTimeout(() => {
        item.status = 'incorrect'
      }, 500)
    },

    // ---- 已审核状态 ----
    statusBadgeClass(status) {
      const map = {
        correct: 'ds-badge--green',
        incorrect: 'ds-badge--red',
        corrected: 'ds-badge--blue'
      }
      return map[status] || 'ds-badge--gray'
    },
    statusLabel(status) {
      const map = {
        correct: '正确',
        incorrect: '不正确',
        corrected: '已纠正'
      }
      return map[status] || status
    },

    // ---- ECharts ----
    renderAllCharts() {
      this.renderTrendChart()
      this.renderPieChart()
      this.renderBarChart()
    },

    renderTrendChart() {
      if (!this.$refs.trendChart) return
      const echarts = require('echarts')
      if (this.trendChartInstance) this.trendChartInstance.dispose()
      this.trendChartInstance = echarts.init(this.$refs.trendChart)

      // 生成30天日期和模拟数据
      const dates = []
      const data = []
      for (let i = 29; i >= 0; i--) {
        const d = new Date()
        d.setDate(d.getDate() - i)
        dates.push((d.getMonth() + 1) + '/' + d.getDate())
        data.push(+(75 + Math.random() * 20).toFixed(1))
      }

      this.trendChartInstance.setOption({
        tooltip: {
          trigger: 'axis',
          backgroundColor: '#1e293b',
          borderColor: '#334155',
          textStyle: { color: '#e2e8f0', fontSize: 12 },
          formatter: '{b}<br/>正确率: {c}%',
          axisPointer: { lineStyle: { color: '#94a3b8', type: 'dashed' } }
        },
        grid: {
          left: 52,
          right: 24,
          top: 24,
          bottom: 32
        },
        xAxis: {
          type: 'category',
          data: dates,
          axisLine: { lineStyle: { color: '#e5e7eb' } },
          axisTick: { show: false },
          axisLabel: { color: '#9ca3af', fontSize: 11, interval: 4 },
          boundaryGap: false
        },
        yAxis: {
          type: 'value',
          min: 70,
          max: 100,
          axisLine: { show: false },
          axisTick: { show: false },
          splitLine: { lineStyle: { color: '#f3f4f6' } },
          axisLabel: { color: '#9ca3af', fontSize: 11, formatter: '{value}%' }
        },
        series: [
          {
            name: 'AI正确率',
            type: 'line',
            data: data,
            smooth: true,
            symbol: 'circle',
            symbolSize: 6,
            showSymbol: false,
            lineStyle: { width: 2.5, color: '#8b5cf6' },
            itemStyle: { color: '#8b5cf6' },
            areaStyle: {
              color: {
                type: 'linear',
                x: 0, y: 0, x2: 0, y2: 1,
                colorStops: [
                  { offset: 0, color: 'rgba(139,92,246,0.2)' },
                  { offset: 1, color: 'rgba(139,92,246,0.01)' }
                ]
              }
            }
          }
        ]
      })
    },

    renderPieChart() {
      if (!this.$refs.pieChart) return
      const echarts = require('echarts')
      if (this.pieChartInstance) this.pieChartInstance.dispose()
      this.pieChartInstance = echarts.init(this.$refs.pieChart)

      this.pieChartInstance.setOption({
        tooltip: {
          trigger: 'item',
          backgroundColor: '#1e293b',
          borderColor: '#334155',
          textStyle: { color: '#e2e8f0', fontSize: 12 },
          formatter: '{b}: {c}% ({d}%)'
        },
        legend: {
          orient: 'vertical',
          right: 12,
          top: 'center',
          itemWidth: 10,
          itemHeight: 10,
          itemGap: 12,
          textStyle: { color: '#6b7280', fontSize: 12 }
        },
        series: [
          {
            type: 'pie',
            radius: ['45%', '72%'],
            center: ['38%', '50%'],
            avoidLabelOverlap: false,
            label: { show: false },
            emphasis: {
              label: { show: true, fontSize: 14, fontWeight: 'bold' },
              itemStyle: { shadowBlur: 10, shadowOffsetX: 0, shadowColor: 'rgba(0, 0, 0, 0.15)' }
            },
            labelLine: { show: false },
            data: [
              { value: 30, name: '话术规则', itemStyle: { color: '#ef4444' } },
              { value: 25, name: '话术库', itemStyle: { color: '#3b82f6' } },
              { value: 20, name: '知识库', itemStyle: { color: '#22c55e' } },
              { value: 25, name: 'AI生成', itemStyle: { color: '#8b5cf6' } }
            ]
          }
        ]
      })
    },

    renderBarChart() {
      if (!this.$refs.barChart) return
      const echarts = require('echarts')
      if (this.barChartInstance) this.barChartInstance.dispose()
      this.barChartInstance = echarts.init(this.$refs.barChart)

      const categories = ['信息错误', '过于生硬', '答非所问', '语气不当', '知识缺失']
      const values = [4, 6, 8, 12, 15]

      this.barChartInstance.setOption({
        tooltip: {
          trigger: 'axis',
          backgroundColor: '#1e293b',
          borderColor: '#334155',
          textStyle: { color: '#e2e8f0', fontSize: 12 },
          axisPointer: { type: 'shadow' }
        },
        grid: {
          left: 100,
          right: 40,
          top: 16,
          bottom: 16
        },
        xAxis: {
          type: 'value',
          axisLine: { show: false },
          axisTick: { show: false },
          splitLine: { lineStyle: { color: '#f3f4f6' } },
          axisLabel: { color: '#9ca3af', fontSize: 11 }
        },
        yAxis: {
          type: 'category',
          data: categories,
          axisLine: { show: false },
          axisTick: { show: false },
          axisLabel: { color: '#374151', fontSize: 13, fontWeight: 500 }
        },
        series: [
          {
            type: 'bar',
            data: values,
            barWidth: 22,
            itemStyle: {
              borderRadius: [0, 6, 6, 0],
              color: {
                type: 'linear',
                x: 0, y: 0, x2: 1, y2: 0,
                colorStops: [
                  { offset: 0, color: '#6366f1' },
                  { offset: 1, color: '#8b5cf6' }
                ]
              }
            },
            label: {
              show: true,
              position: 'right',
              color: '#6b7280',
              fontSize: 12,
              fontWeight: 600,
              formatter: '{c} 次'
            }
          }
        ]
      })
    },

    handleResize() {
      if (this.trendChartInstance) this.trendChartInstance.resize()
      if (this.pieChartInstance) this.pieChartInstance.resize()
      if (this.barChartInstance) this.barChartInstance.resize()
    },

    disposeCharts() {
      if (this.trendChartInstance) {
        this.trendChartInstance.dispose()
        this.trendChartInstance = null
      }
      if (this.pieChartInstance) {
        this.pieChartInstance.dispose()
        this.pieChartInstance = null
      }
      if (this.barChartInstance) {
        this.barChartInstance.dispose()
        this.barChartInstance = null
      }
    }
  }
}
</script>

<style lang="scss" scoped>
$indigo: #6366f1;
$purple: #8b5cf6;
$gray-50: #f9fafb;
$gray-100: #f3f4f6;
$gray-200: #e5e7eb;
$gray-400: #9ca3af;
$gray-500: #6b7280;
$gray-900: #111827;

// =============================================
// Tabs 样式覆盖
// =============================================
.replay-tabs {
  ::v-deep .el-tabs__header {
    margin: 0;
    padding: 0 20px;
    border-bottom: 1px solid $gray-100;
  }

  ::v-deep .el-tabs__nav-wrap::after {
    display: none;
  }

  ::v-deep .el-tabs__item {
    height: 48px;
    line-height: 48px;
    font-size: 14px;
    font-weight: 500;
    color: $gray-500;
    padding: 0 20px;

    &.is-active {
      color: $indigo;
      font-weight: 600;
    }

    &:hover {
      color: $indigo;
    }
  }

  ::v-deep .el-tabs__active-bar {
    background: linear-gradient(90deg, $indigo, $purple);
    height: 3px;
    border-radius: 3px 3px 0 0;
  }

  ::v-deep .el-tabs__content {
    padding: 20px;
  }
}

.tab-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  height: 18px;
  padding: 0 6px;
  border-radius: 9px;
  font-size: 11px;
  font-weight: 600;
  margin-left: 6px;
  line-height: 1;

  &--orange {
    background: #fff7ed;
    color: #ea580c;
  }

  &--green {
    background: #f0fdf4;
    color: #16a34a;
  }
}

// =============================================
// Tab 1: 待审核 - 卡片列表
// =============================================
.replay-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.replay-card {
  border: 1px solid $gray-100;
  border-radius: 12px;
  padding: 20px;
  background: #fff;
  transition: all 0.4s ease;

  &:hover {
    border-color: #e0e7ff;
    box-shadow: 0 2px 12px rgba(99, 102, 241, 0.06);
  }

  &--approved {
    background: #f0fdf4;
    border-color: #bbf7d0;
  }

  &--rejected {
    background: #fef2f2;
    border-color: #fecaca;
  }

  &__conversation {
    display: flex;
    flex-direction: column;
    gap: 12px;
    margin-bottom: 16px;
  }

  &__footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding-top: 14px;
    border-top: 1px solid $gray-100;
  }

  &__actions {
    display: flex;
    gap: 8px;
  }

  &__result {
    display: flex;
    align-items: center;

    .ds-badge i {
      margin-right: 4px;
    }
  }
}

// 聊天气泡
.chat-bubble {
  border-radius: 10px;
  padding: 12px 16px;

  &--customer {
    background: $gray-50;
    border: 1px solid $gray-100;
  }

  &--ai {
    background: #f5f3ff;
    border: 1px solid #ede9fe;
  }

  &__label {
    font-size: 12px;
    font-weight: 600;
    margin-bottom: 6px;
    display: flex;
    align-items: center;
    gap: 4px;

    .chat-bubble--customer & {
      color: $gray-500;
    }

    .chat-bubble--ai & {
      color: $purple;
    }
  }

  &__text {
    font-size: 14px;
    line-height: 1.7;
    color: $gray-900;
  }
}

// 来源标签
.source-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;

  &--sm {
    padding: 2px 8px;
    font-size: 11px;
  }
}

// 审核按钮
.btn-approve {
  background: #f0fdf4 !important;
  color: #16a34a !important;
  border: 1px solid #bbf7d0 !important;
  border-radius: 8px !important;
  font-weight: 500 !important;
  transition: all 0.2s !important;

  &:hover {
    background: #dcfce7 !important;
    border-color: #86efac !important;
    box-shadow: 0 2px 8px rgba(22, 163, 74, 0.15) !important;
  }

  i {
    margin-right: 2px;
  }
}

.btn-reject {
  background: #fff !important;
  color: #dc2626 !important;
  border: 1px solid #fecaca !important;
  border-radius: 8px !important;
  font-weight: 500 !important;
  transition: all 0.2s !important;

  &:hover {
    background: #fef2f2 !important;
    border-color: #fca5a5 !important;
    box-shadow: 0 2px 8px rgba(220, 38, 38, 0.12) !important;
  }

  i {
    margin-right: 2px;
  }
}

// =============================================
// Tab 2: 已审核列表
// =============================================
.reviewed-list {
  display: flex;
  flex-direction: column;
}

.reviewed-item {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px 0;
  border-bottom: 1px solid $gray-50;
  transition: background 0.2s;

  &:last-child {
    border-bottom: none;
  }

  &:hover {
    background: #fafbff;
    margin: 0 -20px;
    padding-left: 20px;
    padding-right: 20px;
  }

  &__icon {
    width: 32px;
    height: 32px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    font-size: 14px;

    &.is-correct {
      background: #dcfce7;
      color: #16a34a;
    }

    &.is-incorrect {
      background: #fee2e2;
      color: #dc2626;
    }
  }

  &__content {
    flex: 1;
    min-width: 0;
  }

  &__customer,
  &__reply {
    font-size: 13px;
    color: $gray-500;
    line-height: 1.5;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 520px;
  }

  &__customer {
    margin-bottom: 2px;
    color: $gray-900;
    font-weight: 500;
  }
}

.reviewed-label {
  font-size: 11px;
  color: $gray-400;
  font-weight: 600;
  margin-right: 4px;
}

// =============================================
// Tab 3: 统计面板
// =============================================
.stats-panel {
  padding: 0;
}

.stats-row {
  display: flex;
  gap: 16px;
}

.stats-chart-card {
  overflow: visible;

  &--wide {
    flex: 2;
  }

  &--narrow {
    flex: 1;
  }
}

.chart-container {
  width: 100%;
  height: 300px;
  padding: 12px;

  &--bar {
    height: 260px;
  }
}

// =============================================
// 响应式
// =============================================
@media (max-width: 1200px) {
  .stats-row {
    flex-direction: column;
  }
}
</style>
