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
    // the `three` chunk is ~600 kB but lazy-loaded only when the globe mounts,
    // so it never touches first paint — the default 500 kB warning is noise here
    chunkSizeWarningLimit: 700,
    rollupOptions: {
      output: {
        // long-lived vendor chunks cache independently of app code changes
        manualChunks(id: string) {
          if (!id.includes('node_modules')) return undefined
          // three + the coastline data: a big chunk, but lazy-loaded with the globe
          if (id.includes('/three/') || id.includes('topojson') || id.includes('world-atlas'))
            return 'three'
          if (id.includes('recharts') || id.includes('d3-')) return 'recharts'
          if (id.includes('leaflet')) return 'leaflet' // before react: react-leaflet matches both
          if (id.includes('react')) return 'react'
          return 'vendor'
        },
      },
    },
  },
})
