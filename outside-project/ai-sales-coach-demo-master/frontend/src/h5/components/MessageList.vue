<template>
  <div ref="scroller" class="msg-list">
    <div v-for="(m, idx) in messages" :key="m.id || m.seq || idx" :class="['msg-row', Number(m.role) === 2 ? 'seat' : 'customer']">
      <div class="msg-bubble">{{ m.content }}</div>
    </div>
    <div v-if="aiReplying" class="msg-row customer">
      <div class="msg-typing"><span /><span /><span /></div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'H5MessageList',
  props: {
    messages: { type: Array, default: () => [] },
    aiReplying: { type: Boolean, default: false }
  },
  watch: {
    messages: { deep: true, handler() { this.$nextTick(() => this.scrollToBottom()) } },
    aiReplying() { this.$nextTick(() => this.scrollToBottom()) }
  },
  mounted() { this.scrollToBottom() },
  methods: {
    scrollToBottom() {
      const el = this.$refs.scroller
      if (el) el.scrollTop = el.scrollHeight
    }
  }
}
</script>

<style lang="scss" scoped>
.msg-list {
  flex: 1;
  overflow-y: auto;
  padding: 14px;
  background: var(--h5-bg);
  -webkit-overflow-scrolling: touch;
}
.msg-row {
  display: flex;
  margin-bottom: 14px;
  &.customer { justify-content: flex-start; }
  &.seat { justify-content: flex-end; }
}
.msg-bubble {
  max-width: 78%;
  padding: 10px 12px;
  font-size: 14px;
  line-height: 1.55;
  border-radius: 12px;
  word-break: break-word;
  white-space: pre-wrap;
}
.msg-row.customer .msg-bubble {
  background: #fff;
  color: var(--h5-text-1);
  border-top-left-radius: 4px;
  box-shadow: var(--h5-shadow);
}
.msg-row.seat .msg-bubble {
  background: var(--h5-gradient);
  color: #fff;
  border-top-right-radius: 4px;
  box-shadow: 0 2px 6px rgba(99,102,241,.22);
}
.msg-typing {
  display: inline-flex;
  gap: 3px;
  padding: 12px;
  background: #fff;
  border-radius: 12px;
  border-top-left-radius: 4px;
  box-shadow: var(--h5-shadow);
  align-items: center;
}
.msg-typing span {
  width: 6px; height: 6px;
  background: var(--h5-text-3);
  border-radius: 50%;
  animation: msgBounce 1.4s infinite ease-in-out both;
}
.msg-typing span:nth-child(2) { animation-delay: -.32s; }
.msg-typing span:nth-child(3) { animation-delay: -.16s; }
@keyframes msgBounce {
  0%, 80%, 100% { transform: scale(0); }
  40% { transform: scale(1); }
}
</style>
