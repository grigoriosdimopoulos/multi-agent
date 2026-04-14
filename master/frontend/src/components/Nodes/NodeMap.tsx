import { useState } from 'react'
import { Network, Cpu, Wifi, WifiOff, Settings, Plus, Trash2, X, ChevronDown, ChevronUp, Check, AlertCircle } from 'lucide-react'
import type { NodeInfo, Agent, AgentConfig, NodeConfigUpdate } from '../../types'
import { api } from '../../api/client'

interface Props {
  nodes: NodeInfo[]
  agents: Agent[]               // available agents defined on master
  onRefresh: () => void
}

interface ConfigModalState {
  nodeId: string
  agents: AgentConfig[]
  saving: boolean
  error: string
  success: boolean
}

const PROVIDER_TYPES = ['ollama', 'openai', 'anthropic', 'groq'] as const

function agentToConfig(a: Agent): AgentConfig {
  return {
    name: a.name,
    description: a.description,
    provider: a.provider,
    tools: a.tools,
    privilege_level: a.privilege_level,
    tags: a.tags,
  }
}

const BLANK_AGENT: AgentConfig = {
  name: '',
  description: '',
  provider: { type: 'ollama', model: 'llama3.2' },
  tools: ['read_file', 'fetch_webpage'],
  privilege_level: 1,
}

