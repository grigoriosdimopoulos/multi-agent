import { useState } from 'react'
import { ListTodo, RefreshCw, ChevronDown, ChevronUp, X, Zap, Shield, Wrench } from 'lucide-react'
import type { Task, NodeInfo, Agent } from '../../types'
import { api } from '../../api/client'

const STATUS_STYLE: Record<string, string> = {
  pending:   'bg-yellow-900 text-yellow-300',
  running:   'bg-blue-900 text-blue-300 animate-pulse',
  completed: 'bg-green-900 text-green-300',
  failed:    'bg-red-900 text-red-300',
  cancelled: 'bg-gray-700 text-gray-400',
}

const PRIVILEGE_LABELS: Record<number, { label: string; color: string }> = {
  0: { label: 'Read-Only',  color: 'text-gray-400' },
  1: { label: 'Standard',   color: 'text-blue-400' },
  2: { label: 'Elevated',   color: 'text-orange-400' },
  3: { label: 'Admin',      color: 'text-red-400' },
}

const ALL_TOOLS = [
  'read_file', 'write_file', 'list_directory', 'search_in_files',
  'fetch_webpage', 'http_request',
  'execute_python', 'execute_shell',
  'read_excel', 'write_excel', 'read_word', 'write_word', 'read_pdf', 'read_csv', 'write_csv',
  'query_knowledge_base',
]

interface Props {
  tasks: Task[]
  nodes: NodeInfo[]
  agents: Agent[]
  onRefresh: () => void
}

interface NewTask {
  input: string
  agent_id: string
  chain_id: string
  node_id: string
  recursive: boolean
  privilege_level: number
  required_tools: string[]
  prerequisites: string[]
}

const DEFAULT_TASK: NewTask = {
  input: '',
  agent_id: '',
  chain_id: '',
  node_id: '',
  recursive: false,
  privilege_level: 1,
  required_tools: [],
  prerequisites: [],
}

