<template>
  <div class="ds-page-header">
    <div class="ds-page-header__left">
      <h1 class="ds-page-title">{{ title }}</h1>
      <p v-if="desc" class="ds-page-desc">{{ desc }}</p>
    </div>
    <div v-if="$slots.default" class="ds-header-actions">
      <slot></slot>
    </div>
  </div>
</template>

<script>
export default {
  name: 'PageHeader',
  props: {
    title: { type: String, required: true },
    desc: { type: String, default: '' }
  }
}
</script>
