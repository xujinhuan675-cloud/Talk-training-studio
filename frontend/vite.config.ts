import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

const DEFAULT_API_URL = 'http://127.0.0.1:8012'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiUrl = env.VITE_API_URL || DEFAULT_API_URL
  const apiProxy = {
    target: apiUrl,
    changeOrigin: true,
    ws: true,
  }

  if (!env.VITE_API_URL) {
    console.warn(
      `[vite] VITE_API_URL is not set; proxying /api and /health to ${apiUrl}. Run ../start-dev.cmd to sync local env files.`,
    )
  }

  return {
    plugins: [react()],
    server: {
      proxy: {
        '/api': apiProxy,
        '/health': apiProxy,
      },
    },
  }
})
