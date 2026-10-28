import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'
import fs from 'node:fs'
import { fileURLToPath } from 'node:url'
import type { Plugin } from 'vite'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

/** 开发时服务项目根目录下的 assets/ 静态文件（主题预览 HTML / 风格预览 webp 等） */
function serveRootAssets(): Plugin {
  const assetsRoot = path.resolve(__dirname, '../assets')
  const MIME: Record<string, string> = {
    '.html': 'text/html; charset=utf-8',
    '.webp': 'image/webp',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.svg': 'image/svg+xml',
    '.css': 'text/css',
    '.js': 'application/javascript',
    '.json': 'application/json',
  }
  return {
    name: 'serve-root-assets',
    configureServer(server) {
      server.middlewares.use('/assets', (req, res, next) => {
        const filePath = path.join(assetsRoot, req.url || '')
        if (!filePath.startsWith(assetsRoot)) {
          res.statusCode = 403
          res.end('Forbidden')
          return
        }
        try {
          if (fs.statSync(filePath).isFile()) {
            res.setHeader('Content-Type', MIME[path.extname(filePath)] || 'application/octet-stream')
            fs.createReadStream(filePath).pipe(res)
            return
          }
        } catch { /* not found, fall through */ }
        next()
      })
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss(), serveRootAssets()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    strictPort: false,
  },
})
