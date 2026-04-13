import type {
  Agent,
  Chain,
  Task,
  NodeInfo,
  KnowledgeCollection,
} from '../types'

const BASE = '/api'

function headers(): HeadersInit {
  const key = localStorage.getItem('api_key') ?? ''
  return key ? { 'Content-Type': 'application/json', 'X-API-Key': key } : { 'Content-Type': 'application/json' }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { ...init, headers: { ...headers(), ...init?.headers } })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail ?? `HTTP ${res.status}`)
  }
  return res.json()
}

// ---- Agents ----
export const api = {
  // Agents
  listAgents: () => req<Agent[]>('/agents/'),
  getAgent:   (id: string) => req<Agent>(`/agents/${id}`),
  createAgent:(body: unknown) => req<Agent>('/agents/', { method: 'POST', body: JSON.stringify(body) }),
  deleteAgent:(id: string) => req<void>(`/agents/${id}`, { method: 'DELETE' }),

  // Chains
  listChains:  () => req<Chain[]>('/chains/'),
  createChain: (body: unknown) => req<Chain>('/chains/', { method: 'POST', body: JSON.stringify(body) }),

  // Tasks
  listTasks:  (status?: string) => req<Task[]>(`/tasks/${status ? `?status=${status}` : ''}`),
  getTask:    (id: string) => req<Task>(`/tasks/${id}`),
  submitTask: (body: unknown) => req<Task>('/tasks/', { method: 'POST', body: JSON.stringify(body) }),

  // Nodes
  listNodes: () => req<NodeInfo[]>('/nodes/'),

  // Knowledge
  listCollections: () => req<KnowledgeCollection[]>('/knowledge/collections'),
  deleteCollection:(name: string) => req<void>(`/knowledge/collections/${name}`, { method: 'DELETE' }),
  ingestFile:(file: File, collection: string) => {
    const form = new FormData()
    form.append('file', file)
    form.append('collection', collection)
    const key = localStorage.getItem('api_key') ?? ''
    return fetch(`${BASE}/knowledge/ingest/file`, {
      method: 'POST',
      headers: key ? { 'X-API-Key': key } : {},
      body: form,
    }).then(r => r.json())
  },
  queryKnowledge:(query: string, collection = 'default', n = 5) =>
    req<{ results: unknown[] }>('/knowledge/query', {
      method: 'POST',
      body: JSON.stringify({ query, collection, n_results: n }),
    }),

  // Chat (non-streaming)
  chat:(body: unknown) => req<{ task_id: string; content: string; status: string }>('/chat/', {
    method: 'POST',
    body: JSON.stringify(body),
  }),

  // Health
  health: () => req<{ status: string; agents: number; ws_connections: number }>('/health').catch(() => null),
}
