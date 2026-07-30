import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined
          if (id.includes('leaflet') || id.includes('supercluster')) return 'maps'
          if (id.includes('/react/') || id.includes('/react-dom/') || id.includes('/scheduler/')) {
            return 'react'
          }
          return 'vendor'
        },
      },
    },
  },
  server: {
    port: 5173,
  },
  test: {
    environment: 'node',
  },
})
