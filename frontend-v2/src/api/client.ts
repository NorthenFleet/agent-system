import axios, { type AxiosError } from 'axios'
import { ElMessage } from 'element-plus'

declare module 'axios' {
  export interface AxiosRequestConfig {
    suppressErrorToast?: boolean
  }
}

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

    // Some callers render their own local fallback (for example a missing
    // document image).  They still receive the rejected promise, but a single
    // optional asset must not make the whole workspace look as if it failed.
    if (error.config?.suppressErrorToast && status !== 401 && status !== 403) {
      return Promise.reject(error)
    }

    if (status === 401) {
      const developmentMode = localStorage.getItem('auth_login_enabled') === 'false'
      localStorage.removeItem('jwt_token')
      localStorage.removeItem('jwt_refresh_token')
      localStorage.removeItem('jwt_auth_mode')
      ElMessage.warning(developmentMode ? '开发会话已失效，请刷新页面' : '登录已过期，请重新登录')
      if (!developmentMode && window.location.pathname !== '/login') {
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
