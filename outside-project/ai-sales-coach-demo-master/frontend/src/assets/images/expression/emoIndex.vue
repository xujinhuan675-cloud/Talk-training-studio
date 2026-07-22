<template>
  <div class="expression-page">
    <el-popover width="400" trigger="click" placement="top">
      <div class="scroll" style="height: 210px; overflow-y: scroll">
        <!-- 动态绑定usemap，对应组件实例唯一的qqMap名称（带#前缀） -->
        <img class="qq-face emo_img" src="./qqface.png" :usemap="'#' + uniqueQqMapName" />
        <!-- 动态绑定map的name属性，确保全局唯一 -->
        <map :name="uniqueQqMapName">
          <area v-for="(expression, index) in 105" :key="index" shape="rect" :coords="(index % 15) * 25 +
            ', ' +
            parseInt(index / 15) * 25 +
            ', ' +
            ((index % 15) + 1) * 25 +
            ', ' +
            (parseInt(index / 15) + 1) * 25
            " :title="qqFaceMap[index] || index" @click="selectExpression(index)" />
        </map>
        <!-- 动态绑定usemap，对应组件实例唯一的emojiMap名称（带#前缀） -->
        <img class="emo_img" src="./emoji.png" :usemap="'#' + uniqueEmojiMapName" />
        <!-- 动态绑定map的name属性，确保全局唯一 -->
        <map :name="uniqueEmojiMapName">
          <area v-for="(emoji, index) in 177" :key="index" shape="rect" :coords="(index % 15) * 25 +
            ', ' +
            parseInt(index / 15) * 25 +
            ', ' +
            ((index % 15) + 1) * 25 +
            ', ' +
            (parseInt(index / 15) + 1) * 25
            " :title="qqFaceMap[105 + index]" @click="selectExpression(105 + index)" />
        </map>
      </div>
      <div slot="reference" class="expression-icon" title="表情">
        <img
          src="@/assets/images/emo_icon.png"
          class="emo_ico">
      </div>
    </el-popover>
  </div>
</template>

<script>
// 导入表情映射表
import { expressionMap, emojiMap } from '@/utils/qqFaceMap'

export default {
  // 修正组件名称，与功能匹配
  name: 'ExpressionSelector',
  // 规范Props定义，避免传递异常
  props: {
    parames: {
      type: [Object, String, Number],
      default: () => ({}) // 默认值避免undefined报错
    }
  },
  computed: {
    // qq表情映射表
    qqFaceMap() {
      return expressionMap || {}
    },
    // 生成组件实例唯一的qqMap名称，解决全局冲突
    uniqueQqMapName() {
      return `qqMap_${this._uid}`
    },
    // 生成组件实例唯一的emojiMap名称，解决全局冲突
    uniqueEmojiMapName() {
      return `emojiMap_${this._uid}`
    }
  },
  methods: {
    // 选择表情，触发回调传递结果
    selectExpression(val) {
      let rm = expressionMap[val];
      const qqList = [113, 114, 115, 116, 117, 118, 124, 125];

      if (rm) {
        if (val < 105 || qqList.indexOf(val) >= 0) {
          rm = '[' + expressionMap[val] + ']';
        } else {
          rm = '<' + rm + '>';
          rm = emojiMap[rm];
          const rmencode = parseInt(rm, 16);
          rm = String.fromCodePoint(rmencode);
        }
        // console.log(this.parames);
        
        // 传递表情结果和组件props参数
        this.$emit('expressionContent', {
          emoji: rm,
          parames: this.parames // 正常传递props参数，恢复注释
        });
      }
    }
  }
}
</script>

<style lang="scss" scoped>
.expression-icon {
  width: fit-content;
  cursor: pointer;
  font-size: 24px;
}

.emo_img {
  width: 100%;
  display: block;
}

.emo_ico {
  width: 20px;
  height: 20px;
  display: block;
  font-size: 0;
  // margin-bottom: 12px;
}
</style>