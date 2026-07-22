<template>
  <div class="h5-profile">
    <!-- 顶部紫色渐变身份区 -->
    <div class="hero">
      <div class="hero-avatar">{{ avatarText }}</div>
      <div class="hero-name">{{ user.name || '未登录' }}</div>
      <div class="hero-meta">
        <span class="hero-badge">{{ roleLabel }}</span>
        <span class="hero-meta__dot">·</span>
        <span>销冠陪练</span>
      </div>
    </div>

    <div class="section">
      <div class="section__title">使用提示</div>
      <div class="tips">
        <div class="tip-row">💡 长按麦克风按钮即可录音输入</div>
        <div class="tip-row">💡 至少完成 1 轮对话才能结束并评分</div>
        <div class="tip-row">💡 必练完成 100% 后才能进入团队排行榜</div>
      </div>
    </div>

    <!-- 退出 -->
    <div class="logout-wrap">
      <button class="logout-btn" @click="onLogout">退出登录</button>
    </div>

    <div class="copyright">© {{ year }} 销冠陪练</div>
  </div>
</template>

<script>
import { mapGetters } from 'vuex'

export default {
  name: 'H5Profile',
  computed: {
    ...mapGetters('h5User', ['user']),
    avatarText() {
      const n = (this.user && this.user.name) || '?'
      return n.slice(0, 1)
    },
    roleLabel() {
      const r = this.user && this.user.role
      if (r === 'manager') return '管理员'
      if (r === 'staff') return '坐席'
      if (r === 'group_manager') return '组长'
      return r || '员工'
    },
    year() { return new Date().getFullYear() }
  },
  methods: {
    onLogout() {
      this.$dialog.confirm({
        title: '退出登录',
        message: '确定要退出当前账号吗?',
        confirmButtonText: '退出',
        confirmButtonColor: '#DC2626'
      }).then(async () => {
        await this.$store.dispatch('h5User/logout')
        this.$toast.success('已退出')
        setTimeout(() => {
          this.$router.replace('/m/login')
        }, 300)
      }).catch(() => {})
    }
  }
}
</script>

<style lang="scss" scoped>
.h5-profile {
  min-height: 100vh;
  background: var(--h5-bg);
  padding-bottom: calc(80px + env(safe-area-inset-bottom));
}

.hero {
  background: var(--h5-login-gradient);
  padding: 36px 20px 28px;
  color: #fff;
  text-align: center;
  padding-top: calc(36px + env(safe-area-inset-top));
}
.hero-avatar {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  background: rgba(255, 255, 255, .22);
  border: 2px solid rgba(255, 255, 255, .4);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 26px;
  font-weight: 700;
  margin-bottom: 10px;
  backdrop-filter: blur(6px);
}
.hero-name {
  font-size: 20px;
  font-weight: 700;
  margin-bottom: 6px;
}
.hero-meta {
  font-size: 12px;
  color: rgba(255, 255, 255, .85);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  &__dot { opacity: .6; }
}
.hero-badge {
  background: rgba(255, 255, 255, .2);
  padding: 2px 10px;
  border-radius: 10px;
}

.section {
  margin: 12px 12px 0;
  &__title {
    font-size: 12px;
    color: var(--h5-text-3);
    padding: 8px 4px;
  }
}
.cell {
  display: flex;
  align-items: center;
  background: #fff;
  padding: 14px 16px;
  font-size: 14px;
  color: var(--h5-text-1);
  border-bottom: 1px solid #F3F4F6;
  &:first-child { border-radius: var(--h5-radius) var(--h5-radius) 0 0; }
  &:last-child { border-bottom: 0; border-radius: 0 0 var(--h5-radius) var(--h5-radius); }
  &:only-child { border-radius: var(--h5-radius); }
  &:active { background: #FAFAFB; }

  &__icon {
    width: 22px;
    text-align: center;
    margin-right: 10px;
    font-size: 16px;
  }
  &__label {
    flex: 1;
  }
  &__value {
    color: var(--h5-text-3);
    font-size: 12px;
    margin-right: 6px;
  }
  &__arrow {
    color: var(--h5-text-3);
  }
}

.tips {
  background: #fff;
  border-radius: var(--h5-radius);
  padding: 6px 16px;
}
.tip-row {
  font-size: 12px;
  color: var(--h5-text-2);
  padding: 8px 0;
  line-height: 1.6;
  border-bottom: 1px dashed #F3F4F6;
  &:last-child { border-bottom: 0; }
}

.logout-wrap {
  padding: 28px 16px 0;
}
.logout-btn {
  width: 100%;
  height: 46px;
  background: #fff;
  border: 1px solid #FECACA;
  border-radius: 10px;
  color: #DC2626;
  font-size: 15px;
  font-weight: 600;
  &:active { background: #FEF2F2; }
}

.copyright {
  text-align: center;
  font-size: 11px;
  color: var(--h5-text-3);
  padding: 22px 0 0;
}
</style>
