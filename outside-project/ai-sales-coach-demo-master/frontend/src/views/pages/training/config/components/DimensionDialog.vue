<template>
  <el-dialog
    :visible.sync="innerVisible"
    :title="editRow ? '编辑评价维度' : '新增评价维度'"
    width="520px"
    :close-on-click-modal="false"
    append-to-body
    @close="onClose"
  >
    <el-form ref="form" :model="form" :rules="rules" label-width="90px" size="small">
      <el-form-item label="维度名称" prop="name">
        <el-input v-model="form.name" maxlength="32" show-word-limit placeholder="如：专业度、亲和力" />
      </el-form-item>
      <el-form-item label="评分标准" prop="description">
        <el-input v-model="form.description" type="textarea" :rows="4" maxlength="500" show-word-limit
                  placeholder="描述 AI 对该维度的评分依据，如「头皮/发质讲解准确，不夸大功效」" />
      </el-form-item>
      <el-form-item label="启用状态">
        <el-switch v-model="form.status" :active-value="1" :inactive-value="0" />
        <span class="hint">停用后不可在新场景中选用，历史引用不受影响</span>
      </el-form-item>
    </el-form>
    <div slot="footer" class="dialog-footer">
      <el-button size="small" @click="onClose">取消</el-button>
      <el-button size="small" type="primary" :loading="saving" @click="onSubmit">确定</el-button>
    </div>
  </el-dialog>
</template>

<script>
import API from '@/api'

export default {
  name: 'DimensionDialog',
  props: {
    visible: { type: Boolean, required: true },
    editRow: { type: Object, default: null }
  },
  data() {
    return {
      saving: false,
      form: {
        name: this.editRow ? this.editRow.name : '',
        description: this.editRow ? this.editRow.description : '',
        status: this.editRow ? Number(this.editRow.status) : 1
      },
      rules: {
        name: [{ required: true, message: '请输入维度名称', trigger: 'blur' }],
        description: [{ required: true, message: '请输入评分标准', trigger: 'blur' }]
      }
    }
  },
  computed: {
    innerVisible: {
      get() { return this.visible },
      set(v) { this.$emit('update:visible', v) }
    }
  },
  methods: {
    onClose() {
      this.innerVisible = false
    },
    onSubmit() {
      this.$refs.form.validate(async valid => {
        if (!valid) return
        this.saving = true
        try {
          if (this.editRow) {
            await API.trainingDimensionEdit({ id: this.editRow.id, ...this.form })
          } else {
            await API.trainingDimensionAdd(this.form)
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
.hint {
  margin-left: 10px;
  font-size: 12px;
  color: #9ca3af;
}
</style>
