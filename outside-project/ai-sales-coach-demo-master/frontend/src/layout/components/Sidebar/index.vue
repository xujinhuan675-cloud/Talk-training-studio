<template>
  <div class="custom-sidebar" :class="{ 'is-collapse': isCollapse }">
    <logo :collapse="isCollapse" />

    <el-scrollbar wrap-class="scrollbar-wrapper">
      <el-menu
        :default-active="activeMenu"
        :collapse="isCollapse"
        background-color="transparent"
        text-color="#cbd5e1"
        active-text-color="#ffffff"
        :collapse-transition="false"
        mode="vertical"
        class="custom-nav-menu"
      >
        <el-menu-item
          v-for="item in menuItems"
          :key="item.path"
          :index="item.path"
          @click="navigateTo(item.path)"
        >
          <i :class="item.icon"></i>
          <span slot="title">{{ item.title }}</span>
        </el-menu-item>
      </el-menu>
    </el-scrollbar>

    <div class="sidebar-user" :class="{ 'sidebar-user--collapsed': isCollapse }">
      <div class="user-avatar-circle">{{ (name || '用')[0] }}</div>
      <template v-if="!isCollapse">
        <div class="user-text">
          <p class="user-name">{{ name || '演示用户' }}</p>
          <p class="user-role">{{ roleLabel }}</p>
        </div>
        <el-button type="text" class="logout-btn" @click="logout">退出</el-button>
      </template>
    </div>
  </div>
</template>

<script>
import { mapGetters } from 'vuex'
import Logo from './Logo'

export default {
  name: 'CustomSidebar',
  components: { Logo },
  data() {
    return {
      baseMenuItems: [
        { title: '闯关陪练', path: '/training/challenge', icon: 'el-icon-s-flag' },
        { title: '练习记录', path: '/training/history', icon: 'el-icon-document' },
        { title: '销冠榜', path: '/training/leaderboard', icon: 'el-icon-trophy' },
        { title: '陪练配置', path: '/training/config', icon: 'el-icon-setting', adminOnly: true }
      ]
    }
  },
  computed: {
    ...mapGetters(['sidebar', 'name', 'role']),
    isCollapse() {
      return !this.sidebar.opened
    },
    activeMenu() {
      return this.$route.meta.activeMenu || this.$route.path
    },
    roleLabel() {
      const map = { admin: '管理员', leader: '组长', staff: '员工' }
      return map[this.role] || '演示账号'
    },
    menuItems() {
      return this.baseMenuItems.filter(item => !item.adminOnly || this.role === 'admin')
    }
  },
  methods: {
    navigateTo(path) {
      if (this.$route.path !== path) {
        this.$router.push(path, () => {}, () => {})
      }
    },
    async logout() {
      await this.$store.dispatch('user/logout')
      this.$router.push('/login')
    }
  }
}
</script>

<style lang="scss" scoped>
$sidebar-bg: #0f172a;
$sidebar-border: rgba(255, 255, 255, 0.06);
$indigo: #4f46e5;
$text-default: #cbd5e1;
$text-muted: #94a3b8;

.custom-sidebar {
  width: 100%;
  height: 100%;
  background: $sidebar-bg;
  display: flex;
  flex-direction: column;
  overflow: hidden;

  ::v-deep .el-scrollbar {
    flex: 1;
    height: 0;
  }

  ::v-deep .scrollbar-wrapper {
    overflow-x: hidden !important;
  }
}

::v-deep .custom-nav-menu {
  background: transparent !important;
  border: none !important;
  padding-top: 10px;

  &.el-menu--collapse {
    width: 72px;

    .el-menu-item {
      padding-left: 0 !important;
      padding-right: 0 !important;
      text-align: center;

      i {
        margin-right: 0 !important;
      }
    }
  }

  .el-menu-item {
    height: 42px;
    line-height: 42px;
    margin: 4px 8px;
    border-radius: 7px;
    color: $text-default !important;
    background: transparent !important;
    border-left: 3px solid transparent;
    transition: all 0.15s;

    i {
      color: $text-muted;
      font-size: 17px;
      margin-right: 10px;
    }

    &:hover {
      background: rgba(255, 255, 255, 0.06) !important;
      color: #fff !important;
    }

    &.is-active {
      background: rgba(79, 70, 229, 0.25) !important;
      border-left-color: $indigo;
      color: #fff !important;

      i {
        color: #fff !important;
      }
    }
  }
}

.sidebar-user {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 10px 12px;
  padding: 10px 12px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid $sidebar-border;
  border-radius: 10px;
  flex-shrink: 0;

  &--collapsed {
    justify-content: center;
    padding: 8px;
  }
}

.user-avatar-circle {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  background: $indigo;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 14px;
  font-weight: 700;
  flex-shrink: 0;
}

.user-text {
  flex: 1;
  min-width: 0;
}

.user-name {
  font-size: 13px;
  font-weight: 500;
  color: $text-default;
  margin: 0 0 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.user-role {
  font-size: 11px;
  color: #64748b;
  margin: 0;
}

.logout-btn {
  color: #cbd5e1;
  padding: 0;
}
</style>
