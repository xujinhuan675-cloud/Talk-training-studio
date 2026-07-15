<template>
  <div class="h5-layout">
    <keep-alive>
      <router-view v-if="$route.meta.keepAlive" :key="$route.fullPath" />
    </keep-alive>
    <router-view v-if="!$route.meta.keepAlive" :key="$route.fullPath" />
    <van-tabbar
      v-if="!$route.meta.hideTab && tabVisible"
      v-model="active"
      route
      active-color="#6366F1"
      inactive-color="#9CA3AF"
      safe-area-inset-bottom
    >
      <van-tabbar-item replace to="/m/challenge">
        <template #icon><span class="tab-emoji">🎯</span></template>
        陪练
      </van-tabbar-item>
      <van-tabbar-item replace to="/m/history">
        <template #icon><span class="tab-emoji">📋</span></template>
        记录
      </van-tabbar-item>
      <van-tabbar-item replace to="/m/leaderboard">
        <template #icon><span class="tab-emoji">🏆</span></template>
        榜单
      </van-tabbar-item>
      <van-tabbar-item replace to="/m/profile">
        <template #icon><span class="tab-emoji">👤</span></template>
        我的
      </van-tabbar-item>
    </van-tabbar>
  </div>
</template>

<script>
export default {
  name: 'H5Layout',
  provide() {
    return {
      setTabVisible: (v) => { this.tabVisible = !!v }
    }
  },
  data() {
    return { active: 0, tabVisible: true }
  },
  watch: {
    // 切路由时默认恢复 Tab,避免上一页未及时还原
    $route() { this.tabVisible = true }
  }
}
</script>

<style lang="scss" scoped>
.h5-layout {
  min-height: 100vh;
  background: var(--h5-bg);
  padding-bottom: calc(50px + env(safe-area-inset-bottom));
}
::v-deep .tab-emoji {
  font-size: 22px;
  line-height: 1;
  font-family: "Apple Color Emoji", "Segoe UI Emoji", "Noto Color Emoji", sans-serif;
  display: inline-block;
}
</style>
