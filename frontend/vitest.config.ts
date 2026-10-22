import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  base: '/resume/',
  plugins: [vue()],
  test: { environment: 'jsdom', include: ['src/**/*.test.ts'], restoreMocks: true },
})
