import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath, URL } from 'node:url'

const apiTarget = process.env.STOCKLLM_DEV_API_URL ?? 'http://127.0.0.1:8768'
const frontendPort = Number.parseInt(process.env.STOCKLLM_DEV_FRONTEND_PORT ?? '5173', 10)
if (!Number.isInteger(frontendPort) || frontendPort < 1 || frontendPort > 65_535) {
  throw new Error('STOCKLLM_DEV_FRONTEND_PORT must be a valid TCP port.')
}

function vendorChunkName(id: string) {
  if (!id.includes('/node_modules/')) return undefined
  if (id.includes('/node_modules/@base-ui/') || id.includes('/node_modules/lucide-react/')) return 'ui-vendor'
  if (id.includes('/node_modules/react/') || id.includes('/node_modules/react-dom/') || id.includes('/node_modules/scheduler/')) return 'react-vendor'
  if (id.includes('/@tanstack/')) return 'query-vendor'
  if (id.includes('/motion/') || id.includes('/motion-dom/')) return 'motion-vendor'
  if (id.includes('/lightweight-charts/')) return 'charts-vendor'
  if (id.includes('/react-markdown/') || id.includes('/remark-') || id.includes('/micromark') || id.includes('/unified/')) return 'markdown-vendor'
  return undefined
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
  build: {
    rollupOptions: {
      output: {
        manualChunks: vendorChunkName,
      },
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
