import { useState } from 'react'
import { ListTodo, RefreshCw, ChevronDown, ChevronUp } from 'lucide-react'
import type { Task } from '../../types'
import { api } from '../../api/client'

const STATUS_STYLE: Record<string, string> = {
  pending:   'bg-yellow-900 text-yellow-300',
  running:   'bg-blue-900 text-blue-300 animate-pulse',
  completed: 'bg-green-900 text-green-300',
  failed:    'bg-red-900 text-red-300',
}

interface Props { tasks: Task[]; onRefresh: () => void }

export function TaskQueue({ tasks, onRefresh }: Props) {
  const [expanded, setExpanded] = useState<string | null>(null)
  const [newTask, setNewTask] = useState({ input: '', agent_id: '', recursive: false })
  const [submitting, setSubmitting] = useState(false)

  async function submit() {
    if (!newTask.input.trim()) return
    setSubmitting(true)
    try {
      await api.submitTask({
        input: newTask.input,
        agent_id: newTask.agent_id || undefined,
        recursive: newTask.recursive,
      })
      setNewTask({ input: '', agent_id: '', recursive: false })
      setTimeout(onRefresh, 1000)
    } finally {
      setSubmitting(false)
    }
  }

  const running = tasks.filter(t => t.status === 'running').length
  const completed = tasks.filter(t => t.status === 'completed').length
  const failed = tasks.filter(t => t.status === 'failed').length

  return (
    <div className="p-4 space-y-4 overflow-y-auto h-full">
      <div className="flex justify-between items-center">
        <h2 className="text-lg font-semibold text-white">Task Queue ({tasks.length})</h2>
        <button onClick={onRefresh} className="p-1.5 rounded-lg hover:bg-gray-800 text-gray-400 hover:text-white">
          <RefreshCw size={15} />
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-2">
        {[
          { label: 'Running', count: running, color: 'text-blue-400' },
          { label: 'Done',    count: completed, color: 'text-green-400' },
          { label: 'Failed',  count: failed, color: 'text-red-400' },
        ].map(s => (
          <div key={s.label} className="bg-gray-800 rounded-lg p-3 text-center">
            <div className={`text-2xl font-bold ${s.color}`}>{s.count}</div>
            <div className="text-xs text-gray-500">{s.label}</div>
          </div>
        ))}
      </div>

      {/* Submit form */}
      <div className="bg-gray-800 rounded-xl border border-gray-700 p-3 space-y-2">
        <p className="text-xs font-medium text-gray-400">Submit Task</p>
        <textarea
          value={newTask.input}
          onChange={e => setNewTask(t => ({...t, input: e.target.value}))}
          placeholder="Describe the task…"
          rows={2}
          className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white resize-none"
        />
        <div className="flex gap-2 items-center">
          <input
            value={newTask.agent_id}
            onChange={e => setNewTask(t => ({...t, agent_id: e.target.value}))}
            placeholder="Agent ID (optional)"
            className="flex-1 bg-gray-900 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-white"
          />
          <label className="flex items-center gap-1 text-xs text-gray-400 whitespace-nowrap">
            <input type="checkbox" checked={newTask.recursive} onChange={e => setNewTask(t => ({...t, recursive: e.target.checked}))} className="accent-brand-600" />
            Recursive
          </label>
          <button onClick={submit} disabled={submitting || !newTask.input.trim()}
            className="px-4 py-1.5 bg-brand-600 hover:bg-brand-700 text-white text-sm rounded-lg disabled:opacity-50">
            Submit
          </button>
        </div>
      </div>

      {/* Task list */}
      {tasks.length === 0 && (
        <div className="text-center py-12 text-gray-500">
          <ListTodo size={40} className="mx-auto mb-3 opacity-30" />
          <p>No tasks yet.</p>
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
                <p className="text-[10px] text-gray-500 mt-0.5">
                  {new Date(task.created_at).toLocaleString()}
                  {task.agent_id && ` · ${task.agent_id}`}
                </p>
              </div>
              <button onClick={() => setExpanded(e => e === task.task_id ? null : task.task_id)} className="text-gray-500 hover:text-white">
                {expanded === task.task_id ? <ChevronUp size={14}/> : <ChevronDown size={14}/>}
              </button>
            </div>
            {expanded === task.task_id && (
              <div className="px-3 pb-3 border-t border-gray-700 pt-2 space-y-2">
                {task.output && (
                  <div className="text-xs text-gray-300 bg-gray-900 rounded-lg p-2 max-h-40 overflow-y-auto whitespace-pre-wrap">
                    {task.output}
                  </div>
                )}
                {task.error && (
                  <p className="text-xs text-red-400 bg-red-900/20 rounded-lg p-2">{task.error}</p>
                )}
                {task.subtask_ids.length > 0 && (
                  <p className="text-xs text-gray-500">Subtasks: {task.subtask_ids.join(', ')}</p>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
