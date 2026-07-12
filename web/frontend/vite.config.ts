import path from 'node:path'
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  test: {
    // The suite covers the pure derivation modules in src/lib — geometry,
    // trend maths, maintenance rules. No DOM, no network, so 'node' keeps it
    // fast and keeps a jsdom dependency out of CI.
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
})
