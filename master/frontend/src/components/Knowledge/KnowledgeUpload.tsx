import { useState, useCallback, useRef } from 'react'
import { Upload, BookOpen, Trash2, Search, FileText } from 'lucide-react'
import type { KnowledgeCollection } from '../../types'
import { api } from '../../api/client'

interface Props {
  collections: KnowledgeCollection[]
  onRefresh: () => void
}

export function KnowledgeUpload({ collections, onRefresh }: Props) {
  const [dragOver, setDragOver] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [collection, setCollection] = useState('default')
  const [queryText, setQueryText] = useState('')
  const [queryResults, setQueryResults] = useState<unknown[]>([])
  const [querying, setQuerying] = useState(false)
  const [status, setStatus] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)

  const upload = useCallback(async (files: FileList | null) => {
    if (!files?.length) return
    setUploading(true)
    setStatus('')
    let ok = 0; let fail = 0
    for (const file of Array.from(files)) {
      try {
        const result = await api.ingestFile(file, collection)
        if (result.success) { ok++; setStatus(`✓ ${file.name} → ${result.chunks} chunks`) }
        else { fail++; setStatus(`✗ ${file.name}: ${result.error}`) }
      } catch (e: unknown) {
        fail++; setStatus(`✗ ${file.name}: ${e instanceof Error ? e.message : 'Error'}`)
      }
    }
    setStatus(`Done: ${ok} ok, ${fail} failed`)
    setUploading(false)
    onRefresh()
  }, [collection, onRefresh])

  async function query() {
    if (!queryText.trim()) return
    setQuerying(true)
    const r = await api.queryKnowledge(queryText, collection)
    setQueryResults(r.results)
    setQuerying(false)
  }

  async function deleteCol(name: string) {
    await api.deleteCollection(name)
    onRefresh()
  }

  return (
    <div className="p-4 space-y-4 overflow-y-auto h-full">
      <h2 className="text-lg font-semibold text-white">Knowledge Base</h2>

      {/* Collection selector */}
      <div className="flex gap-2">
        <input
          value={collection}
          onChange={e => setCollection(e.target.value)}
          placeholder="Collection name"
          className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white"
        />
      </div>

      {/* Drop zone */}
      <div
        onDragOver={e => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={e => { e.preventDefault(); setDragOver(false); upload(e.dataTransfer.files) }}
        onClick={() => fileRef.current?.click()}
        className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors ${
          dragOver ? 'border-brand-500 bg-brand-600/10' : 'border-gray-700 hover:border-gray-600'
        }`}
      >
        <Upload size={32} className="mx-auto mb-3 text-gray-500" />
        <p className="text-sm text-gray-400">
          {uploading ? 'Uploading…' : 'Drop files here or click to browse'}
        </p>
        <p className="text-xs text-gray-600 mt-1">PDF, DOCX, XLSX, TXT, MD, CSV, JSON, YAML…</p>
        <input ref={fileRef} type="file" multiple className="hidden" onChange={e => upload(e.target.files)} />
      </div>

      {status && (
        <p className={`text-sm rounded-lg px-3 py-2 ${status.startsWith('✓') || status.startsWith('Done') ? 'bg-green-900/30 text-green-300' : 'bg-red-900/30 text-red-300'}`}>
          {status}
        </p>
      )}

      {/* Collections */}
      <div>
        <h3 className="text-sm font-medium text-gray-400 mb-2 flex items-center gap-2">
          <BookOpen size={14} /> Collections
        </h3>
        {collections.length === 0
          ? <p className="text-xs text-gray-600">No collections yet.</p>
          : (
            <div className="space-y-1">
              {collections.map(c => (
                <div key={c.name} className="flex items-center justify-between bg-gray-800 rounded-lg px-3 py-2">
                  <div className="flex items-center gap-2">
                    <FileText size={14} className="text-gray-500" />
                    <span className="text-sm text-white">{c.name}</span>
                    <span className="text-xs text-gray-500">{c.count} chunks</span>
                  </div>
                  <button onClick={() => deleteCol(c.name)} className="text-gray-600 hover:text-red-400 transition-colors">
                    <Trash2 size={13} />
                  </button>
                </div>
              ))}
            </div>
          )
        }
      </div>

      {/* Query */}
      <div className="space-y-2">
        <h3 className="text-sm font-medium text-gray-400 flex items-center gap-2">
          <Search size={14} /> Test Query
        </h3>
        <div className="flex gap-2">
          <input
            value={queryText}
            onChange={e => setQueryText(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && query()}
            placeholder="Search knowledge base…"
            className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white"
          />
          <button onClick={query} disabled={querying}
            className="px-4 py-2 bg-brand-600 hover:bg-brand-700 text-white text-sm rounded-lg disabled:opacity-50">
            Search
          </button>
        </div>
        {queryResults.length > 0 && (
          <div className="space-y-2">
            {(queryResults as Array<{content: string; score: number; metadata: {filename: string}}>).map((r, i) => (
              <div key={i} className="bg-gray-800 rounded-lg p-3 text-xs">
                <div className="flex justify-between text-gray-500 mb-1">
                  <span>{r.metadata?.filename ?? 'unknown'}</span>
                  <span>score: {r.score?.toFixed(3)}</span>
                </div>
                <p className="text-gray-300 line-clamp-4">{r.content}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
