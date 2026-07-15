<template>
  <div class="score-bar">
    <div class="score-bar__head">
      <span class="score-bar__name">{{ name }}</span>
      <span class="score-bar__value">{{ value }}</span>
    </div>
    <div class="score-bar__track">
      <div class="score-bar__fill" :style="{ width: percentage + '%' }" />
    </div>
    <div v-if="comment" class="score-bar__comment">{{ comment }}</div>
  </div>
</template>

<script>
export default {
  name: 'H5ScoreBar',
  props: {
    name: { type: String, default: '' },
    value: { type: [Number, String], default: 0 },
    max: { type: Number, default: 100 },
    comment: { type: String, default: '' }
  },
  computed: {
    percentage() {
      const v = Number(this.value) || 0
      const m = this.max || 100
      return Math.max(0, Math.min(100, (v / m) * 100))
    }
  }
}
</script>

<style lang="scss" scoped>
.score-bar {
  padding: 10px 0;
}
.score-bar__head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 6px;
}
.score-bar__name {
  font-size: 13px;
  color: var(--h5-text-2);
  font-weight: 500;
}
.score-bar__value {
  font-size: 15px;
  font-weight: 700;
  color: var(--h5-primary);
}
.score-bar__track {
  height: 6px;
  background: #F3F4F6;
  border-radius: 3px;
  overflow: hidden;
}
.score-bar__fill {
  height: 100%;
  background: var(--h5-gradient);
  border-radius: 3px;
  transition: width .4s ease;
}
.score-bar__comment {
  margin-top: 6px;
  font-size: 12px;
  color: var(--h5-text-3);
  line-height: 1.5;
}
</style>
