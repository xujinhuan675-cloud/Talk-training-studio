<template>
  <div class="h5-login">
    <div class="brand-banner">
      <div class="brand-logo">AI销冠陪练</div>
      <div class="brand-slogan">AI 模拟客户 · 实战演练 · 即时评分</div>
      <div class="brand-features">
        <span class="feature-chip">场景闯关</span>
        <span class="feature-chip">多维评分</span>
        <span class="feature-chip">复盘提升</span>
      </div>
    </div>

    <div class="form-card">
      <div class="card-title">移动端演练</div>
      <div class="card-subtitle">使用演示账号开始一次销售陪练</div>

      <div v-if="errorMsg" class="error-tip">{{ errorMsg }}</div>

      <div class="field-group">
        <div class="field-label">账号</div>
        <div class="field-input">
          <van-icon name="user-o" class="field-icon" />
          <input v-model="form.username" type="text" placeholder="请输入账号" autocomplete="off">
        </div>
      </div>

      <div class="field-group">
        <div class="field-label">密码</div>
        <div class="field-input">
          <van-icon name="lock" class="field-icon" />
          <input
            v-model="form.password"
            :type="passwordVisible ? 'text' : 'password'"
            placeholder="请输入密码"
            autocomplete="new-password"
            @keyup.enter="onLogin"
          >
          <van-icon
            :name="passwordVisible ? 'eye-o' : 'closed-eye'"
            class="field-suffix"
            @click="passwordVisible = !passwordVisible"
          />
        </div>
      </div>

      <button class="h5-gradient-btn" :disabled="loading" @click="onLogin">
        <span v-if="!loading">立即登录</span>
        <span v-else>登录中...</span>
        <van-icon v-if="!loading" name="arrow" />
      </button>

      <div class="demo-accounts">
        <p>演示账号</p>
        <span>user1 / user123</span>
        <span>leader1 / leader123</span>
        <span>admin / admin123</span>
      </div>
    </div>

    <div class="copyright">© {{ year }} AI销冠陪练中心</div>
  </div>
</template>

<script>
export default {
  name: 'H5Login',
  data() {
    return {
      form: {
        username: 'user1',
        password: 'user123'
      },
      passwordVisible: false,
      loading: false,
      errorMsg: '',
      redirect: '/m/challenge'
    }
  },
  computed: {
    year() {
      return new Date().getFullYear()
    }
  },
  created() {
    const r = this.$route.query.redirect
    if (r) this.redirect = decodeURIComponent(r)
  },
  methods: {
    validate() {
      if (!this.form.username) {
        this.errorMsg = '请输入账号'
        return false
      }
      if (!this.form.password) {
        this.errorMsg = '请输入密码'
        return false
      }
      this.errorMsg = ''
      return true
    },
    async onLogin() {
      if (!this.validate()) return
      this.loading = true
      try {
        await this.$store.dispatch('h5User/login', { ...this.form })
        this.$toast.success('登录成功')
        setTimeout(() => {
          this.$router.replace(this.redirect || '/m/challenge')
        }, 200)
      } catch (e) {
        this.errorMsg = e.message || '登录失败'
      } finally {
        this.loading = false
      }
    }
  }
}
</script>

<style lang="scss" scoped>
.h5-login {
  min-height: 100vh;
  background: var(--h5-bg);
  display: flex;
  flex-direction: column;
}

.brand-banner {
  background: var(--h5-login-gradient);
  padding: 56px 24px 80px;
  color: #fff;
  text-align: left;

  .brand-logo {
    font-size: 24px;
    font-weight: 700;
    margin-bottom: 8px;
  }

  .brand-slogan {
    font-size: 14px;
    color: rgba(255, 255, 255, .85);
    margin-bottom: 22px;
  }

  .brand-features {
    display: flex;
    gap: 8px;
  }

  .feature-chip {
    flex: 1;
    background: rgba(255, 255, 255, .15);
    border-radius: 8px;
    padding: 8px 4px;
    font-size: 12px;
    text-align: center;
    color: #fff;
    border: 1px solid rgba(255, 255, 255, .12);
  }
}

.form-card {
  background: #fff;
  border-radius: 16px;
  margin: -48px 20px 0;
  padding: 24px 20px 28px;
  box-shadow: var(--h5-shadow-lg);
  position: relative;
  z-index: 2;

  .card-title {
    font-size: 22px;
    font-weight: 700;
    color: #111827;
    margin-bottom: 4px;
  }

  .card-subtitle {
    font-size: 13px;
    color: #6b7280;
    margin-bottom: 20px;
  }

  .error-tip {
    background: #fef2f2;
    border: 1px solid #fecaca;
    color: #dc2626;
    font-size: 13px;
    border-radius: 8px;
    padding: 8px 12px;
    margin-bottom: 14px;
  }
}

.field-group {
  margin-bottom: 16px;
}

.field-label {
  font-size: 13px;
  color: #374151;
  margin-bottom: 6px;
  font-weight: 500;
}

.field-input {
  height: 46px;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  display: flex;
  align-items: center;
  padding: 0 12px;

  input {
    flex: 1;
    border: none;
    outline: none;
    background: transparent;
    font-size: 15px;
    color: #111827;
  }
}

.field-icon {
  color: #9ca3af;
  margin-right: 8px;
}

.field-suffix {
  color: #9ca3af;
  padding-left: 8px;
}

.h5-gradient-btn {
  width: 100%;
  height: 48px;
  border: none;
  border-radius: 12px;
  background: var(--h5-primary-gradient);
  color: #fff;
  font-size: 16px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-top: 6px;
}

.demo-accounts {
  margin-top: 18px;
  padding: 12px;
  border-radius: 10px;
  background: #f8fafc;
  display: grid;
  gap: 6px;
  color: #64748b;
  font-size: 12px;

  p {
    color: #334155;
    font-weight: 600;
    margin: 0;
  }
}

.copyright {
  margin-top: auto;
  padding: 18px;
  text-align: center;
  font-size: 12px;
  color: #9ca3af;
}
</style>
