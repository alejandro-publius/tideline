import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // 127.0.0.1 (not localhost) so the proxy never resolves to an IPv6 listener
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
  build: {
    rollupOptions: {
      output: {
        // long-lived vendor chunks cache independently of app code changes
        manualChunks(id: string) {
          if (!id.includes('node_modules')) return undefined
          if (id.includes('recharts') || id.includes('d3-')) return 'recharts'
          if (id.includes('leaflet')) return 'leaflet' // before react: react-leaflet matches both
          if (id.includes('react')) return 'react'
          return 'vendor'
        },
      },
    },
  },
})