export function TaskQueue({ tasks, nodes, agents, onRefresh }: Props) {
  const [expanded, setExpanded] = useState<string | null>(null)
  const [newTask, setNewTask] = useState<NewTask>(DEFAULT_TASK)
  const [submitting, setSubmitting] = useState(false)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [toolFilter, setToolFilter] = useState('')

  function toggleTool(tool: string) {
    setNewTask(t => ({
      ...t,
      required_tools: t.required_tools.includes(tool)
        ? t.required_tools.filter(x => x !== tool)
        : [...t.required_tools, tool],
    }))
  }

  async function submit() {
    if (!newTask.input.trim()) return
    setSubmitting(true)
    try {
      await api.submitTask({
        input: newTask.input,
        agent_id: newTask.agent_id || undefined,
        chain_id: newTask.chain_id || undefined,
        node_id: newTask.node_id || undefined,
        recursive: newTask.recursive,
        privilege_level: newTask.privilege_level,
        required_tools: newTask.required_tools,
        prerequisites: newTask.prerequisites.filter(Boolean),
      })
      setNewTask(DEFAULT_TASK)
      setShowAdvanced(false)
      setTimeout(onRefresh, 800)
    } finally {
      setSubmitting(false)
    }
  }

  async function cancel(taskId: string) {
    try {
      await api.cancelTask(taskId)
      setTimeout(onRefresh, 400)
    } catch { /* ignore */ }
  }

  const running   = tasks.filter(t => t.status === 'running').length
  const completed = tasks.filter(t => t.status === 'completed').length
  const failed    = tasks.filter(t => t.status === 'failed').length
  const pending   = tasks.filter(t => t.status === 'pending').length

  const filteredTools = ALL_TOOLS.filter(t => t.includes(toolFilter.toLowerCase()))
  const activeNodes = nodes.filter(n => n.status === 'active')

  return (
    <div className="p-4 space-y-4 overflow-y-auto h-full">
      <div className="flex justify-between items-center">
        <h2 className="text-lg font-semibold text-white">Task Queue ({tasks.length})</h2>
        <button onClick={onRefresh} className="p-1.5 rounded-lg hover:bg-gray-800 text-gray-400 hover:text-white">
          <RefreshCw size={15} />
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-2">
        {[
          { label: 'Pending',  count: pending,   color: 'text-yellow-400' },
          { label: 'Running',  count: running,   color: 'text-blue-400' },
          { label: 'Done',     count: completed, color: 'text-green-400' },
          { label: 'Failed',   count: failed,    color: 'text-red-400' },
        ].map(s => (
          <div key={s.label} className="bg-gray-800 rounded-lg p-2 text-center">
            <div className={`text-xl font-bold ${s.color}`}>{s.count}</div>
            <div className="text-[10px] text-gray-500">{s.label}</div>
          </div>
        ))}
      </div>

      {/* Submit form */}
      <div className="bg-gray-800 rounded-xl border border-gray-700 p-3 space-y-3">
        <p className="text-xs font-medium text-gray-400 uppercase tracking-wide">Submit Task</p>

        <textarea
          value={newTask.input}
          onChange={e => setNewTask(t => ({ ...t, input: e.target.value }))}
          placeholder="Describe what you want the agent to do…"
          rows={3}
          className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white resize-none focus:outline-none focus:border-brand-500"
        />

        {/* Basic options row */}
        <div className="grid grid-cols-2 gap-2">
          {/* Target node */}
          <div>
            <label className="text-[10px] text-gray-500 mb-1 block">Target Node</label>
            <select
              value={newTask.node_id}
              onChange={e => setNewTask(t => ({ ...t, node_id: e.target.value }))}
              className="w-full bg-gray-900 border border-gray-700 rounded-lg px-2 py-1.5 text-sm text-white"
            >
              <option value="">Broadcast (any node)</option>
              {activeNodes.map(n => (
                <option key={n.node_id} value={n.node_id}>
                  {n.node_id} ({n.agent_ids.length} agents)
                </option>
              ))}
            </select>
          </div>

          {/* Agent */}
          <div>
            <label className="text-[10px] text-gray-500 mb-1 block">Agent (optional)</label>
            <select
              value={newTask.agent_id}
              onChange={e => setNewTask(t => ({ ...t, agent_id: e.target.value }))}
              className="w-full bg-gray-900 border border-gray-700 rounded-lg px-2 py-1.5 text-sm text-white"
            >
              <option value="">Default agent</option>
              {agents.map(a => (
                <option key={a.id} value={a.id}>{a.name}</option>
              ))}
            </select>
          </div>
        </div>

        {/* Advanced toggle */}
        <button
          onClick={() => setShowAdvanced(x => !x)}
          className="text-xs text-gray-500 hover:text-gray-300 flex items-center gap-1"
        >
          {showAdvanced ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          Advanced options
        </button>

        {showAdvanced && (
          <div className="space-y-3 border-t border-gray-700 pt-3">

            {/* Privilege level */}
            <div>
              <label className="text-[10px] text-gray-500 mb-1 flex items-center gap-1">
                <Shield size={10} /> Privilege Level
              </label>
              <div className="flex gap-2">
                {[0, 1, 2, 3].map(lv => (
                  <button
                    key={lv}
                    onClick={() => setNewTask(t => ({ ...t, privilege_level: lv }))}
                    className={`flex-1 py-1 rounded text-[10px] font-medium border transition-colors ${
                      newTask.privilege_level === lv
                        ? 'border-brand-500 bg-brand-900/30 text-brand-300'
                        : 'border-gray-700 bg-gray-900 text-gray-500 hover:text-gray-300'
                    }`}
                  >
                    {PRIVILEGE_LABELS[lv].label}
                  </button>
                ))}
              </div>
            </div>

            {/* Required tools */}
            <div>
              <label className="text-[10px] text-gray-500 mb-1 flex items-center gap-1">
                <Wrench size={10} /> Required Tools
                {newTask.required_tools.length > 0 && (
                  <span className="text-brand-400 ml-1">({newTask.required_tools.length} selected)</span>
                )}
              </label>
              <input
                value={toolFilter}
                onChange={e => setToolFilter(e.target.value)}
                placeholder="Filter tools…"
                className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1 text-xs text-white mb-1.5"
              />
              <div className="grid grid-cols-2 gap-1 max-h-28 overflow-y-auto">
                {filteredTools.map(tool => (
                  <label key={tool} className="flex items-center gap-1.5 cursor-pointer group">
                    <input
                      type="checkbox"
                      checked={newTask.required_tools.includes(tool)}
                      onChange={() => toggleTool(tool)}
                      className="accent-brand-600"
                    />
                    <span className="text-[10px] text-gray-400 group-hover:text-gray-200 truncate">{tool}</span>
                  </label>
                ))}
              </div>
            </div>

            {/* Chain ID */}
            <div>
              <label className="text-[10px] text-gray-500 mb-1 flex items-center gap-1">
                <Zap size={10} /> Chain ID (optional)
              </label>
              <input
                value={newTask.chain_id}
                onChange={e => setNewTask(t => ({ ...t, chain_id: e.target.value }))}
                placeholder="e.g. research-chain"
                className="w-full bg-gray-900 border border-gray-700 rounded-lg px-2 py-1.5 text-sm text-white"
              />
            </div>

            {/* Recursive */}
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={newTask.recursive}
                onChange={e => setNewTask(t => ({ ...t, recursive: e.target.checked }))}
                className="accent-brand-600"
              />
              <span className="text-xs text-gray-400">Recursive (allow sub-tasks)</span>
            </label>
          </div>
        )}

        <button
          onClick={submit}
          disabled={submitting || !newTask.input.trim()}
          className="w-full py-2 bg-brand-600 hover:bg-brand-700 text-white text-sm rounded-lg disabled:opacity-50 font-medium transition-colors"
        >
          {submitting ? 'Dispatching…' : 'Dispatch to Node'}
        </button>
      </div>

      {/* Task list */}
      {tasks.length === 0 && (
        <div className="text-center py-12 text-gray-500">
          <ListTodo size={40} className="mx-auto mb-3 opacity-30" />
          <p>No tasks yet. Submit one above.</p>
        </div>
      )}

      <div className="space-y-2">
        {tasks.map(task => (
          <div key={task.task_id} className="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
            <div className="flex items-start gap-3 p-3">
              <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium mt-0.5 whitespace-nowrap ${STATUS_STYLE[task.status] ?? ''}`}>
                {task.status}
              </span>
              <div className="flex-1 min-w-0">
                <p className="text-sm text-white truncate">{task.input}</p>
                <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                  <span className="text-[10px] text-gray-500">{new Date(task.created_at).toLocaleString()}</span>
                  {task.node_id && (
                    <span className="text-[10px] text-brand-400">→ {task.node_id}</span>
                  )}
                  {task.agent_id && (
                    <span className="text-[10px] text-gray-500">{task.agent_id}</span>
                  )}
                  {task.privilege_level > 1 && (
                    <span className={`text-[10px] ${PRIVILEGE_LABELS[task.privilege_level]?.color}`}>
                      {PRIVILEGE_LABELS[task.privilege_level]?.label}
                    </span>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-1">
                {(task.status === 'pending' || task.status === 'running') && (
                  <button
                    onClick={() => cancel(task.task_id)}
                    className="text-gray-600 hover:text-red-400 transition-colors"
                    title="Cancel task"
                  >
                    <X size={13} />
                  </button>
                )}
                <button
                  onClick={() => setExpanded(e => e === task.task_id ? null : task.task_id)}
                  className="text-gray-500 hover:text-white"
                >
                  {expanded === task.task_id ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                </button>
              </div>
            </div>

            {expanded === task.task_id && (
              <div className="px-3 pb-3 border-t border-gray-700 pt-2 space-y-2">
                {/* Metadata */}
                <div className="grid grid-cols-2 gap-2 text-[10px]">
                  <div>
                    <span className="text-gray-600">Task ID:</span>
                    <span className="text-gray-400 ml-1 font-mono">{task.task_id.slice(0, 12)}…</span>
                  </div>
                  <div>
                    <span className="text-gray-600">Iterations:</span>
                    <span className="text-gray-400 ml-1">{task.iterations}</span>
                  </div>
                  {task.completed_at && (
                    <div>
                      <span className="text-gray-600">Completed:</span>
                      <span className="text-gray-400 ml-1">{new Date(task.completed_at).toLocaleTimeString()}</span>
                    </div>
                  )}
                  {task.required_tools.length > 0 && (
                    <div className="col-span-2">
                      <span className="text-gray-600">Tools:</span>
                      <span className="text-gray-400 ml-1">{task.required_tools.join(', ')}</span>
                    </div>
                  )}
                </div>

                {task.output && (
                  <div className="text-xs text-gray-300 bg-gray-900 rounded-lg p-2 max-h-48 overflow-y-auto whitespace-pre-wrap">
                    {task.output}
                  </div>
                )}
                {task.error && (
                  <p className="text-xs text-red-400 bg-red-900/20 rounded-lg p-2">{task.error}</p>
                )}
                {task.subtask_ids.length > 0 && (
                  <p className="text-[10px] text-gray-500">Subtasks: {task.subtask_ids.join(', ')}</p>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
