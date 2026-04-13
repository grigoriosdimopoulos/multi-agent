import { useState, useRef, useEffect, useCallback } from 'react'
import type { ChatMessage, Agent, Chain } from '../../types'
import { MessageBubble } from './MessageBubble'
import { InputBar } from './InputBar'
import { api } from '../../api/client'
import { v4 as uuid } from 'crypto'

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

    try {
      // Use SSE for streaming
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

      if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`)

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let accumulated = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        const chunk = decoder.decode(value)
        for (const line of chunk.split('\n')) {
          if (!line.startsWith('data:')) continue
          try {
            const ev = JSON.parse(line.slice(5))
            if (ev.event === 'token') {
              accumulated += (ev.token as string).replace(/\\n/g, '\n')
              setMessages(prev =>
                prev.map(m => m.taskId === taskId ? { ...m, content: accumulated } : m)
              )
            } else if (ev.event === 'done') {
              setMessages(prev =>
                prev.map(m => m.taskId === taskId ? { ...m, streaming: false } : m)
              )
            }
          } catch {/* ignore */}
        }
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
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
