import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { ChatMessage } from '../../types'
import clsx from 'clsx'

interface Props { message: ChatMessage }

export function MessageBubble({ message }: Props) {
  const isUser = message.role === 'user'
  const isSystem = message.role === 'system'

  if (isSystem) {
    return (
      <div className="flex justify-center">
        <span className="text-xs text-gray-500 bg-gray-800 px-3 py-1 rounded-full">
          {message.content}
        </span>
      </div>
    )
  }

  return (
    <div className={clsx('flex', isUser ? 'justify-end' : 'justify-start')}>
      {!isUser && (
        <div className="w-7 h-7 rounded-full bg-brand-600 flex items-center justify-center text-sm mr-2 mt-1 shrink-0">
          🤖
        </div>
      )}
      <div
        className={clsx(
          'max-w-[80%] rounded-2xl px-4 py-3 text-sm',
          isUser
            ? 'bg-brand-600 text-white rounded-br-sm'
            : 'bg-gray-800 text-gray-100 rounded-bl-sm'
        )}
      >
        {message.streaming && !message.content ? (
          <span className="inline-flex gap-1">
            <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce [animation-delay:0ms]" />
            <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce [animation-delay:150ms]" />
            <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce [animation-delay:300ms]" />
          </span>
        ) : (
          <ReactMarkdown remarkPlugins={[remarkGfm]} className="prose prose-invert prose-sm max-w-none">
            {message.content}
          </ReactMarkdown>
        )}
        {message.streaming && message.content && (
          <span className="inline-block w-0.5 h-4 bg-gray-400 ml-0.5 animate-pulse" />
        )}
        <div className="text-[10px] text-gray-500 mt-1 text-right">
          {new Date(message.timestamp).toLocaleTimeString()}
        </div>
      </div>
      {isUser && (
        <div className="w-7 h-7 rounded-full bg-gray-700 flex items-center justify-center text-sm ml-2 mt-1 shrink-0">
          👤
        </div>
      )}
    </div>
  )
}
