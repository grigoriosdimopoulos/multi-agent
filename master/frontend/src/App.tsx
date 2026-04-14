import { useState, useEffect, useCallback, useRef } from 'react'
import { Sidebar } from './components/Layout/Sidebar'
import { Header } from './components/Layout/Header'
import { ChatWindow } from './components/Chat/ChatWindow'
import { AgentPanel } from './components/Agents/AgentPanel'
import { NodeMap } from './components/Nodes/NodeMap'
import { TaskQueue } from './components/Tasks/TaskQueue'
import { KnowledgeUpload } from './components/Knowledge/KnowledgeUpload'
import { useWebSocket } from './hooks/useWebSocket'
import type { Agent, Chain, Task, NodeInfo, KnowledgeCollection, Notification, View } from './types'
import { api } from './api/client'

const SESSION_ID = Math.random().toString(36).slice(2)

const VIEW_TITLES: Record<View, string> = {
  chat: 'Chat', agents: 'Agents', nodes: 'Nodes',
  tasks: 'Tasks', knowledge: 'Knowledge',
}

export default function App() {
  const [view, setView] = useState<View>('chat')
  const [agents, setAgents] = useState<Agent[]>([])
  const [chains, setChains] = useState<Chain[]>([])
  const [tasks, setTasks] = useState<Task[]>([])
  const [nodes, setNodes] = useState<NodeInfo[]>([])
  const [collections, setCollections] = useState<KnowledgeCollection[]>([])
  const [notifications, setNotifications] = useState<Notification[]>([])
  const [showNotifications, setShowNotifications] = useState(false)
  const [streamingTokens] = useState(new Map<string, string>())

  // ---------- Data loaders ----------
  const loadAgents      = useCallback(() => api.listAgents().then(setAgents).catch(console.error), [])
  const loadChains      = useCallback(() => api.listChains().then(setChains).catch(console.error), [])
  const loadTasks       = useCallback(() => api.listTasks().then(setTasks).catch(console.error), [])
  const loadNodes       = useCallback(() => api.listNodes().then(setNodes).catch(console.error), [])
  const loadCollections = useCallback(() => api.listCollections().then(setCollections).catch(console.error), [])

  useEffect(() => {
    loadAgents(); loadChains(); loadTasks(); loadNodes(); loadCollections()
    const interval = setInterval(() => { loadNodes(); loadTasks() }, 10_000)
    return () => clearInterval(interval)
  }, [loadAgents, loadChains, loadTasks, loadNodes, loadCollections])

  // ---------- WebSocket ----------
  const { connected } = useWebSocket(SESSION_ID, useCallback((msg) => {
    if (msg.type === 'task_update' && msg.data) {
      const updated = msg.data as unknown as Task
      setTasks(prev => {
        const idx = prev.findIndex(t => t.task_id === updated.task_id)
        if (idx >= 0) { const next = [...prev]; next[idx] = updated; return next }
        return [updated, ...prev]
      })
    } else if (msg.type === 'notification' && msg.data) {
      const n: Notification = {
        event_id: Math.random().toString(36).slice(2),
        type: (msg.data as any).type ?? 'info',
        message: (msg.data as any).message ?? '',
        data: msg.data as Record<string, unknown>,
        timestamp: new Date().toISOString(),
      }
      setNotifications(prev => [n, ...prev.slice(0, 49)])
    } else if (msg.type === 'token' && msg.task_id && msg.token) {
      streamingTokens.set(msg.task_id, (streamingTokens.get(msg.task_id) ?? '') + msg.token)
    } else if (msg.type === 'agent_update') {
      loadAgents()
    }
  }, [loadAgents, streamingTokens]))

  function markAllRead() {
    setNotifications(prev => prev.map(n => ({ ...n, read: true })))
    setShowNotifications(false)
  }

  return (
    <div className="flex h-full overflow-hidden">
      <Sidebar
        current={view}
        onChange={setView}
        notifications={notifications}
        onNotificationsClick={() => setShowNotifications(s => !s)}
      />

      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <Header title={VIEW_TITLES[view]} connected={connected} agentCount={agents.length} />

        <main className="flex-1 overflow-hidden">
          {view === 'chat'      && <ChatWindow agents={agents} chains={chains} streamingTokens={streamingTokens} sessionId={SESSION_ID} />}
          {view === 'agents'    && <AgentPanel agents={agents} onRefresh={loadAgents} />}
          {view === 'nodes'     && <NodeMap nodes={nodes} agents={agents} onRefresh={loadNodes} />}
          {view === 'tasks'     && <TaskQueue tasks={tasks} nodes={nodes} agents={agents} onRefresh={loadTasks} />}
          {view === 'knowledge' && <KnowledgeUpload collections={collections} onRefresh={loadCollections} />}
        </main>
      </div>

      {/* Notification drawer */}
      {showNotifications && (
        <div className="absolute right-0 top-14 w-80 max-h-[70vh] bg-gray-900 border border-gray-700 rounded-xl shadow-xl overflow-hidden z-50 flex flex-col">
          <div className="flex justify-between items-center p-3 border-b border-gray-800">
            <span className="font-medium text-white text-sm">Notifications</span>
            <button onClick={markAllRead} className="text-xs text-brand-400 hover:text-brand-300">Mark all read</button>
          </div>
          <div className="overflow-y-auto">
            {notifications.length === 0
              ? <p className="text-center text-gray-500 text-sm py-6">No notifications</p>
              : notifications.map(n => (
                <div key={n.event_id} className={`p-3 border-b border-gray-800 text-sm ${n.read ? 'opacity-50' : ''}`}>
                  <p className="text-white">{n.message}</p>
                  <p className="text-[10px] text-gray-500 mt-0.5">{new Date(n.timestamp).toLocaleTimeString()}</p>
                </div>
              ))
            }
          </div>
        </div>
      )}
    </div>
  )
}
