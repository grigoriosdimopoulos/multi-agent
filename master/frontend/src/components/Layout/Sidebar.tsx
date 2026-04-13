import { Bot, MessageSquare, Network, ListTodo, BookOpen, Bell } from 'lucide-react'
import type { View, Notification } from '../../types'
import clsx from 'clsx'

interface SidebarProps {
  current: View
  onChange: (v: View) => void
  notifications: Notification[]
  onNotificationsClick: () => void
}

const NAV: { id: View; label: string; Icon: typeof Bot }[] = [
  { id: 'chat',      label: 'Chat',      Icon: MessageSquare },
  { id: 'agents',    label: 'Agents',    Icon: Bot           },
  { id: 'nodes',     label: 'Nodes',     Icon: Network       },
  { id: 'tasks',     label: 'Tasks',     Icon: ListTodo      },
  { id: 'knowledge', label: 'Knowledge', Icon: BookOpen      },
]

export function Sidebar({ current, onChange, notifications, onNotificationsClick }: SidebarProps) {
  const unread = notifications.filter(n => !n.read).length

  return (
    <aside className="w-16 md:w-56 flex flex-col bg-gray-900 border-r border-gray-800 shrink-0">
      {/* Logo */}
      <div className="h-14 flex items-center px-4 border-b border-gray-800 gap-2">
        <span className="text-2xl">🤖</span>
        <span className="hidden md:block font-bold text-sm text-white truncate">Multi-Agent AI</span>
      </div>

      {/* Nav */}
      <nav className="flex-1 py-3 space-y-1 px-2">
        {NAV.map(({ id, label, Icon }) => (
          <button
            key={id}
            onClick={() => onChange(id)}
            className={clsx(
              'w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors',
              current === id
                ? 'bg-brand-600 text-white'
                : 'text-gray-400 hover:bg-gray-800 hover:text-white'
            )}
          >
            <Icon size={18} />
            <span className="hidden md:block">{label}</span>
          </button>
        ))}
      </nav>

      {/* Notifications bell */}
      <div className="px-2 pb-4">
        <button
          onClick={onNotificationsClick}
          className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium text-gray-400 hover:bg-gray-800 hover:text-white transition-colors relative"
        >
          <Bell size={18} />
          <span className="hidden md:block">Alerts</span>
          {unread > 0 && (
            <span className="absolute top-1 right-1 md:right-3 w-4 h-4 flex items-center justify-center text-[10px] bg-red-500 text-white rounded-full">
              {unread > 9 ? '9+' : unread}
            </span>
          )}
        </button>
      </div>
    </aside>
  )
}
