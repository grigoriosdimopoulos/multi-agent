import { Network, Cpu, Wifi, WifiOff } from 'lucide-react'
import type { NodeInfo } from '../../types'

interface Props { nodes: NodeInfo[] }

export function NodeMap({ nodes }: Props) {
  return (
    <div className="p-4 space-y-4 overflow-y-auto h-full">
      <h2 className="text-lg font-semibold text-white">Connected Nodes ({nodes.length})</h2>

      {nodes.length === 0 && (
        <div className="text-center py-12 text-gray-500">
          <Network size={40} className="mx-auto mb-3 opacity-30" />
          <p>No nodes connected.</p>
          <p className="text-xs mt-2">Start a node with: <code className="bg-gray-800 px-1 rounded">python -m node.worker</code></p>
        </div>
      )}

      {/* Network topology visualisation */}
      {nodes.length > 0 && (
        <div className="relative bg-gray-900 rounded-xl border border-gray-800 p-6 min-h-48 flex flex-wrap gap-6 items-center justify-center">
          {/* Master node */}
          <div className="flex flex-col items-center gap-1">
            <div className="w-14 h-14 rounded-full bg-brand-600/30 border-2 border-brand-600 flex items-center justify-center">
              <Cpu size={24} className="text-brand-400" />
            </div>
            <span className="text-xs text-brand-400 font-medium">MASTER</span>
          </div>

          {nodes.map(node => (
            <div key={node.node_id} className="flex flex-col items-center gap-1">
              {/* Line to master (decorative) */}
              <div className="w-px h-6 bg-gray-700 -mb-3 mt-0" />
              <div className={`w-12 h-12 rounded-full border-2 flex items-center justify-center ${
                node.status === 'active' ? 'border-green-500 bg-green-900/20' : 'border-red-700 bg-red-900/10'
              }`}>
                <Network size={20} className={node.status === 'active' ? 'text-green-400' : 'text-red-600'} />
              </div>
              <div className="text-center">
                <div className="flex items-center gap-1 justify-center">
                  {node.status === 'active'
                    ? <Wifi size={10} className="text-green-400" />
                    : <WifiOff size={10} className="text-red-400" />}
                  <span className="text-[11px] font-medium text-white">{node.node_id}</span>
                </div>
                <span className="text-[10px] text-gray-500">{node.host}:{node.port}</span>
                <span className="text-[10px] text-gray-600 block">{node.agent_ids.length} agents</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Node details */}
      <div className="space-y-2">
        {nodes.map(node => (
          <div key={node.node_id} className="bg-gray-800 rounded-xl border border-gray-700 p-3">
            <div className="flex justify-between items-start">
              <div>
                <div className="flex items-center gap-2">
                  <span className={`w-2 h-2 rounded-full ${node.status === 'active' ? 'bg-green-400' : 'bg-red-500'}`} />
                  <span className="font-medium text-white text-sm">{node.node_id}</span>
                </div>
                <p className="text-xs text-gray-400 mt-0.5">{node.host}:{node.port}</p>
              </div>
              <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                node.status === 'active' ? 'bg-green-900 text-green-300' : 'bg-red-900 text-red-300'
              }`}>
                {node.status}
              </span>
            </div>
            {node.agent_ids.length > 0 && (
              <div className="mt-2">
                <p className="text-xs text-gray-500 mb-1">Agents:</p>
                <div className="flex flex-wrap gap-1">
                  {node.agent_ids.map(id => (
                    <span key={id} className="text-[10px] bg-gray-700 text-gray-300 px-1.5 py-0.5 rounded">{id}</span>
                  ))}
                </div>
              </div>
            )}
            <p className="text-[10px] text-gray-600 mt-2">
              Last seen: {new Date(node.last_seen).toLocaleTimeString()}
            </p>
          </div>
        ))}
      </div>
    </div>
  )
}
