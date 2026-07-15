<template>
  <el-dialog
    :visible.sync="innerVisible"
    :title="editId ? '编辑销售场景' : '新增销售场景'"
    width="760px"
    :close-on-click-modal="false"
    append-to-body
    @close="onClose"
  >
    <el-form ref="form" :model="form" :rules="rules" label-position="top" size="small" v-loading="loading" class="scenario-form">
      <div class="form-row form-row--2col">
        <el-form-item label="场景名称" prop="name">
          <el-input v-model="form.name" maxlength="60" show-word-limit placeholder="请输入场景名称" />
        </el-form-item>
        <el-form-item label="难度等级" prop="difficulty">
          <el-select v-model="form.difficulty" placeholder="选择难度" style="width:100%">
            <el-option label="简单" :value="1" />
            <el-option label="中等" :value="2" />
            <el-option label="困难" :value="3" />
            <el-option label="专家" :value="4" />
          </el-select>
        </el-form-item>
      </div>
      <el-form-item label="客户画像" prop="persona">
        <el-input v-model="form.persona" type="textarea" :rows="3" maxlength="500" show-word-limit
                  placeholder="客户身份、性格、需求、预算、抗拒点" />
      </el-form-item>
      <el-form-item label="场景描述" prop="scene_desc">
        <el-input v-model="form.scene_desc" type="textarea" :rows="3" maxlength="500" show-word-limit
                  placeholder="当前销售情境、目标、限制条件" />
      </el-form-item>
      <el-form-item label="客户开场白">
        <el-input v-model="form.opening_message" type="textarea" :rows="2" maxlength="500" show-word-limit
                  placeholder="选填。留空则由坐席主动开场" />
        <div class="opening-hint">
          <span class="hint-strong">填了</span> → AI 扮演客户先开口，坐席接住开始练习；
          <span class="hint-strong">不填</span> → 坐席先主动向客户开场（适合"新客接待 / 主动推介"型场景）。
        </div>
      </el-form-item>

      <el-form-item prop="dimension_config" class="dim-form-item">
        <template slot="label">
          <div class="dim-label-row">
            <span class="dim-label-text">评价维度与权重 <span class="required-star">*</span></span>
            <div class="dim-toolbar">
              <el-button size="mini" plain @click="dimPickerVisible = !dimPickerVisible">{{ dimPickerVisible ? '收起维度库' : '添加维度' }}</el-button>
              <el-button size="mini" plain :disabled="selectedDims.length === 0" @click="distributeEvenly">一键均分</el-button>
              <span class="dim-toolbar__count">已选 {{ selectedDims.length }} 项</span>
            </div>
          </div>
        </template>
        <div class="dim-block">

          <!-- 维度库面板（展开后） -->
          <div v-if="dimPickerVisible" class="dim-picker">
            <div class="dim-picker__head">
              <el-input v-model="dimSearch" size="mini" placeholder="搜索维度库" prefix-icon="el-icon-search" clearable class="dim-picker__search" />
              <span class="dim-picker__hint">仅展示已启用且未选择的维度，列表过长时在此区域内滚动</span>
            </div>
            <div class="dim-picker__list">
              <div v-for="dim in availableDims" :key="dim.id" class="dim-picker__item">
                <div class="dim-picker__info">
                  <div class="dim-picker__name">{{ dim.name }}</div>
                  <div class="dim-picker__desc">{{ dim.description }}</div>
                </div>
                <el-button size="mini" plain class="dim-picker__add-btn" @click="addDim(dim)">添加</el-button>
              </div>
              <div v-if="availableDims.length === 0" class="dim-picker__empty">暂无可添加的维度</div>
            </div>
          </div>

          <!-- 已选维度表格 -->
          <el-table :data="selectedDims" size="mini" border class="dim-table" empty-text="暂无已选维度">
            <el-table-column label="维度" prop="dimension_name" min-width="100" />
            <el-table-column label="评分标准" min-width="220" show-overflow-tooltip>
              <template slot-scope="{ row }">{{ getDimDesc(row.dimension_id) }}</template>
            </el-table-column>
            <el-table-column label="权重" width="200">
              <template slot-scope="{ row }">
                <div class="weight-cell">
                  <div class="weight-cell__bar">
                    <div class="weight-cell__bar-fill" :style="{ width: Math.min(100, Math.max(0, Number(row.weight) || 0)) + '%' }"></div>
                  </div>
                  <el-input v-model.number="row.weight" size="mini" maxlength="3" class="weight-cell__input"
                            @input="row.weight = onWeightInput(row.weight)">
                    <template slot="append">%</template>
                  </el-input>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="70" align="center">
              <template slot-scope="{ $index }">
                <el-button type="text" size="mini" class="danger-text" @click="removeDim($index)">移除</el-button>
              </template>
            </el-table-column>
          </el-table>

          <!-- 权重合计提示 -->
          <div :class="['dim-summary', totalWeight !== 100 ? 'dim-summary--error' : '']">
            <span class="dim-summary__text">权重合计必须等于 100%，否则不能保存场景。</span>
            <span class="dim-summary__sum">当前合计 {{ totalWeight }}%</span>
          </div>
        </div>
      </el-form-item>

      <div class="form-row form-row--2col">
        <el-form-item label="是否必练">
          <el-switch v-model="form.is_required" :active-value="1" :inactive-value="0" />
          <div class="switch-hint">必练场景影响排行榜入榜资格。</div>
        </el-form-item>
        <el-form-item label="启用状态">
          <el-switch v-model="form.status" :active-value="1" :inactive-value="0" />
          <div class="switch-hint">停用后坐席不可发起新练习。</div>
        </el-form-item>
      </div>
    </el-form>
    <div slot="footer" class="dialog-footer">
      <el-button size="small" @click="onClose">取消</el-button>
      <el-button size="small" type="primary" :loading="saving" :disabled="totalWeight !== 100" @click="onSubmit">确定</el-button>
    </div>
  </el-dialog>
