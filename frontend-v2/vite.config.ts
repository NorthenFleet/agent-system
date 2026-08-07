import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  resolve: {
    extensions: ['.ts', '.tsx', '.vue', '.mjs', '.js', '.json'],
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
  }
})
