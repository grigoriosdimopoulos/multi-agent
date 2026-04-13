export type ProviderType = 'ollama' | 'openai' | 'anthropic' | 'groq'

export interface ProviderConfig {
  type: ProviderType
  model: string
  api_key?: string
  base_url?: string
}

export interface Agent {
  id: string
  name: string
  description: string
  provider: ProviderConfig
  tools: string[]
  privilege_level: number
  tags: string[]
  status: 'active' | 'inactive'
}

export interface Chain {
  chain_id: string
  mode: 'sequential' | 'parallel' | 'router'
  steps: string[]
}

export type TaskStatus = 'pending' | 'running' | 'completed' | 'failed'

export interface Task {
  task_id: string
  status: TaskStatus
  agent_id?: string
  chain_id?: string
  input: string
  output?: string
  error?: string
  created_at: string
  completed_at?: string
  iterations: number
  subtask_ids: string[]
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp: string
  taskId?: string
  streaming?: boolean
}

export interface NodeInfo {
  node_id: string
  host: string
  port: number
  status: 'active' | 'offline'
  agent_ids: string[]
  capabilities: Record<string, string>
  last_seen: string
}

export interface Notification {
  event_id: string
  type: string
  message: string
  data: Record<string, unknown>
  timestamp: string
  read?: boolean
}

export interface KnowledgeCollection {
  name: string
  count: number
}

export type View = 'chat' | 'agents' | 'nodes' | 'tasks' | 'knowledge'
