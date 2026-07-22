<template>
  <section class="app-main">
    <!-- <breadcrumb class="breadcrumb-container" v-show="name !== 'Dashboard' " /> -->
    <!-- <transition name="fade-transform" mode="out-in"> -->


    <div class="bg_fff" :class="{
      'bg_fff--full': ($route.name && $route.name.startsWith('marketing_remix')) || name === 'Dashboard',
      'bg_fff--no-padding': noPaddingRoutes.includes($route.name)
    }">

      <keep-alive>
        <!-- 需要缓存的视图组件 -->
        <router-view :key="key" v-if="$route.meta.keepAlive"/>
      </keep-alive>
      <router-view :key="key" v-if="!$route.meta.keepAlive"/>

    </div>
    <!-- </transition> -->
  </section>
</template>
·
<script>
// import Breadcrumb from '@/components/Breadcrumb'

export default {
  data() {
    return {
      name: "",
      // 需要去除外层 padding 的路由列表（拓客模块卡片式页面，自行管理内边距）
      noPaddingRoutes: ['tk_manage', 'tk_task_detail', 'tk_reply_customer_detail'],
    }
  },
  created() {
    this.name = this.$route.name;
  },
  components: {
    // Breadcrumb,
  },
  name: 'AppMain',
  computed: {
    key() {
      return this.$route.path
    }
  },
  watch: {
    $route(to, from) {
      this.name = this.$route.name;
    }
  }
}
</script>

<style scoped>
.app-main {
  /* 64px = navbar height */
  min-height: calc(100vh);
  width: 100%;
  position: relative;
  overflow: hidden;
  background: #f9fafb;
  padding: 0;
}

.fixed-header+.app-main {
  padding-top: 48px;
}

.bg_fff {
  width: 100%;
  height: calc(100vh - 48px);
  overflow: auto;
  background: #f9fafb;
  padding: 16px;
}

.bg_fff.bg_fff--full {
  height: 100vh;
}

/* 拓客任务管理页：去除外层 padding，让卡片式页面充满内容区 */
.bg_fff.bg_fff--no-padding {
  padding: 0;
}
</style>

<style lang="scss">
// fix css style bug in open el-dialog
.el-popup-parent--hidden {
  .fixed-header {
    // padding-right: 15px;
  }
}

.breadcrumb-container {
  width: 100%;
  background: none;
  padding: 0 18px;
  // border-bottom: 17px solid #f0f2f5;
}
</style>
