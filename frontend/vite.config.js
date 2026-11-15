import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

function cesiumAssetsPlugin() {
  return {
    name: 'copy-cesium-assets',
    buildStart() {
      const src = path.resolve(__dirname, 'node_modules/cesium/Build/Cesium')
      const dest = path.resolve(__dirname, 'public/cesium')
      const dirs = ['Assets', 'Workers', 'ThirdParty', 'Widgets']
      for (const dir of dirs) {
        const target = path.join(dest, dir)
        if (!fs.existsSync(target)) {
          fs.cpSync(path.join(src, dir), target, { recursive: true })
        }
      }
    }
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), cesiumAssetsPlugin()],
  server: {
    host: '127.0.0.1',
    proxy: {
      '/api': {
        target: 'https://harmonization-of-modis-and-viirs-hot-ccxf.onrender.com',
        changeOrigin: true,
        rewrite: (requestPath) => requestPath.replace(/^\/api/, ''),
      },
    },
    fs: {
      allow: [__dirname, path.resolve(__dirname, '../data/boundaries')],
    },
  },
})
