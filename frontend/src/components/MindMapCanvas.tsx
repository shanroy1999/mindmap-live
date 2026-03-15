import { useCallback, useEffect } from 'react'
import ReactFlow, {
  Background,
  Controls,
  useNodesState,
  useEdgesState,
  type Node as RFNode,
  type Edge as RFEdge,
  type NodeDragHandler,
} from 'react-flow-renderer'
import 'react-flow-renderer/dist/style.css'
import apiClient from '../api/client'
import type { ApiNode, ApiEdge } from '../types/api'

interface Props {
  mapId: string
  title: string
  onLogout: () => void
}

function toRFNode(n: ApiNode): RFNode {
  return {
    id: n.id,
    position: { x: n.x, y: n.y },
    data: { label: n.label },
  }
}

function toRFEdge(e: ApiEdge): RFEdge {
  return {
    id: e.id,
    source: e.source_id,
    target: e.target_id,
    label: e.label ?? undefined,
  }
}

export default function MindMapCanvas({ mapId, title, onLogout }: Props) {
  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])

  useEffect(() => {
    Promise.all([
      apiClient.get<ApiNode[]>(`/api/mindmaps/${mapId}/nodes`),
      apiClient.get<ApiEdge[]>(`/api/mindmaps/${mapId}/edges`),
    ]).then(([nodesRes, edgesRes]) => {
      setNodes(nodesRes.data.map(toRFNode))
      setEdges(edgesRes.data.map(toRFEdge))
    }).catch(console.error)
  }, [mapId, setNodes, setEdges])

  const handleNodeDragStop: NodeDragHandler = useCallback((_event, node) => {
    apiClient
      .patch(`/api/nodes/${node.id}`, { x: node.position.x, y: node.position.y })
      .catch(console.error)
  }, [])

  const handleAddNode = async () => {
    try {
      const res = await apiClient.post<ApiNode>(`/api/mindmaps/${mapId}/nodes`, {
        label: 'New Node',
        x: 0,
        y: 0,
      })
      setNodes((prev) => [...prev, toRFNode(res.data)])
    } catch (err) {
      console.error('Failed to create node', err)
    }
  }

  return (
    <div style={{ width: '100vw', height: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* Toolbar */}
      <div style={toolbarStyle}>
        <span style={{ fontWeight: 700, fontSize: 16, color: '#6366f1' }}>{title}</span>
        <button onClick={handleAddNode} style={btnStyle}>+ New Node</button>
        <button onClick={onLogout} style={{ ...btnStyle, background: '#e5e7eb', color: '#374151' }}>
          Logout
        </button>
      </div>

      {/* Canvas */}
      <div style={{ flex: 1 }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeDragStop={handleNodeDragStop}
          fitView
        >
          <Background />
          <Controls />
        </ReactFlow>
      </div>
    </div>
  )
}

const toolbarStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 12,
  padding: '10px 16px',
  background: '#fff',
  borderBottom: '1px solid #e5e7eb',
  zIndex: 10,
}

const btnStyle: React.CSSProperties = {
  padding: '6px 14px',
  background: '#6366f1',
  color: '#fff',
  border: 'none',
  borderRadius: 6,
  fontSize: 14,
  fontWeight: 600,
  cursor: 'pointer',
}
