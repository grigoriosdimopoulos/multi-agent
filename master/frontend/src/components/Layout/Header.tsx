import { Wifi, WifiOff } from 'lucide-react'

interface HeaderProps {
  title: string
  connected: boolean
  agentCount: number
}

export function Header({ title, connected, agentCount }: HeaderProps) {
  return (
    <header className="h-14 flex items-center justify-between px-4 border-b border-gray-800 bg-gray-900 shrink-0">
      <h1 className="font-semibold text-white">{title}</h1>
      <div className="flex items-center gap-3 text-sm text-gray-400">
        <span>{agentCount} agent{agentCount !== 1 ? 's' : ''}</span>
        <span className={`flex items-center gap-1 ${connected ? 'text-green-400' : 'text-red-400'}`}>
          {connected ? <Wifi size={14} /> : <WifiOff size={14} />}
          {connected ? 'Live' : 'Disconnected'}
        </span>
      </div>
    </header>
  )
}
