import { useState, useEffect } from 'react'
import { Wifi, WifiOff } from 'lucide-react'

interface HeaderProps {
  title: string
  connected: boolean
  agentCount: number
}

const LS_KEY = 'api_key'

export function Header({ title, connected, agentCount }: HeaderProps) {
  const [apiKey, setApiKey] = useState('')
  const [apiKeyRequired, setApiKeyRequired] = useState(false)

  useEffect(() => {
    setApiKey(() => localStorage.getItem(LS_KEY) ?? '')
  }, [])

  useEffect(() => {
    fetch('/api/health')
      .then(async r => {
        if (r.status === 401) {
          setApiKeyRequired(true)
          return
        }
        if (!r.ok) return
        const data = (await r.json()) as { api_key_required?: boolean }
        setApiKeyRequired(Boolean(data.api_key_required))
      })
      .catch(() => {})
  }, [])

  function persistApiKey(value: string) {
    setApiKey(value)
    if (value.trim()) localStorage.setItem(LS_KEY, value.trim())
    else localStorage.removeItem(LS_KEY)
  }

  return (
    <header className="h-14 flex items-center justify-between gap-3 px-4 border-b border-gray-800 bg-gray-900 shrink-0">
      <h1 className="font-semibold text-white shrink-0">{title}</h1>
      <div className="flex items-center gap-3 min-w-0 flex-1 justify-end">
        {apiKeyRequired && (
          <label className="flex items-center gap-2 min-w-0 flex-1 max-w-[9rem] sm:max-w-[14rem] text-xs text-gray-500">
            <span className="shrink-0">API key</span>
            <input
              type="password"
              autoComplete="off"
              placeholder="MASTER_API_KEYS"
              value={apiKey}
              onChange={e => persistApiKey(e.target.value)}
              className="w-full min-w-0 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-gray-200 placeholder:text-gray-600"
            />
          </label>
        )}
        <span className="text-sm text-gray-400 shrink-0">{agentCount} agent{agentCount !== 1 ? 's' : ''}</span>
        <span className={`flex items-center gap-1 shrink-0 text-sm ${connected ? 'text-green-400' : 'text-red-400'}`}>
          {connected ? <Wifi size={14} /> : <WifiOff size={14} />}
          {connected ? 'Live' : 'Disconnected'}
        </span>
      </div>
    </header>
  )
}
