import axios, { type AxiosError } from 'axios'
import { ElMessage } from 'element-plus'

const apiClient = axios.create({
  baseURL: '',
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// 请求拦截器：自动附加 JWT Token
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('jwt_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

// 响应拦截器：统一错误处理
apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    const status = error.response?.status

    if (status === 401) {
      // Token 过期或无效 → 清除并跳转登录
      localStorage.removeItem('jwt_token')
      ElMessage.warning('登录已过期，请重新登录')
      // 避免重复跳转
      if (window.location.pathname !== '/login') {
        window.location.href = '/login'
      }
    } else if (status === 403) {
      ElMessage.error('权限不足，无法访问该资源')
    } else if (status === 500) {
      ElMessage.error('服务器内部错误，请稍后重试')
    } else if (status === 404) {
      ElMessage.warning('请求的资源不存在')
    } else if (error.code === 'ECONNABORTED') {
      ElMessage.error('请求超时，请检查网络连接')
    } else if (!error.response) {
      // 网络错误
      ElMessage.error('网络连接失败，请检查网络设置')
    } else {
      // 其他错误：展示后端返回的消息（如有）
      const msg = (error.response?.data as any)?.detail || '请求失败，请稍后重试'
      ElMessage.error(msg)
    }

    return Promise.reject(error)
  }
)

export default apiClient
