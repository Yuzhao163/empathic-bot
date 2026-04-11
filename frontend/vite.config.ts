import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: process.env.VITE_GATEWAY_URL || 'http://localhost:8080',
        changeOrigin: true,
        rewrite: (path) => path,
      },
      '/ws': {
        target: process.env.VITE_GATEWAY_URL || 'http://localhost:8080',
        ws: true,
      },
    },
  },
  define: {
    'process.env.VITE_GATEWAY_URL': JSON.stringify(process.env.VITE_GATEWAY_URL || 'http://localhost:8080'),
  },
})
