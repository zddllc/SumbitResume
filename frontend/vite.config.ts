import vue from '@vitejs/plugin-vue'
import { defineConfig, loadEnv } from 'vite'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const base = process.env.VITE_BASE_PATH || env.VITE_BASE_PATH || '/resume/'
  if (!base.startsWith('/') || !base.endsWith('/') || /[?#\\%\s]/.test(base) ||
      base.includes('//') || base.split('/').some(part => part === '.' || part === '..')) {
    throw new Error('VITE_BASE_PATH must be an absolute URL prefix ending in /')
  }
  const proxy = {
    [`${base}api/`]: { target: process.env.API_PROXY_TARGET || env.API_PROXY_TARGET || 'http://127.0.0.1:8000' },
  }
  return {
    base, plugins: [vue()],
    server: { host: '127.0.0.1', proxy },
    preview: { host: '127.0.0.1', proxy },
    build: { outDir: 'dist' },
  }
})
