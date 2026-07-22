<template>
  <div class="login-container">
    <div class="login-box">
      <div class="login-header">
        <h2>AI销冠陪练中心</h2>
        <p class="subtitle">演示账号：admin / admin123</p>
      </div>
      <el-form ref="loginForm" :model="form" :rules="rules" class="login-form">
        <el-form-item prop="username">
          <el-input
            v-model="form.username"
            placeholder="用户名"
            prefix-icon="el-icon-user"
            @keyup.enter.native="handleLogin"
          />
        </el-form-item>
        <el-form-item prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="密码"
            prefix-icon="el-icon-lock"
            show-password
            @keyup.enter.native="handleLogin"
          />
        </el-form-item>
        <el-button
          type="primary"
          :loading="loading"
          class="login-btn"
          @click="handleLogin"
        >
          登录
        </el-button>
      </el-form>
      <div class="demo-accounts">
        <p>演示账号：</p>
        <ul>
          <li>admin / admin123（管理员，可配置场景和维度）</li>
          <li>user1 / user123（员工，可进行演练）</li>
          <li>user2 / user123（员工）</li>
        </ul>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'Login',
  data() {
    return {
      form: { username: 'admin', password: 'admin123' },
      loading: false,
      rules: {
        username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
        password: [{ required: true, message: '请输入密码', trigger: 'blur' }]
      }
    }
  },
  methods: {
    handleLogin() {
      this.$refs.loginForm.validate(valid => {
        if (!valid) return
        this.loading = true
        this.$store.dispatch('user/login', this.form)
          .then(() => {
            const redirect = this.$route.query.redirect || '/training/challenge'
            this.$router.push(redirect)
          })
          .catch(err => {
            this.$message.error(err.message || '登录失败')
          })
          .finally(() => {
            this.loading = false
          })
      })
    }
  }
}
</script>

<style lang="scss" scoped>
.login-container {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.login-box {
  background: #fff;
  border-radius: 12px;
  padding: 40px;
  width: 400px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.15);
}

.login-header {
  text-align: center;
  margin-bottom: 32px;

  h2 {
    font-size: 24px;
    color: #333;
    margin: 0 0 8px;
  }

  .subtitle {
    color: #999;
    font-size: 13px;
    margin: 0;
  }
}

.login-form {
  .login-btn {
    width: 100%;
    height: 44px;
    font-size: 16px;
    margin-top: 8px;
  }
}

.demo-accounts {
  margin-top: 24px;
  padding: 16px;
  background: #f8f9fa;
  border-radius: 8px;
  font-size: 12px;
  color: #666;

  p { margin: 0 0 8px; font-weight: 600; }
  ul { margin: 0; padding-left: 16px; }
  li { margin-bottom: 4px; }
}
</style>
