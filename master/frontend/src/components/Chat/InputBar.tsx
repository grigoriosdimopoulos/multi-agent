import { useState, useRef, KeyboardEvent } from 'react'
import { Send } from 'lucide-react'

interface Props {
  onSend: (text: string) => void
  loading: boolean
}

export function InputBar({ onSend, loading }: Props) {
  const [text, setText] = useState('')
  const ref = useRef<HTMLTextAreaElement>(null)

  function submit() {
    if (!text.trim() || loading) return
    onSend(text.trim())
    setText('')
    ref.current!.style.height = 'auto'
  }

  function onKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  return (
    <div className="p-3 border-t border-gray-800 bg-gray-900">
      <div className="flex items-end gap-2 bg-gray-800 rounded-xl border border-gray-700 px-3 py-2">
        <textarea
          ref={ref}
          value={text}
          onChange={e => {
            setText(e.target.value)
            e.target.style.height = 'auto'
            e.target.style.height = Math.min(e.target.scrollHeight, 160) + 'px'
          }}
          onKeyDown={onKey}
          placeholder="Message the agent… (Enter to send, Shift+Enter for newline)"
          rows={1}
          className="flex-1 bg-transparent text-white placeholder-gray-500 text-sm resize-none outline-none max-h-40"
          disabled={loading}
        />
        <button
          onClick={submit}
          disabled={!text.trim() || loading}
          className="p-2 rounded-lg bg-brand-600 hover:bg-brand-700 disabled:opacity-40 disabled:cursor-not-allowed text-white transition-colors shrink-0"
        >
          <Send size={16} />
        </button>
      </div>
      <p className="text-[10px] text-gray-600 mt-1 ml-1">Shift+Enter for newline • Enter to send</p>
    </div>
  )
}
