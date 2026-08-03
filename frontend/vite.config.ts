import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath, URL } from 'node:url'

const apiTarget = process.env.STOCKLLM_DEV_API_URL ?? 'http://127.0.0.1:8768'
const frontendPort = Number.parseInt(process.env.STOCKLLM_DEV_FRONTEND_PORT ?? '5173', 10)
if (!Number.isInteger(frontendPort) || frontendPort < 1 || frontendPort > 65_535) {
  throw new Error('STOCKLLM_DEV_FRONTEND_PORT must be a valid TCP port.')
}

export default defineConfig({
  plugins: [react(), tailwindcss()],
  optimizeDeps: {
    include: ['@base-ui/react/alert-dialog'],
  },
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: frontendPort,
    strictPort: true,
    proxy: {
      '/api': apiTarget,
    },
  },
})
