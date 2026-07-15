<template>
  <div class="training-config-page">
    <page-header title="陪练配置" desc="管理销售场景和评价维度，决定坐席闯关陪练的训练内容和评分标准" />

    <el-tabs v-model="activeTab" class="config-tabs">
      <!-- ====== 场景管理 ====== -->
      <el-tab-pane label="销售场景" name="scenario">
        <div class="action-row action-row--between">
          <h3 class="section-title">场景列表</h3>
          <div class="action-right">
            <el-select v-model="scenarioFilter.difficulty" size="small" clearable placeholder="全部难度" class="filter-select" @change="loadScenarios(1)">
              <el-option label="简单" :value="1" />
              <el-option label="中等" :value="2" />
              <el-option label="困难" :value="3" />
              <el-option label="专家" :value="4" />
            </el-select>
            <el-input
              v-model="scenarioFilter.keyword"
              size="small"
              placeholder="搜索场景"
              clearable
              class="search-input"
              @keyup.enter.native="loadScenarios(1)"
              @blur="loadScenarios(1)"
              @clear="loadScenarios(1)"
            />
            <el-button size="small" type="primary" @click="openScenarioDialog()">新增场景</el-button>
          </div>
        </div>

        <el-table :data="scenarioList" v-loading="scenarioLoading" border stripe size="small">
          <el-table-column label="场景名称" prop="name" min-width="160">
            <template slot-scope="{ row }">
              <span class="cell-name-bold">{{ row.name }}</span>
            </template>
          </el-table-column>
          <el-table-column label="难度" width="90">
            <template slot-scope="{ row }">
              <el-tag size="mini" :type="difficultyTag(row.difficulty)">{{ difficultyLabel(row.difficulty) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="客户画像" min-width="220" show-overflow-tooltip>
            <template slot-scope="{ row }">{{ row.persona || '-' }}</template>
          </el-table-column>
          <el-table-column label="评价维度" width="110">
            <template slot-scope="{ row }">
              <span>{{ (row.dimension_config || []).length }} 项</span>
            </template>
          </el-table-column>
          <el-table-column label="是否必练" width="90">
            <template slot-scope="{ row }">
              <el-tag v-if="row.is_required == 1" size="mini" type="warning">必练</el-tag>
              <el-tag v-else size="mini" type="info">非必练</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="启用状态" width="110">
            <template slot-scope="{ row }">
              <el-switch
                :value="row.status == 1"
                @change="onScenarioStatusChange(row, $event)"
              />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="140">
            <template slot-scope="{ row }">
              <el-button type="text" size="mini" @click="openScenarioDialog(row)">编辑</el-button>
              <el-button type="text" size="mini" class="danger-text" @click="onScenarioDelete(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <div class="pagination-wrap" v-if="scenarioTotal > scenarioPagination.limit">
          <el-pagination
            background layout="prev, pager, next"
            :total="scenarioTotal" :page-size="scenarioPagination.limit"
            :current-page.sync="scenarioPagination.page"
            @current-change="loadScenarios()"
          />
        </div>

        <scenario-dialog
          v-if="scenarioDialogVisible"
          :visible.sync="scenarioDialogVisible"
          :edit-id="editingScenarioId"
          :edit-row="editingScenario"
          :dimensions="enabledDimensions"
          @success="onScenarioSaved"
        />
      </el-tab-pane>

      <!-- ====== 评价维度库 ====== -->
      <el-tab-pane label="评价维度" name="dimension">
        <div class="action-row action-row--between">
          <h3 class="section-title">评价维度库</h3>
          <el-button size="small" type="primary" @click="openDimensionDialog()">新增维度</el-button>
        </div>

        <el-table :data="dimensionList" v-loading="dimensionLoading" border stripe size="small">
          <el-table-column label="维度名称" prop="name" min-width="160">
            <template slot-scope="{ row }">
              <span class="cell-name-bold">{{ row.name }}</span>
            </template>
          </el-table-column>
          <el-table-column label="评分标准" min-width="280" show-overflow-tooltip>
            <template slot-scope="{ row }">{{ row.description || '-' }}</template>
          </el-table-column>
          <el-table-column label="引用场景数" width="110">
            <template slot-scope="{ row }">{{ row.ref_count || 0 }}</template>
          </el-table-column>
          <el-table-column label="启用状态" width="110">
            <template slot-scope="{ row }">
              <el-switch :value="row.status == 1" @change="onDimensionStatusChange(row, $event)" />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="140">
            <template slot-scope="{ row }">
              <el-button type="text" size="mini" @click="openDimensionDialog(row)">编辑</el-button>
              <el-button type="text" size="mini" class="danger-text" @click="onDimensionDelete(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <div class="pagination-wrap" v-if="dimensionTotal > dimensionPagination.limit">
          <el-pagination
            background layout="prev, pager, next"
            :total="dimensionTotal" :page-size="dimensionPagination.limit"
            :current-page.sync="dimensionPagination.page"
            @current-change="loadDimensions()"
          />
        </div>

        <dimension-dialog
          v-if="dimensionDialogVisible"
          :visible.sync="dimensionDialogVisible"
          :edit-row="editingDimension"
          @success="onDimensionSaved"
        />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script>
import API from '@/api'
import PageHeader from '@/components/PageHeader/index.vue'
import ScenarioDialog from './components/ScenarioDialog.vue'
import DimensionDialog from './components/DimensionDialog.vue'

const DIFFICULTY_LABELS = { 1: '简单', 2: '中等', 3: '困难', 4: '专家' }
const DIFFICULTY_TAGS = { 1: 'success', 2: 'info', 3: 'warning', 4: 'danger' }

export default {
  name: 'TrainingConfig',
  components: { PageHeader, ScenarioDialog, DimensionDialog },
  data() {
    return {
      activeTab: 'scenario',

      // 场景
      scenarioList: [],
      scenarioTotal: 0,
      scenarioLoading: false,
      scenarioFilter: { keyword: '', difficulty: '', is_required: '' },
      scenarioPagination: { page: 1, limit: 20 },
      scenarioDialogVisible: false,
      editingScenarioId: null,
      editingScenario: null,
      enabledDimensions: [],

      // 维度
      dimensionList: [],
      dimensionTotal: 0,
      dimensionLoading: false,
      dimensionPagination: { page: 1, limit: 20 },
      dimensionDialogVisible: false,
      editingDimension: null
    }
  },
  created() {
    this.loadScenarios()
    this.loadEnabledDimensions()
    this.loadDimensions()
  },
  methods: {
    difficultyLabel(d) { return DIFFICULTY_LABELS[d] || '-' },
    difficultyTag(d) { return DIFFICULTY_TAGS[d] || '' },

    async loadScenarios(page) {
      this.scenarioLoading = true
      if (page) this.scenarioPagination.page = page
      try {
        const res = await API.trainingScenarioList({
          page: this.scenarioPagination.page,
          limit: this.scenarioPagination.limit,
          keyword: this.scenarioFilter.keyword,
          difficulty: this.scenarioFilter.difficulty,
          is_required: this.scenarioFilter.is_required
        })
        const data = res.data || {}
        this.scenarioList = data.list || []
        this.scenarioTotal = data.total || 0
      } finally {
        this.scenarioLoading = false
      }
    },

    async loadEnabledDimensions() {
      const res = await API.trainingDimensionList({ status: 1, page: 1, limit: 200 })
      const data = res.data || {}
      this.enabledDimensions = (data.list || []).filter(d => Number(d.status) === 1)
    },

    openScenarioDialog(row) {
      this.editingScenarioId = row ? row.id : null
      this.editingScenario = row ? { ...row } : null
      this.scenarioDialogVisible = true
    },

    async onScenarioStatusChange(row, val) {
      try {
        await API.trainingScenarioStatus({ id: row.id, status: val ? 1 : 0 })
        row.status = val ? 1 : 0
        this.$message.success('操作成功')
      } catch (e) {
        // 拦截器已弹窗
      }
    },

    async onScenarioDelete(row) {
      try {
        await this.$confirm(`确认删除场景「${row.name}」？已有练习记录将保留，但坐席无法再发起新练习。`, '删除场景', { type: 'warning' })
        await API.trainingScenarioDelete({ id: row.id })
        this.$message.success('已删除')
        this.loadScenarios()
      } catch (e) {
        if (e !== 'cancel') {/* 接口失败由拦截器处理 */}
      }
    },

    onScenarioSaved() {
      this.scenarioDialogVisible = false
      this.loadScenarios()
      this.loadEnabledDimensions()
    },

    async loadDimensions(page) {
      this.dimensionLoading = true
      if (page) this.dimensionPagination.page = page
      try {
        const res = await API.trainingDimensionList({
          page: this.dimensionPagination.page,
          limit: this.dimensionPagination.limit
        })
        const data = res.data || {}
        this.dimensionList = data.list || []
        this.dimensionTotal = data.total || 0
      } finally {
        this.dimensionLoading = false
      }
    },

    openDimensionDialog(row) {
      this.editingDimension = row ? { ...row } : null
      this.dimensionDialogVisible = true
    },

    async onDimensionStatusChange(row, val) {
      try {
        await API.trainingDimensionStatus({ id: row.id, status: val ? 1 : 0 })
        row.status = val ? 1 : 0
        this.$message.success('操作成功')
        this.loadEnabledDimensions()
      } catch (e) {}
    },

    async onDimensionDelete(row) {
      try {
        await this.$confirm(`确认删除维度「${row.name}」？被启用场景引用的维度不可删除。`, '删除维度', { type: 'warning' })
        await API.trainingDimensionDelete({ id: row.id })
        this.$message.success('已删除')
        this.loadDimensions()
        this.loadEnabledDimensions()
      } catch (e) {
        if (e !== 'cancel') {/* 接口失败由拦截器处理 */}
      }
    },

    onDimensionSaved() {
      this.dimensionDialogVisible = false
      this.loadDimensions()
      this.loadEnabledDimensions()
    }
  }
}
</script>

<style lang="scss" scoped>
.training-config-page {
  padding: 16px 20px 24px;
}
.config-tabs {
  margin-top: 8px;
}
.action-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
  &--right { justify-content: flex-end; }
  &--between { justify-content: space-between; }
}
.action-right {
  display: flex;
  align-items: center;
  gap: 10px;
}
.section-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: #111827;
}
.search-input { width: 240px; }
.filter-select { width: 140px; }
.muted { color: #9ca3af; }
.danger-text { color: #dc2626; }
.cell-name-bold { font-weight: 600; color: #111827; }
.pagination-wrap {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
</style>
