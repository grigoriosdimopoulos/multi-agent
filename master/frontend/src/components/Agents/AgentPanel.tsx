import { useState } from 'react'
import { Plus, Trash2, Bot, ChevronDown, ChevronUp } from 'lucide-react'
import type { Agent } from '../../types'
import { api } from '../../api/client'

const PROVIDER_COLORS: Record<string, string> = {
  ollama:    'bg-green-900 text-green-300',
  openai:    'bg-blue-900 text-blue-300',
  anthropic: 'bg-purple-900 text-purple-300',
  groq:      'bg-orange-900 text-orange-300',
}

const ALL_TOOLS = [
  'read_file','write_file','list_directory','search_in_files',
  'fetch_webpage','http_request',
  'execute_python','execute_shell',
  'read_excel','write_excel','read_word','write_word','read_pdf','read_csv','write_csv',
  'query_knowledge_base',
]

interface Props {
  agents: Agent[]
  onRefresh: () => void
}

export function AgentPanel({ agents, onRefresh }: Props) {
  const [showForm, setShowForm] = useState(false)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [form, setForm] = useState({
    name: '', description: '', provider_type: 'ollama', model: 'llama3.2',
    api_key: '', base_url: '', system_prompt: 'You are a helpful AI assistant.',
    temperature: 0.7, privilege_level: 1, tools: [] as string[],
  })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  async function save() {
    if (!form.name.trim()) { setError('Name is required'); return }
    setSaving(true); setError('')
    try {
      await api.createAgent({
        name: form.name,
        description: form.description,
        provider: {
          type: form.provider_type,
          model: form.model,
          api_key: form.api_key || undefined,
          base_url: form.base_url || undefined,
        },
        tools: form.tools,
        system_prompt: form.system_prompt,
        temperature: form.temperature,
        privilege_level: form.privilege_level,
      })
      setShowForm(false)
      onRefresh()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to create agent')
    } finally { setSaving(false) }
  }

  async function remove(id: string) {
    await api.deleteAgent(id)
    onRefresh()
  }

  function toggleTool(t: string) {
    setForm(f => ({
      ...f,
      tools: f.tools.includes(t) ? f.tools.filter(x => x !== t) : [...f.tools, t],
    }))
  }

  return (
    <div className="p-4 space-y-4 overflow-y-auto h-full">
      <div className="flex justify-between items-center">
        <h2 className="text-lg font-semibold text-white">Agents ({agents.length})</h2>
        <button
          onClick={() => setShowForm(!showForm)}
          className="flex items-center gap-2 px-3 py-1.5 bg-brand-600 hover:bg-brand-700 text-white rounded-lg text-sm transition-colors"
        >
          <Plus size={14} /> New Agent
        </button>
      </div>

      {/* Create form */}
      {showForm && (
        <div className="bg-gray-800 rounded-xl border border-gray-700 p-4 space-y-3">
          <h3 className="font-medium text-white text-sm">Create Agent</h3>
          {error && <p className="text-red-400 text-xs">{error}</p>}
          <div className="grid grid-cols-2 gap-3">
            <input placeholder="Name *" value={form.name} onChange={e => setForm(f => ({...f, name: e.target.value}))}
              className="col-span-2 bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white" />
            <input placeholder="Description" value={form.description} onChange={e => setForm(f => ({...f, description: e.target.value}))}
              className="col-span-2 bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white" />
            <select value={form.provider_type} onChange={e => setForm(f => ({...f, provider_type: e.target.value}))}
              className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white">
              <option value="ollama">Ollama (free/local)</option>
              <option value="openai">OpenAI</option>
              <option value="anthropic">Anthropic</option>
              <option value="groq">Groq (fast/free tier)</option>
            </select>
            <input placeholder="Model (e.g. llama3.2)" value={form.model} onChange={e => setForm(f => ({...f, model: e.target.value}))}
              className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white" />
            <input placeholder="API Key (leave blank for Ollama)" value={form.api_key} onChange={e => setForm(f => ({...f, api_key: e.target.value}))}
              type="password" className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white" />
            <input placeholder="Base URL (optional override)" value={form.base_url} onChange={e => setForm(f => ({...f, base_url: e.target.value}))}
              className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white" />
          </div>
          <textarea placeholder="System prompt" value={form.system_prompt}
            onChange={e => setForm(f => ({...f, system_prompt: e.target.value}))} rows={3}
            className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white resize-none" />
          <div>
            <p className="text-xs text-gray-400 mb-2">Tools (grant capabilities)</p>
            <div className="flex flex-wrap gap-2">
              {ALL_TOOLS.map(t => (
                <label key={t} className="flex items-center gap-1 cursor-pointer">
                  <input type="checkbox" checked={form.tools.includes(t)} onChange={() => toggleTool(t)} className="accent-brand-600" />
                  <span className="text-xs text-gray-300">{t}</span>
                </label>
              ))}
            </div>
          </div>
          <div className="flex gap-2">
            <button onClick={save} disabled={saving}
              className="px-4 py-2 bg-brand-600 hover:bg-brand-700 text-white rounded-lg text-sm disabled:opacity-50">
              {saving ? 'Creating…' : 'Create'}
            </button>
            <button onClick={() => setShowForm(false)} className="px-4 py-2 bg-gray-700 text-white rounded-lg text-sm">Cancel</button>
          </div>
        </div>
      )}

      {/* Agent cards */}
      {agents.length === 0 && (
        <div className="text-center py-12 text-gray-500">
          <Bot size={40} className="mx-auto mb-3 opacity-30" />
          <p>No agents yet. Create one to get started.</p>
        </div>
      )}
      <div className="space-y-2">
        {agents.map(a => (
          <div key={a.id} className="bg-gray-800 border border-gray-700 rounded-xl overflow-hidden">
            <div className="flex items-center gap-3 p-3">
              <div className="w-8 h-8 rounded-lg bg-brand-600/20 flex items-center justify-center">
                <Bot size={16} className="text-brand-500" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-white text-sm truncate">{a.name}</span>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${PROVIDER_COLORS[a.provider.type] ?? 'bg-gray-700 text-gray-300'}`}>
                    {a.provider.type}
                  </span>
                </div>
                <p className="text-xs text-gray-400 truncate">{a.provider.model} · {a.tools.length} tools</p>
              </div>
              <button onClick={() => setExpanded(e => e === a.id ? null : a.id)} className="text-gray-500 hover:text-white">
                {expanded === a.id ? <ChevronUp size={16}/> : <ChevronDown size={16}/>}
              </button>
              <button onClick={() => remove(a.id)} className="text-gray-600 hover:text-red-400 transition-colors">
                <Trash2 size={14} />
              </button>
            </div>
            {expanded === a.id && (
              <div className="px-3 pb-3 text-xs text-gray-400 border-t border-gray-700 pt-2 space-y-1">
                <p><span className="text-gray-500">ID:</span> {a.id}</p>
                {a.description && <p><span className="text-gray-500">Desc:</span> {a.description}</p>}
                <p><span className="text-gray-500">Tools:</span> {a.tools.join(', ') || 'none'}</p>
                <p><span className="text-gray-500">Privilege:</span> {['Read-only','Standard','Elevated','Admin'][a.privilege_level]}</p>
                {a.tags.length > 0 && <p><span className="text-gray-500">Tags:</span> {a.tags.join(', ')}</p>}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
