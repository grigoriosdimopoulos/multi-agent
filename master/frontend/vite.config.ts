import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import http from 'node:http'
import type { IncomingMessage } from 'node:http'

/**
 * Vite's default `/api` http-proxy often buffers streaming POST bodies, so SSE never
 * arrives incrementally. This middleware pipes `/api/chat` directly — same origin as
 * the dev UI (no CORS) and true streaming.
 */
function streamingChatProxy(apiPort: number): Plugin {
  return {
    name: 'streaming-chat-proxy',
    enforce: 'pre',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const url = req.url ?? ''
        if (!url.startsWith('/api/chat') || req.method !== 'POST') {
          return next()
        }

        const forwardHeaders = (incoming: IncomingMessage): http.OutgoingHttpHeaders => {
          const out: http.OutgoingHttpHeaders = {}
          for (const [k, v] of Object.entries(incoming.headers)) {
            const key = k.toLowerCase()
            if (
              [
                'connection',
                'keep-alive',
                'proxy-authenticate',
                'proxy-authorization',
                'te',
                'trailer',
                'transfer-encoding',
                'upgrade',
              ].includes(key)
            ) {
              continue
            }
            if (v !== undefined) out[key] = v
          }
          out.host = `127.0.0.1:${apiPort}`
          return out
        }

        const proxyReq = http.request(
          {
            hostname: '127.0.0.1',
            port: apiPort,
            path: url,
            method: 'POST',
            headers: forwardHeaders(req as IncomingMessage),
          },
          (proxyRes) => {
            res.writeHead(proxyRes.statusCode ?? 502, proxyRes.headers)
            proxyRes.pipe(res, { end: true })
          }
        )

        proxyReq.on('error', (err) => {
          if (!res.headersSent) {
            res.statusCode = 502
            res.setHeader('content-type', 'application/json')
            res.end(
              JSON.stringify({
                detail: `Dev chat proxy: cannot reach API on 127.0.0.1:${apiPort} (${err.message}). Start uvicorn.`,
              })
            )
          } else {
            res.end()
          }
        })

        ;(req as IncomingMessage).pipe(proxyReq, { end: true })
      })
    },
  }
}

const API_PORT = Number(process.env.VITE_API_PORT || process.env.API_PORT || 8000)

export default defineConfig({
  plugins: [streamingChatProxy(API_PORT), react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: `http://127.0.0.1:${API_PORT}`, changeOrigin: true },
      '/ws': { target: `ws://127.0.0.1:${API_PORT}`, ws: true },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
})
