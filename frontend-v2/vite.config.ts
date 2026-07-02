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
    port: 3021,
    proxy: {
      '/api': {
        target: 'http://localhost:3020',
        changeOrigin: true
      },
      '/ws': {
        target: 'ws://localhost:3020',
        ws: true
      }
    }
  }
})