</template>

<script>
import API from '@/api'

export default {
  name: 'ScenarioDialog',
  props: {
    visible: { type: Boolean, required: true },
    editId: { type: [Number, String], default: null },
    editRow: { type: Object, default: null },
    dimensions: { type: Array, default: () => [] }
  },
  data() {
    return {
      loading: false,
      saving: false,
      dimPickerVisible: false,
      dimSearch: '',
      form: {
        name: '',
        difficulty: 1,
        persona: '',
        scene_desc: '',
        opening_message: '',
        is_required: 0,
        status: 1
      },
      selectedDims: [],
      rules: {
        name: [{ required: true, message: '请输入场景名称', trigger: 'blur' }],
        difficulty: [{ required: true, message: '请选择难度等级', trigger: 'change' }],
        persona: [{ required: true, message: '请填写客户画像', trigger: 'blur' }],
        scene_desc: [{ required: true, message: '请填写场景描述', trigger: 'blur' }]
      }
    }
  },
  computed: {
    innerVisible: {
      get() { return this.visible },
      set(v) { this.$emit('update:visible', v) }
    },
    totalWeight() {
      return this.selectedDims.reduce((acc, d) => acc + (Number(d.weight) || 0), 0)
    },
    selectedIds() {
      return new Set(this.selectedDims.map(d => Number(d.dimension_id)))
    },
    availableDims() {
      const kw = (this.dimSearch || '').trim().toLowerCase()
      return this.dimensions.filter(d => {
        if (this.selectedIds.has(Number(d.id))) return false
        if (Number(d.status) !== 1) return false
        if (kw && !(d.name || '').toLowerCase().includes(kw)) return false
        return true
      })
    },
    dimMap() {
      const m = {}
      this.dimensions.forEach(d => { m[Number(d.id)] = d })
      return m
    }
  },
  created() {
    if (this.editId) this.loadDetail()
  },
  methods: {
    getDimDesc(id) {
      const d = this.dimMap[Number(id)]
      return d ? d.description : ''
    },
    async loadDetail() {
      this.loading = true
      try {
        const res = await API.trainingScenarioList({ page: 1, limit: 1, id: this.editId })
        // 列表接口不接受 id 参数，改为本地从父传入 / 全量查
        // 改用 scenarioList + 客户端筛选；项目中如有 detail 接口可替换
      } finally {
        this.loading = false
      }
      // 兜底：单独取一次列表中匹配项
      const res = await API.trainingScenarioList({ page: 1, limit: 100 })
      const data = res.data || {}
      const found = this.editRow || (data.list || []).find(r => Number(r.id) === Number(this.editId))
      if (found) {
        this.form = {
          name: found.name || '',
          difficulty: Number(found.difficulty) || 1,
          persona: found.persona || '',
          scene_desc: found.scene_desc || '',
          opening_message: found.opening_message || found.opening || '',
          is_required: Number(found.is_required) || 0,
          status: Number(found.status) || 1
        }
        this.selectedDims = (found.dimension_config || []).map(c => ({
          dimension_id: Number(c.dimension_id || c.id),
          dimension_name: c.dimension_name || c.name || '',
          weight: Number(c.weight) || 0
        })).filter(d => d.dimension_id)
      }
    },
    addDim(dim) {
      this.selectedDims.push({
        dimension_id: Number(dim.id),
        dimension_name: dim.name,
        weight: 0
      })
    },
    removeDim(idx) {
      this.selectedDims.splice(idx, 1)
    },
    onWeightInput(val) {
      // 只保留数字、最多 3 位、不超过 100
      let s = String(val == null ? '' : val).replace(/[^\d]/g, '').slice(0, 3)
      if (s === '') return ''
      let n = parseInt(s, 10)
      if (n > 100) n = 100
      return n
    },
    distributeEvenly() {
      const n = this.selectedDims.length
      if (n === 0) return
      const base = Math.floor(100 / n)
      const rest = 100 - base * n
      this.selectedDims.forEach((d, i) => {
        d.weight = base + (i < rest ? 1 : 0)
      })
    },
    onClose() {
      this.innerVisible = false
    },
    onSubmit() {
      this.$refs.form.validate(async valid => {
        if (!valid) return
        if (this.selectedDims.length === 0) {
          this.$message.warning('请至少选择 1 个评价维度')
          return
        }
        if (this.totalWeight !== 100) {
          this.$message.warning('评价维度权重合计必须为 100%')
          return
        }
        this.saving = true
        try {
          const payload = {
            ...this.form,
            opening: this.form.opening_message,
            // 用 JSON 字符串传，避免 Qs.stringify 把嵌套数组展开为 dimension_config[0][...]
            // 后端 Controller 已支持 string → json_decode
            dimension_config: JSON.stringify(this.selectedDims.map(d => ({
              id: d.dimension_id,
              dimension_id: d.dimension_id,
              dimension_name: d.dimension_name,
              weight: d.weight
            })))
          }
          if (this.editId) {
            await API.trainingScenarioEdit({ id: this.editId, ...payload })
          } else {
            await API.trainingScenarioAdd(payload)
          }
          this.$message.success('保存成功')
          this.$emit('success')
        } finally {
          this.saving = false
        }
      })
    }
  }
}
</script>

