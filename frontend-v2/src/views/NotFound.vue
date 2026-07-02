<template>
  <div class="not-found-page">
    <div class="not-found-content">
      <!-- 404 大数字 -->
      <div class="error-code">
        <span class="digit d1">4</span>
        <span class="digit d2">0</span>
        <span class="digit d3">4</span>
      </div>
      <h1 class="error-title">页面未找到</h1>
      <p class="error-desc">您访问的页面不存在或已被移除</p>

      <!-- 操作按钮 -->
      <div class="error-actions">
        <el-button type="primary" size="large" @click="goHome">
          🏠 返回首页
        </el-button>
        <el-button size="large" @click="goBack">
          ← 返回上一页
        </el-button>
      </div>

      <!-- 装饰元素 -->
      <div class="decoration">
        <span class="emoji float-1">🐢</span>
        <span class="emoji float-2">💻</span>
        <span class="emoji float-3">🔧</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()

function goHome() {
  router.push('/')
}

function goBack() {
  window.history.back()
}
</script>

<style scoped>
.not-found-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  background: linear-gradient(135deg, #1d1e2c 0%, #2d2f42 100%);
  overflow: hidden;
}

.not-found-content {
  text-align: center;
  position: relative;
  z-index: 1;
}

/* 404 数字 */
.error-code {
  display: flex;
  justify-content: center;
  gap: 8px;
  margin-bottom: 24px;
}

.digit {
  font-size: 120px;
  font-weight: 900;
  line-height: 1;
  background: linear-gradient(135deg, #409eff 0%, #66b1ff 50%, #79bbff 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  animation: pulse 2s ease-in-out infinite;
}

.d1 { animation-delay: 0s; }
.d2 { animation-delay: 0.3s; }
.d3 { animation-delay: 0.6s; }

@keyframes pulse {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-8px); }
}

.error-title {
  font-size: 28px;
  font-weight: 600;
  color: #e0e0e0;
  margin: 0 0 12px;
}

.error-desc {
  font-size: 16px;
  color: #909399;
  margin: 0 0 32px;
}

.error-actions {
  display: flex;
  gap: 16px;
  justify-content: center;
}

/* 浮动装饰 */
.decoration {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.emoji {
  position: absolute;
  font-size: 40px;
  opacity: 0.15;
  animation: float 6s ease-in-out infinite;
}

.float-1 { top: 10%; left: 15%; animation-delay: 0s; }
.float-2 { top: 60%; right: 20%; animation-delay: 2s; }
.float-3 { bottom: 15%; left: 25%; animation-delay: 4s; }

@keyframes float {
  0%, 100% { transform: translateY(0) rotate(0deg); }
  50% { transform: translateY(-20px) rotate(10deg); }
}

@media (max-width: 640px) {
  .digit {
    font-size: 80px;
  }
  .error-title {
    font-size: 22px;
  }
  .error-desc {
    font-size: 14px;
  }
  .error-actions {
    flex-direction: column;
    align-items: center;
  }
}
</style>
