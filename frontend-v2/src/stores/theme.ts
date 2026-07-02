import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

export const useThemeStore = defineStore('theme', () => {
  const isDark = ref(localStorage.getItem('theme') === 'dark')

  watch(isDark, (dark) => {
    document.documentElement.classList.toggle('dark', dark)
    localStorage.setItem('theme', dark ? 'dark' : 'light')
    // 设置 Element Plus 暗色 CSS 变量
    if (dark) {
      document.documentElement.style.setProperty('--el-bg-color', '#1a1b2e')
      document.documentElement.style.setProperty('--el-text-color-primary', '#e0e0e0')
    } else {
      document.documentElement.style.setProperty('--el-bg-color', '#ffffff')
      document.documentElement.style.setProperty('--el-text-color-primary', '#303133')
    }
  })

  // 初始化
  if (isDark.value) {
    document.documentElement.classList.add('dark')
  }

  function toggle() {
    isDark.value = !isDark.value
  }

  return { isDark, toggle }
})