export function NodeMap({ nodes, agents, onRefresh }: Props) {
  const [modal, setModal] = useState<ConfigModalState | null>(null)
  const [expandedNode, setExpandedNode] = useState<string | null>(null)
  const [addingAgent, setAddingAgent] = useState(false)
  const [newAgent, setNewAgent] = useState<AgentConfig>({ ...BLANK_AGENT })

  function openConfig(node: NodeInfo) {
    const existing: AgentConfig[] = node.agent_configs.length > 0
      ? node.agent_configs
      : node.agent_ids.map(id => {
          const master = agents.find(a => a.id === id || a.name === id)
          return master ? agentToConfig(master) : { ...BLANK_AGENT, name: id }
        })

    setModal({
      nodeId: node.node_id,
      agents: existing,
      saving: false,
      error: '',
      success: false,
    })
    setAddingAgent(false)
    setNewAgent({ ...BLANK_AGENT })
  }

  function closeModal() {
    setModal(null)
    setAddingAgent(false)
  }

  function addFromMaster(agent: Agent) {
    if (!modal) return
    const cfg = agentToConfig(agent)
    if (modal.agents.find(a => a.name === cfg.name)) return
    setModal(m => m ? { ...m, agents: [...m.agents, cfg] } : m)
  }

  function removeAgent(idx: number) {
    setModal(m => m ? { ...m, agents: m.agents.filter((_, i) => i !== idx) } : m)
  }

  function addCustomAgent() {
    if (!newAgent.name.trim() || !modal) return
    setModal(m => m ? { ...m, agents: [...m.agents, { ...newAgent }] } : m)
    setNewAgent({ ...BLANK_AGENT })
    setAddingAgent(false)
  }

  async function saveConfig() {
    if (!modal) return
    setModal(m => m ? { ...m, saving: true, error: '', success: false } : m)
    try {
      const body: NodeConfigUpdate = { agents: modal.agents }
      await api.configureNode(modal.nodeId, body)
      setModal(m => m ? { ...m, saving: false, success: true } : m)
      setTimeout(() => { closeModal(); onRefresh() }, 1200)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      setModal(m => m ? { ...m, saving: false, error: msg } : m)
    }
  }

  return (
    <div className="p-4 space-y-4 overflow-y-auto h-full">
      <div className="flex justify-between items-center">
        <h2 className="text-lg font-semibold text-white">Connected Nodes ({nodes.length})</h2>
        <button onClick={onRefresh} className="text-xs text-gray-500 hover:text-white px-2 py-1 rounded hover:bg-gray-800">
          Refresh
        </button>
      </div>

      {nodes.length === 0 && (
        <div className="text-center py-12 text-gray-500">
          <Network size={40} className="mx-auto mb-3 opacity-30" />
          <p>No nodes connected.</p>
          <p className="text-xs mt-2">
            Start a node with: <code className="bg-gray-800 px-1 rounded">python -m node.worker</code>
          </p>
        </div>
      )}

      {/* Network topology */}
      {nodes.length > 0 && (
        <div className="relative bg-gray-900 rounded-xl border border-gray-800 p-6 flex flex-wrap gap-8 items-center justify-center">
          {/* Master node */}
          <div className="flex flex-col items-center gap-1">
            <div className="w-14 h-14 rounded-full bg-brand-600/30 border-2 border-brand-600 flex items-center justify-center">
              <Cpu size={24} className="text-brand-400" />
            </div>
            <span className="text-xs text-brand-400 font-medium">MASTER</span>
          </div>

          {nodes.map(node => (
            <div key={node.node_id} className="flex flex-col items-center gap-1">
              <div className={`w-12 h-12 rounded-full border-2 flex items-center justify-center ${
                node.status === 'active'
                  ? 'border-green-500 bg-green-900/20'
                  : 'border-gray-600 bg-gray-900/20'
              }`}>
                <Network size={20} className={node.status === 'active' ? 'text-green-400' : 'text-gray-600'} />
              </div>
              <div className="text-center">
                <div className="flex items-center gap-1 justify-center">
                  {node.status === 'active'
                    ? <Wifi size={10} className="text-green-400" />
                    : <WifiOff size={10} className="text-gray-500" />}
                  <span className="text-[11px] font-medium text-white">{node.node_id}</span>
                </div>
                <span className="text-[10px] text-gray-500 block">{node.host}:{node.port}</span>
                <div className="flex gap-2 text-[9px] justify-center mt-0.5">
                  <span className="text-blue-400">{node.tasks_running} running</span>
                  <span className="text-green-400">{node.tasks_completed} done</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Node detail cards */}
      <div className="space-y-2">
        {nodes.map(node => (
          <div key={node.node_id} className="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
            <div className="flex justify-between items-start p-3">
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className={`w-2 h-2 rounded-full ${node.status === 'active' ? 'bg-green-400' : 'bg-gray-500'}`} />
                  <span className="font-medium text-white text-sm">{node.node_id}</span>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${
                    node.status === 'active' ? 'bg-green-900 text-green-300' : 'bg-gray-700 text-gray-400'
                  }`}>
                    {node.status}
                  </span>
                </div>
                <p className="text-xs text-gray-400 mt-0.5">{node.host}:{node.port}</p>
                <div className="flex gap-3 mt-1 text-[10px]">
                  <span className="text-blue-400">{node.tasks_running} running</span>
                  <span className="text-green-400">{node.tasks_completed} completed</span>
                  <span className="text-gray-500">{node.agent_ids.length} agents</span>
                </div>
              </div>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => openConfig(node)}
                  className="flex items-center gap-1 text-xs text-gray-400 hover:text-white bg-gray-700 hover:bg-gray-600 px-2 py-1 rounded-lg transition-colors"
                  title="Configure agents on this node"
                >
                  <Settings size={12} />
                  Configure
                </button>
                <button
                  onClick={() => setExpandedNode(e => e === node.node_id ? null : node.node_id)}
                  className="text-gray-500 hover:text-white ml-1"
                >
                  {expandedNode === node.node_id ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                </button>
              </div>
            </div>

            {expandedNode === node.node_id && (
              <div className="px-3 pb-3 border-t border-gray-700 pt-2 space-y-2">
                <p className="text-[10px] text-gray-500">
                  Last seen: {new Date(node.last_seen).toLocaleTimeString()}
                  {Object.entries(node.capabilities).map(([k, v]) => ` · ${k}: ${v}`)}
                </p>
                {node.agent_ids.length > 0 && (
                  <div>
                    <p className="text-[10px] text-gray-500 mb-1">Active Agents:</p>
                    <div className="flex flex-wrap gap-1">
                      {node.agent_ids.map(id => (
                        <span key={id} className="text-[10px] bg-gray-700 text-gray-300 px-1.5 py-0.5 rounded">{id}</span>
                      ))}
                    </div>
                  </div>
                )}
                {node.agent_configs.length > 0 && (
                  <div>
                    <p className="text-[10px] text-gray-500 mb-1">Configured Agents:</p>
                    <div className="space-y-1">
                      {node.agent_configs.map((cfg, i) => (
                        <div key={i} className="text-[10px] bg-gray-900 rounded p-1.5 flex justify-between">
                          <span className="text-white font-medium">{cfg.name}</span>
                          <span className="text-gray-500">{cfg.provider?.type} · {cfg.provider?.model}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* ---- Config Modal ---- */}
      {modal && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
          <div className="bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-lg max-h-[85vh] flex flex-col shadow-2xl">
            {/* Header */}
            <div className="flex justify-between items-center p-4 border-b border-gray-700">
              <div>
                <h3 className="font-semibold text-white">Configure Node: {modal.nodeId}</h3>
                <p className="text-xs text-gray-400 mt-0.5">
                  Select which agents run on this node. Changes are pushed live via Redis.
                </p>
              </div>
              <button onClick={closeModal} className="text-gray-500 hover:text-white">
                <X size={18} />
              </button>
            </div>

            {/* Body */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">

              {/* Add from master agents */}
              {agents.length > 0 && (
                <div>
                  <p className="text-xs text-gray-400 mb-2 font-medium">Add from Master Agents</p>
                  <div className="flex flex-wrap gap-1.5">
                    {agents.map(a => {
                      const already = modal.agents.some(m => m.name === a.name)
                      return (
                        <button
                          key={a.id}
                          onClick={() => addFromMaster(a)}
                          disabled={already}
                          className={`text-xs px-2 py-1 rounded-lg border transition-colors flex items-center gap-1 ${
                            already
                              ? 'border-green-700 bg-green-900/20 text-green-400 cursor-default'
                              : 'border-gray-600 bg-gray-800 text-gray-300 hover:border-brand-500 hover:text-white'
                          }`}
                        >
                          {already && <Check size={10} />}
                          {a.name}
                          <span className="text-[9px] text-gray-500">{a.provider.type}</span>
                        </button>
                      )
                    })}
                  </div>
                </div>
              )}

              {/* Current agents list */}
              <div>
                <p className="text-xs text-gray-400 mb-2 font-medium">
                  Agents on this Node ({modal.agents.length})
                </p>
                {modal.agents.length === 0 && (
                  <p className="text-xs text-gray-600 italic">No agents assigned yet.</p>
                )}
                <div className="space-y-1.5">
                  {modal.agents.map((agent, idx) => (
                    <div key={idx} className="flex items-center justify-between bg-gray-800 rounded-lg px-3 py-2">
                      <div>
                        <span className="text-sm text-white font-medium">{agent.name || '(unnamed)'}</span>
                        <span className="text-[10px] text-gray-500 ml-2">
                          {agent.provider?.type} · {agent.provider?.model}
                        </span>
                        {agent.tools && agent.tools.length > 0 && (
                          <p className="text-[9px] text-gray-600 mt-0.5">
                            Tools: {agent.tools.slice(0, 4).join(', ')}{agent.tools.length > 4 ? ` +${agent.tools.length - 4}` : ''}
                          </p>
                        )}
                      </div>
                      <button
                        onClick={() => removeAgent(idx)}
                        className="text-gray-600 hover:text-red-400 transition-colors"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  ))}
                </div>
              </div>

              {/* Add custom agent */}
              {addingAgent ? (
                <div className="bg-gray-800 rounded-xl border border-gray-700 p-3 space-y-2">
                  <p className="text-xs text-gray-400 font-medium">Custom Agent</p>
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="text-[10px] text-gray-500">Name *</label>
                      <input
                        value={newAgent.name}
                        onChange={e => setNewAgent(a => ({ ...a, name: e.target.value }))}
                        placeholder="my-agent"
                        className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1 text-sm text-white"
                      />
                    </div>
                    <div>
                      <label className="text-[10px] text-gray-500">Provider</label>
                      <select
                        value={newAgent.provider.type}
                        onChange={e => setNewAgent(a => ({ ...a, provider: { ...a.provider, type: e.target.value as typeof PROVIDER_TYPES[number] } }))}
                        className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1 text-sm text-white"
                      >
                        {PROVIDER_TYPES.map(p => <option key={p} value={p}>{p}</option>)}
                      </select>
                    </div>
                    <div className="col-span-2">
                      <label className="text-[10px] text-gray-500">Model</label>
                      <input
                        value={newAgent.provider.model}
                        onChange={e => setNewAgent(a => ({ ...a, provider: { ...a.provider, model: e.target.value } }))}
                        placeholder="llama3.2"
                        className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1 text-sm text-white"
                      />
                    </div>
                    {(newAgent.provider.type !== 'ollama') && (
                      <div className="col-span-2">
                        <label className="text-[10px] text-gray-500">API Key</label>
                        <input
                          type="password"
                          value={newAgent.provider.api_key ?? ''}
                          onChange={e => setNewAgent(a => ({ ...a, provider: { ...a.provider, api_key: e.target.value } }))}
                          placeholder="sk-…"
                          className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1 text-sm text-white"
                        />
                      </div>
                    )}
                  </div>
                  <div className="flex gap-2 pt-1">
                    <button
                      onClick={addCustomAgent}
                      disabled={!newAgent.name.trim()}
                      className="flex-1 py-1.5 bg-brand-600 hover:bg-brand-700 text-white text-xs rounded-lg disabled:opacity-50"
                    >
                      Add Agent
                    </button>
                    <button
                      onClick={() => setAddingAgent(false)}
                      className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-xs text-white rounded-lg"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  onClick={() => setAddingAgent(true)}
                  className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-white border border-dashed border-gray-600 hover:border-gray-400 rounded-lg px-3 py-2 w-full justify-center transition-colors"
                >
                  <Plus size={12} />
                  Add Custom Agent
                </button>
              )}
            </div>

            {/* Footer */}
            <div className="p-4 border-t border-gray-700 space-y-2">
              {modal.error && (
                <div className="flex items-center gap-2 text-xs text-red-400 bg-red-900/20 rounded-lg p-2">
                  <AlertCircle size={12} />
                  {modal.error}
                </div>
              )}
              {modal.success && (
                <div className="flex items-center gap-2 text-xs text-green-400 bg-green-900/20 rounded-lg p-2">
                  <Check size={12} />
                  Configuration pushed to node successfully!
                </div>
              )}
              <div className="flex gap-2">
                <button onClick={closeModal} className="flex-1 py-2 bg-gray-700 hover:bg-gray-600 text-white text-sm rounded-lg">
                  Cancel
                </button>
                <button
                  onClick={saveConfig}
                  disabled={modal.saving || modal.agents.length === 0}
                  className="flex-1 py-2 bg-brand-600 hover:bg-brand-700 text-white text-sm rounded-lg disabled:opacity-50 font-medium"
                >
                  {modal.saving ? 'Pushing…' : `Push Config (${modal.agents.length} agents)`}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
