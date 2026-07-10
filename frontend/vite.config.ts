import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // 127.0.0.1 (not localhost) so the proxy never resolves to an IPv6 listener
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
})
