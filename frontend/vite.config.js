import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/score': 'http://localhost:8000',
      '/auth': 'http://localhost:8000',
      '/alerts': 'http://localhost:8000',
      '/dashboard': 'http://localhost:8000',
      '/models': 'http://localhost:8000',
      '/compliance': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
      '/flag': 'http://localhost:8000',
      '/user': 'http://localhost:8000',
      '/blocklist': 'http://localhost:8000',
      '/smishing': 'http://localhost:8000',
      '/audit-log': 'http://localhost:8000',
    }
  }
})
