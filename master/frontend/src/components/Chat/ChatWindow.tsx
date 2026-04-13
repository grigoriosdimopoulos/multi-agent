import { useState, useRef, useEffect, useCallback } from 'react'
import type { ChatMessage, Agent, Chain } from '../../types'
import { MessageBubble } from './MessageBubble'
import { InputBar } from './InputBar'
// Simple UUID without crypto dependency
function uid() { return Math.random().toString(36).slice(2) + Date.now().toString(36) }

interface Props {
  agents: Agent[]
  chains: Chain[]
  streamingTokens: Map<string, string>  // taskId → accumulated tokens
  sessionId: string
}

export function ChatWindow({ agents, chains, streamingTokens, sessionId }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: uid(),
      role: 'system',
      content: '👋 Welcome! Choose an agent and start chatting, or submit a task.',
      timestamp: new Date().toISOString(),
    },
  ])
  const [selectedAgentId, setSelectedAgentId] = useState<string>('')
  const [selectedChainId, setSelectedChainId] = useState<string>('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  /** Batches SSE token updates to one setState per animation frame (fewer React repaints). */
  const streamFlushRafRef = useRef<number | null>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Apply streaming tokens to the streaming message
  useEffect(() => {
    streamingTokens.forEach((tokens, taskId) => {
      setMessages(prev =>
        prev.map(m =>
          m.taskId === taskId ? { ...m, content: tokens, streaming: true } : m
        )
      )
    })
  }, [streamingTokens])

  const sendMessage = useCallback(async (text: string) => {
    if (!text.trim() || loading) return

    const userMsg: ChatMessage = {
      id: uid(),
      role: 'user',
      content: text,
      timestamp: new Date().toISOString(),
    }
    setMessages(prev => [...prev, userMsg])
    setLoading(true)

    const taskId = uid()
    const placeholder: ChatMessage = {
      id: uid(),
      role: 'assistant',
      content: '',
      timestamp: new Date().toISOString(),
      taskId,
      streaming: true,
    }
    setMessages(prev => [...prev, placeholder])

    if (streamFlushRafRef.current != null) {
      cancelAnimationFrame(streamFlushRafRef.current)
      streamFlushRafRef.current = null
    }

    try {
      // Same-origin `/api` in dev (Vite streams chat via middleware) and in prod (FastAPI).
      const key = localStorage.getItem('api_key') ?? ''
      const res = await fetch('/api/chat/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(key ? { 'X-API-Key': key } : {}),
        },
        body: JSON.stringify({
          message: text,
          agent_id: selectedAgentId || undefined,
          chain_id: selectedChainId || undefined,
          session_id: sessionId,
          stream: true,
        }),
      })

      if (!res.ok) {
        const text = await res.text()
        let msg = `HTTP ${res.status}`
        try {
          const j = JSON.parse(text) as { detail?: string }
          if (typeof j.detail === 'string') msg = j.detail
        } catch {
          /* ignore */
        }
        if (res.status === 401) {
          msg +=
            ' Use the Key field in the header (same value as MASTER_API_KEYS in .env), or remove/empty MASTER_API_KEYS for open local dev.'
        }
        throw new Error(msg)
      }
      if (!res.body) throw new Error('No response body')

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let accumulated = ''
      let lineBuf = ''
      let sawDone = false

      const applyError = (msg: string) => {
        if (streamFlushRafRef.current != null) {
          cancelAnimationFrame(streamFlushRafRef.current)
          streamFlushRafRef.current = null
        }
        setMessages(prev =>
          prev.map(m =>
            m.taskId === taskId
              ? { ...m, content: msg, streaming: false }
              : m
          )
        )
      }

      const processSseLine = (line: string) => {
        if (!line.startsWith('data:')) return
        const raw = line.slice(5).trimStart()
        if (!raw) return
        let ev: { event?: string; token?: string; error?: string; task_id?: string; tool?: string; arguments?: Record<string, unknown> }
        try {
          ev = JSON.parse(raw)
        } catch {
          return
        }
        if (ev.event === 'error') {
          applyError(ev.error ?? 'Unknown error')
          sawDone = true
          return
        }
        if (ev.event === 'thinking' && ev.tool) {
          const argStr = ev.arguments ? ` ${JSON.stringify(ev.arguments)}` : ''
          accumulated += `\n> **Tool:** \`${ev.tool}\`${argStr}\n\n`
          setMessages(prev =>
            prev.map(m => (m.taskId === taskId ? { ...m, content: accumulated } : m))
          )
          return
        }
        if (ev.event === 'token' && typeof ev.token === 'string') {
          accumulated += ev.token
          if (streamFlushRafRef.current == null) {
            streamFlushRafRef.current = requestAnimationFrame(() => {
              streamFlushRafRef.current = null
              const t = accumulated
              setMessages(prev =>
                prev.map(m => (m.taskId === taskId ? { ...m, content: t } : m))
              )
            })
          }
        } else if (ev.event === 'done') {
          if (streamFlushRafRef.current != null) {
            cancelAnimationFrame(streamFlushRafRef.current)
            streamFlushRafRef.current = null
          }
          sawDone = true
          setMessages(prev =>
            prev.map(m =>
              m.taskId === taskId
                ? {
                    ...m,
                    content: accumulated || '(empty reply)',
                    streaming: false,
                  }
                : m
            )
          )
        }
      }

      while (true) {
        const { done, value } = await reader.read()
        lineBuf += decoder.decode(value ?? new Uint8Array(), { stream: !done })
        const lines = lineBuf.split('\n')
        lineBuf = lines.pop() ?? ''
        for (const line of lines) {
          processSseLine(line)
        }
        if (done) {
          if (lineBuf) processSseLine(lineBuf)
          break
        }
      }

      if (!sawDone) {
        applyError(
          'Stream ended unexpectedly. If using local models, run Ollama and: ollama pull llama3.2'
        )
      }
    } catch (err: unknown) {
      const raw = err instanceof Error ? err.message : String(err)
      const msg =
        raw === 'Failed to fetch'
          ? 'Could not reach the API. Start the backend on port 8000 (uvicorn) and keep Vite dev running.'
          : raw
      setMessages(prev =>
        prev.map(m =>
          m.taskId === taskId
            ? { ...m, content: `Error: ${msg}`, streaming: false }
            : m
        )
      )
    } finally {
      setLoading(false)
    }
  }, [loading, selectedAgentId, selectedChainId, sessionId])

  return (
    <div className="flex flex-col h-full">
      {/* Agent / Chain selector bar */}
      <div className="flex gap-2 p-3 border-b border-gray-800 bg-gray-900">
        <select
          value={selectedAgentId}
          onChange={e => { setSelectedAgentId(e.target.value); setSelectedChainId('') }}
          className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-white"
        >
          <option value="">Auto-select agent</option>
          {agents.map(a => (
            <option key={a.id} value={a.id}>{a.name} ({a.provider.type}/{a.provider.model})</option>
          ))}
        </select>
        <select
          value={selectedChainId}
          onChange={e => { setSelectedChainId(e.target.value); setSelectedAgentId('') }}
          className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-white"
        >
          <option value="">No chain</option>
          {chains.map(c => (
            <option key={c.chain_id} value={c.chain_id}>{c.chain_id} ({c.mode})</option>
          ))}
        </select>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map(msg => (
          <MessageBubble key={msg.id} message={msg} />
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <InputBar onSend={sendMessage} loading={loading} />
    </div>
  )
}
