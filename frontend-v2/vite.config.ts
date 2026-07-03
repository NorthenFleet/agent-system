import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src')
    }
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:3021',
        changeOrigin: true
      },
      '/ws': {
        target: 'ws://localhost:3021',
        ws: true
      }
    }
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined
          if (id.includes('/vue/') || id.includes('/vue-router/') || id.includes('/pinia/')) {
            return 'vendor-vue'
          }
          if (id.includes('/@element-plus/icons-vue/')) {
            return 'vendor-element-icons'
          }
          if (id.includes('/element-plus/es/components/')) {
            return 'vendor-element-components'
          }
          if (id.includes('/element-plus/') || id.includes('/@element-plus/')) {
            return 'vendor-element-core'
          }
          if (id.includes('node_modules/zrender')) {
            return 'vendor-zrender'
          }
          if (id.includes('node_modules/echarts/lib/chart/')) {
            return 'vendor-echarts-charts'
          }
          if (id.includes('node_modules/echarts/lib/component/')) {
            return 'vendor-echarts-components'
          }
          if (id.includes('node_modules/echarts/lib/coord/')) {
            return 'vendor-echarts-coord'
          }
          if (id.includes('node_modules/echarts/lib/data/')) {
            return 'vendor-echarts-data'
          }
          if (id.includes('node_modules/echarts/lib/renderer/')) {
            return 'vendor-echarts-renderer'
          }
          if (id.includes('node_modules/echarts/lib/scale/')) {
            return 'vendor-echarts-scale'
          }
          if (id.includes('node_modules/echarts/lib/util/')) {
            return 'vendor-echarts-util'
          }
          if (id.includes('node_modules/echarts/lib/')) {
            return 'vendor-echarts-core'
          }
          if (id.includes('/echarts/') || id.includes('/vue-echarts/')) {
            return 'vendor-echarts'
          }
          return 'vendor'
        }
      }
    }
  }
})
