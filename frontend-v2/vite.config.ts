import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath } from 'node:url'

const fromProjectRoot = (path: string) => fileURLToPath(new URL(path, import.meta.url))

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  build: {
    rollupOptions: {
      input: {
        main: fromProjectRoot('./index.html'),
        wordAddin: fromProjectRoot('./word-addin/taskpane.html')
      }
    }
  },
  resolve: {
    extensions: ['.ts', '.tsx', '.vue', '.mjs', '.js', '.json'],
    alias: {
      '@': fromProjectRoot('./src')
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
