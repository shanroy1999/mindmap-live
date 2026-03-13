import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // REST API calls proxied to the FastAPI backend
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      // WebSocket connections proxied to the FastAPI backend
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
})
