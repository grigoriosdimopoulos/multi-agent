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

export type TaskStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'

export interface Task {
  task_id: string
  status: TaskStatus
  agent_id?: string
  chain_id?: string
  node_id?: string
  input: string
  output?: string
  error?: string
  created_at: string
  completed_at?: string
  iterations: number
  subtask_ids: string[]
  required_tools: string[]
  privilege_level: number
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
  agent_configs: AgentConfig[]      // full agent config objects
  capabilities: Record<string, string>
  last_seen: string
  tasks_completed: number
  tasks_running: number
}

/** Subset of agent config used for node configuration (matches agents.yaml format) */
export interface AgentConfig {
  name: string
  description?: string
  provider: {
    type: ProviderType
    model: string
    api_key?: string
    base_url?: string
  }
  tools?: string[]
  system_prompt?: string
  temperature?: number
  max_tokens?: number
  privilege_level?: number
  knowledge_collection?: string
  tags?: string[]
}

export interface NodeConfigUpdate {
  agents: AgentConfig[]
  chains?: ChainConfig[]
  allowed_tools?: string[]
}

export interface ChainConfig {
  chain_id?: string
  mode: 'sequential' | 'parallel' | 'router'
  agent_ids: string[]
  merge_agent_id?: string
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
