<template>
  <div id="app">
    <router-view :key="key" />
  </div>
</template>
<script>

export default {
  name: 'App',
  computed: {
    key() {
      //修复登录页面浏览器地址参数变了不会及时刷新页面问题
      return this.$route.path == '/login' ? this.$route.name ? this.$route.name + new Date() : this.$route + new Date() : ''
    }
  },
  mounted() {
    

  }
}
</script>

<style lang="scss">
@import './styles/qqface.scss';
</style>