import { useEffect, useRef, useCallback, useState } from 'react'

export interface WSMessage {
  type: 'token' | 'task_update' | 'notification' | 'agent_update' | 'pong'
  task_id?: string
  token?: string
  data?: Record<string, unknown>
  action?: string
}

export function useWebSocket(sessionId: string, onMessage: (msg: WSMessage) => void) {
  const ws = useRef<WebSocket | null>(null)
  const [connected, setConnected] = useState(false)
  const reconnectTimer = useRef<number | null>(null)
  const onMessageRef = useRef(onMessage)
  onMessageRef.current = onMessage

  const connect = useCallback(() => {
    const protocol = location.protocol === 'https:' ? 'wss' : 'ws'
    const url = `${protocol}://${location.host}/ws/${sessionId}`
    const socket = new WebSocket(url)

    socket.onopen = () => {
      setConnected(true)
      // Start ping interval
      const ping = setInterval(() => {
        if (socket.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify({ type: 'ping' }))
        }
      }, 25_000)
      ;(socket as any)._pingInterval = ping
    }

    socket.onmessage = (e) => {
      try {
        const msg: WSMessage = JSON.parse(e.data)
        onMessageRef.current(msg)
      } catch {/* ignore parse errors */}
    }

    socket.onclose = () => {
      setConnected(false)
      clearInterval((socket as any)._pingInterval)
      // Reconnect after 3 seconds
      reconnectTimer.current = window.setTimeout(connect, 3000)
    }

    socket.onerror = () => socket.close()

    ws.current = socket
  }, [sessionId])

  useEffect(() => {
    connect()
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
      ws.current?.close()
    }
  }, [connect])

  return { connected }
}