<style lang="scss" scoped>
.dim-block { width: 100%; }

// 顶部 label 布局
.scenario-form ::v-deep .el-form-item__label {
  font-weight: 600;
  color: #111827;
  padding: 0 0 6px;
  line-height: 1.4;
}
.scenario-form ::v-deep .el-form-item {
  margin-bottom: 16px;
}

// 两列同行
.form-row {
  display: grid;
  gap: 16px;
  &--2col { grid-template-columns: 1fr 1fr; }
  ::v-deep .el-form-item { margin-bottom: 16px; }
}

.opening-hint {
  margin-top: 6px;
  font-size: 12px;
  color: #6b7280;
  line-height: 1.6;
  .hint-strong { color: #4f46e5; font-weight: 600; }
}

.dim-form-item ::v-deep .el-form-item__label {
  width: 100%;
}
.dim-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
}
.dim-label-text {
  font-weight: 600;
  color: #111827;
  font-size: 14px;
}
.required-star { color: #f56c6c; margin-left: 2px; font-weight: 700; }

.dim-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  &__count {
    font-size: 12px;
    color: #4f46e5;
    background: #eef2ff;
    border-radius: 4px;
    padding: 2px 8px;
  }
}

.dim-picker {
  margin-bottom: 10px;
  border: 1px dashed #c7d2fe;
  border-radius: 6px;
  padding: 10px 12px;
  background: #fafaff;
  &__head {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 8px;
  }
  &__search { width: 220px; }
  &__hint { font-size: 12px; color: #9ca3af; }
  &__list {
    max-height: 200px;
    overflow-y: auto;
  }
  &__item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 6px 10px;
    background: #fff;
    border-radius: 4px;
    margin-bottom: 4px;
    &:last-child { margin-bottom: 0; }
  }
  &__info {
    flex: 1;
    min-width: 0;
    line-height: 1.4;
  }
  &__name { font-size: 13px; color: #111827; font-weight: 700; }
  &__desc {
    font-size: 12px;
    color: #6b7280;
    margin-top: 1px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  &__add-btn {
    flex-shrink: 0;
    width: 56px;
    padding-left: 0;
    padding-right: 0;
  }
  &__empty {
    padding: 18px;
    text-align: center;
    color: #9ca3af;
    font-size: 12px;
  }
}

.dim-table ::v-deep .el-table__empty-block { min-height: 60px; }

.weight-cell {
  display: flex;
  align-items: center;
  gap: 10px;
  &__bar {
    flex: 1;
    min-width: 60px;
    height: 6px;
    background: #e5e7eb;
    border-radius: 3px;
    overflow: hidden;
  }
  &__bar-fill {
    height: 100%;
    background: linear-gradient(90deg, #6366f1, #9333ea);
    border-radius: 3px;
    transition: width 0.2s;
  }
  &__input { width: 80px; flex-shrink: 0; }
  &__input ::v-deep .el-input__inner { padding: 0 4px; text-align: center; }
  &__input ::v-deep .el-input-group__append { padding: 0 6px; }
}

.dim-summary {
  margin-top: 8px;
  padding: 8px 12px;
  background: #f0fdf4;
  border-radius: 6px;
  border: 1px solid #bbf7d0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  color: #16a34a;
  &__text { color: #15803d; }
  &__sum { font-weight: 600; }
  &--error {
    background: #fef2f2;
    border-color: #fecaca;
    color: #dc2626;
    .dim-summary__text { color: #dc2626; }
    .dim-summary__sum { color: #dc2626; }
  }
}

.hint {
  margin-left: 10px;
  font-size: 12px;
  color: #9ca3af;
}
.switch-hint {
  margin-top: 6px;
  font-size: 12px;
  color: #6b7280;
  line-height: 1.5;
}
.danger-text { color: #dc2626; }
</style>
