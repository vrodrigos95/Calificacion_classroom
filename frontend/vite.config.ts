import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// En desarrollo, /api se envía al backend. Así la cookie de sesión y el
// redirect de OAuth (http://localhost:5173/api/auth/callback) viven en el mismo origen.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: false },
    },
  },
})
