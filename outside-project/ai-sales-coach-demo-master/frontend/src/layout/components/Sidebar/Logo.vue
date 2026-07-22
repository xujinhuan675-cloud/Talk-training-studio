<template>
  <div class="sidebar-logo-container" :class="{ collapse }">
    <router-link v-if="!collapse" class="sidebar-logo-link" to="/">
      <span class="logo-mark">AI</span>
      <span class="logo-text">销冠陪练</span>
    </router-link>

    <button class="sidebar-toggle-btn" :class="{ 'is-centered': collapse }" @click="toggleSidebar">
      <i :class="collapse ? 'el-icon-s-unfold' : 'el-icon-s-fold'"></i>
    </button>
  </div>
</template>

<script>
export default {
  name: 'SidebarLogo',
  props: {
    collapse: {
      type: Boolean,
      required: true
    }
  },
  methods: {
    toggleSidebar() {
      this.$store.dispatch('app/toggleSideBar')
    }
  }
}
</script>

<style lang="scss" scoped>
.sidebar-logo-container {
  width: 100%;
  height: 48px;
  background: #0f172a;
  overflow: hidden;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 12px;

  &.collapse {
    justify-content: center;
    padding: 0;
  }
}

.sidebar-logo-link {
  flex: 1;
  height: 100%;
  display: flex;
  align-items: center;
  gap: 9px;
  color: #fff;
  text-decoration: none;
}

.logo-mark {
  width: 28px;
  height: 28px;
  border-radius: 7px;
  background: #4f46e5;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 12px;
  font-weight: 800;
}

.logo-text {
  font-size: 15px;
  font-weight: 700;
  white-space: nowrap;
}

.sidebar-toggle-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  flex-shrink: 0;
  background: transparent;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  color: rgba(255, 255, 255, 0.55);
  transition: background 0.2s, color 0.2s;

  &:hover {
    background: rgba(255, 255, 255, 0.1);
    color: #fff;
  }

  i {
    font-size: 18px;
  }
}
</style>
