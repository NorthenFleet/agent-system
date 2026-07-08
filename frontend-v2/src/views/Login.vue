<template>
  <div class="login-page">
    <!-- 背景装饰 -->
    <div class="bg-decoration">
      <div class="bg-circle c1"></div>
      <div class="bg-circle c2"></div>
      <div class="bg-circle c3"></div>
      <div class="floating-emojis">
        <span class="femoji e1">🐢</span>
        <span class="femoji e2">💻</span>
        <span class="femoji e3">📋</span>
        <span class="femoji e4">🔧</span>
        <span class="femoji e5">🎯</span>
      </div>
    </div>

    <div class="login-card">
      <div class="login-header">
        <img class="login-logo" src="/favicon.svg" alt="Logo" />
        <h2>智能体集群系统</h2>
        <p class="login-subtitle">一叶科技</p>
      </div>
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        @submit.prevent="handleLogin"
        class="login-form"
      >
        <el-form-item prop="username">
          <el-input
            v-model="form.username"
            placeholder="请输入用户名"
            :prefix-icon="User"
            size="large"
            clearable
          />
        </el-form-item>
        <el-form-item prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="请输入密码"
            :prefix-icon="Lock"
            size="large"
            show-password
            @keyup.enter="handleLogin"
          />
        </el-form-item>
        <el-form-item>
          <div class="form-options">
            <el-checkbox v-model="rememberMe">记住我</el-checkbox>
          </div>
        </el-form-item>
        <el-form-item>
          <el-button
            type="primary"
            size="large"
            class="login-btn"
            :loading="authStore.loading"
            @click="handleLogin"
          >
            登 录
          </el-button>
        </el-form-item>
      </el-form>
      <div class="login-footer">
      <span>默认账号: admin / admin123</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { User, Lock } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import type { FormInstance } from 'element-plus'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()
const formRef = ref<FormInstance>()
const rememberMe = ref(false)

const form = reactive({
  username: '',
  password: ''
})

const rules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 2, max: 20, message: '用户名长度为 2-20 个字符', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码至少 6 个字符', trigger: 'blur' }
  ]
}

async function handleLogin() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  try {
    await authStore.login(form.username, form.password)
    ElMessage.success('登录成功')
    router.push('/')
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '登录失败，请检查用户名和密码')
  }
}
</script>

<style scoped>
.login-page {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100vh;
  background: linear-gradient(135deg, #0f1923 0%, #1d2838 50%, #243447 100%);
  overflow: hidden;
  position: relative;
}

/* 背景装饰 */
.bg-decoration {
  position: absolute;
  inset: 0;
  pointer-events: none;
  overflow: hidden;
}

.bg-circle {
  position: absolute;
  border-radius: 50%;
  opacity: 0.06;
}

.c1 {
  width: 400px; height: 400px;
  background: radial-gradient(circle, #409eff, transparent 70%);
  top: -100px; left: -100px;
  animation: float-slow 20s ease-in-out infinite;
}

.c2 {
  width: 300px; height: 300px;
  background: radial-gradient(circle, #67c23a, transparent 70%);
  bottom: -80px; right: -50px;
  animation: float-slow 15s ease-in-out infinite reverse;
}

.c3 {
  width: 200px; height: 200px;
  background: radial-gradient(circle, #e6a23c, transparent 70%);
  top: 50%; right: 10%;
  animation: float-slow 18s ease-in-out infinite;
  animation-delay: -5s;
}

@keyframes float-slow {
  0%, 100% { transform: translate(0, 0); }
  33% { transform: translate(30px, -20px); }
  66% { transform: translate(-20px, 30px); }
}

/* 浮动 emoji */
.floating-emojis {
  position: absolute;
  inset: 0;
}

.femoji {
  position: absolute;
  font-size: 32px;
  opacity: 0.08;
  animation: float-emoji 12s ease-in-out infinite;
}

.e1 { top: 10%; left: 15%; animation-delay: 0s; }
.e2 { top: 25%; right: 20%; animation-delay: -3s; font-size: 28px; }
.e3 { bottom: 30%; left: 10%; animation-delay: -6s; }
.e4 { bottom: 15%; right: 15%; animation-delay: -9s; font-size: 24px; }
.e5 { top: 60%; left: 40%; animation-delay: -2s; font-size: 26px; }

@keyframes float-emoji {
  0%, 100% { transform: translateY(0) rotate(0deg); }
  50% { transform: translateY(-15px) rotate(8deg); }
}

/* 登录卡片 */
.login-card {
  width: 420px;
  max-width: 90vw;
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(20px);
  border-radius: 16px;
  padding: 48px 40px;
  box-shadow: 0 24px 80px rgba(0, 0, 0, 0.35);
  position: relative;
  z-index: 1;
  animation: slide-up 0.5s ease-out;
}

@keyframes slide-up {
  from { opacity: 0; transform: translateY(30px); }
  to { opacity: 1; transform: translateY(0); }
}

.login-header {
  text-align: center;
  margin-bottom: 36px;
}

.login-logo {
  width: 64px;
  height: 64px;
  display: block;
  margin: 0 auto 8px;
  animation: bounce-logo 2s ease-in-out infinite;
}

@keyframes bounce-logo {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.05); }
}

.login-header h2 {
  font-size: 26px;
  font-weight: 700;
  color: #1d1e2c;
  margin: 0 0 6px;
  letter-spacing: 1px;
}

.login-subtitle {
  color: #909399;
  font-size: 14px;
  margin: 0;
}

.login-form {
  margin-top: 24px;
}

.form-options {
  display: flex;
  justify-content: flex-start;
}

.login-btn {
  width: 100%;
  height: 44px;
  font-size: 16px;
  font-weight: 500;
  letter-spacing: 4px;
  border-radius: 8px;
}

.login-footer {
  text-align: center;
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid #ebeef5;
  font-size: 12px;
  color: #c0c4cc;
}

@media (max-width: 480px) {
  .login-card {
    padding: 32px 24px;
  }
  .login-header h2 {
    font-size: 22px;
  }
  .login-logo {
    width: 48px;
    height: 48px;
  }
}
</style>
