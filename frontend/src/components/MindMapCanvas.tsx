import { useCallback, useEffect, useRef, useState } from 'react'
import ReactFlow, {
  addEdge,
  Background,
  Controls,
  Handle,
  Position,
  useNodesState,
  useEdgesState,
  type Connection,
  type Node as RFNode,
  type Edge as RFEdge,
  type NodeDragHandler,
  type NodeProps,
} from 'react-flow-renderer'
import 'react-flow-renderer/dist/style.css'
import apiClient from '../api/client'
import { useMapSync } from '../hooks/useMapSync'
import type { ApiNode, ApiEdge } from '../types/api'

// ── Types ─────────────────────────────────────────────────────────────────────

interface NodeMovedEvent {
  type: 'node_moved'
  nodeId: string
  x: number
  y: number
}

interface Props {
  mapId: string
  title: string
  onLogout: () => void
}

// ── Editable custom node ──────────────────────────────────────────────────────
// Defined at module level so the nodeTypes object is a stable reference and
// React Flow never needlessly remounts nodes between renders.

function EditableNode({ id, data }: NodeProps) {
  const label = data.label as string
  const editing = data.editing as boolean
  const onCommit = data.onCommit as (id: string, label: string) => void

  return (
    <div style={rfNodeStyle}>
      <Handle type="target" position={Position.Top} style={handleStyle} />
      {editing ? (
        <input
          autoFocus
          defaultValue={label}
          style={rfNodeInputStyle}
          onBlur={(e) => onCommit(id, e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') onCommit(id, e.currentTarget.value)
            if (e.key === 'Escape') onCommit(id, label) // cancel → restore original
          }}
          // Prevent ReactFlow from treating clicks inside the input as canvas clicks.
          onClick={(e) => e.stopPropagation()}
        />
      ) : (
        <span>{label}</span>
      )}
      <Handle type="source" position={Position.Bottom} style={handleStyle} />
    </div>
  )
}

// Stable object — must not be recreated on each render.
const nodeTypes = { editable: EditableNode }

// ── Helpers ───────────────────────────────────────────────────────────────────

function toRFNode(
  n: ApiNode,
  onCommit: (id: string, label: string) => void,
): RFNode {
  return {
    id: n.id,
    type: 'editable',
    position: { x: n.x, y: n.y },
    data: { label: n.label, editing: false, onCommit },
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

// ── Component ─────────────────────────────────────────────────────────────────

export default function MindMapCanvas({ mapId, title, onLogout }: Props) {
  const token = localStorage.getItem('token') ?? ''
  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])
  const [localTitle, setLocalTitle] = useState(title)
  const [editingTitle, setEditingTitle] = useState(false)

  // Keep a ref so the stable `stableCommit` wrapper below always calls the
  // latest version of `commitEdit` without needing to be recreated.
  const commitEditRef = useRef<(id: string, label: string) => void>()

  // Commit an inline node-label edit: update local state + persist to backend.
  const commitEdit = useCallback(
    (id: string, newLabel: string) => {
      setNodes((prev) =>
        prev.map((n) =>
          n.id === id
            ? { ...n, data: { ...n.data, label: newLabel, editing: false } }
            : n,
        ),
      )
      apiClient.patch(`/api/nodes/${id}`, { label: newLabel }).catch(console.error)
    },
    [setNodes],
  )
  commitEditRef.current = commitEdit

  // A truly stable wrapper — safe to pass to toRFNode without causing the
  // useEffect that loads data to re-run when commitEdit is recreated.
  const stableCommit = useCallback((id: string, label: string) => {
    commitEditRef.current?.(id, label)
  }, [])

  // Sync the displayed title whenever the prop changes (e.g. parent refetches).
  useEffect(() => { setLocalTitle(title) }, [title])

  // Load initial node and edge data.
  useEffect(() => {
    Promise.all([
      apiClient.get<ApiNode[]>(`/api/mindmaps/${mapId}/nodes`),
      apiClient.get<ApiEdge[]>(`/api/mindmaps/${mapId}/edges`),
    ])
      .then(([nodesRes, edgesRes]) => {
        setNodes(nodesRes.data.map((n) => toRFNode(n, stableCommit)))
        setEdges(edgesRes.data.map(toRFEdge))
      })
      .catch(console.error)
  }, [mapId, setNodes, setEdges, stableCommit])

  // Apply incoming node_moved events from other users.
  const handleEvent = useCallback(
    (event: Record<string, unknown>) => {
      if (event.type === 'node_moved') {
        const { nodeId, x, y } = event as unknown as NodeMovedEvent
        setNodes((prev) =>
          prev.map((n) => (n.id === nodeId ? { ...n, position: { x, y } } : n)),
        )
      }
    },
    [setNodes],
  )

  const { sendEvent } = useMapSync(mapId, token, { onEvent: handleEvent })

  // ── Feature: drag to move ───────────────────────────────────────────────────

  const handleNodeDragStop: NodeDragHandler = useCallback(
    (_event, node) => {
      apiClient
        .patch(`/api/nodes/${node.id}`, { x: node.position.x, y: node.position.y })
        .catch(console.error)
      sendEvent({
        type: 'node_moved',
        nodeId: node.id,
        x: node.position.x,
        y: node.position.y,
      })
    },
    [sendEvent],
  )

  // ── Feature 1: double-click to edit label inline ────────────────────────────

  const handleNodeDoubleClick = useCallback(
    (_event: React.MouseEvent, node: RFNode) => {
      setNodes((prev) =>
        prev.map((n) =>
          n.id === node.id
            ? { ...n, data: { ...n.data, editing: true } }
            : n,
        ),
      )
    },
    [setNodes],
  )

  // ── Feature 2: drag between handles to create an edge ──────────────────────

  const handleConnect = useCallback(
    async (params: Connection) => {
      console.log('[handleConnect] fired', params)
      if (!params.source || !params.target) return
      try {
        const res = await apiClient.post<ApiEdge>(
          `/api/mindmaps/${mapId}/edges`,
          { source_id: params.source, target_id: params.target },
        )
        setEdges((prev) => addEdge({ ...params, id: res.data.id }, prev))
      } catch (err) {
        console.error('Failed to create edge', err)
      }
    },
    [mapId, setEdges],
  )

  // ── Feature 3: Delete / Backspace removes selected nodes + edges ────────────
  // deleteKeyCode={null} disables ReactFlow's built-in handler so we can call
  // the API before removing items from local state.

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLDivElement>) => {
      if (e.key !== 'Delete' && e.key !== 'Backspace') return
      // Don't intercept while the user is typing in any input / textarea.
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement
      ) return

      const selectedNodeIds = nodes.filter((n) => n.selected).map((n) => n.id)
      const selectedEdgeIds = edges.filter((ed) => ed.selected).map((ed) => ed.id)

      selectedNodeIds.forEach((id) =>
        apiClient.delete(`/api/nodes/${id}`).catch(console.error),
      )
      selectedEdgeIds.forEach((id) =>
        apiClient.delete(`/api/edges/${id}`).catch(console.error),
      )

      if (selectedNodeIds.length > 0)
        setNodes((prev) => prev.filter((n) => !selectedNodeIds.includes(n.id)))
      if (selectedEdgeIds.length > 0)
        setEdges((prev) => prev.filter((ed) => !selectedEdgeIds.includes(ed.id)))
    },
    [nodes, edges, setNodes, setEdges],
  )

  // ── Feature 4: prompt for label when creating a node ───────────────────────

  const handleAddNode = async () => {
    try {
      const res = await apiClient.post<ApiNode>(`/api/mindmaps/${mapId}/nodes`, {
        label: 'New Node',
        x: 100 + Math.random() * 400,
        y: 100 + Math.random() * 300,
      })
      const node = toRFNode(res.data, stableCommit)
      setNodes((prev) => [...prev, { ...node, data: { ...node.data, editing: true } }])
    } catch (err) {
      console.error('Failed to create node', err)
    }
  }

  // ── Feature 5: click title to rename ───────────────────────────────────────

  const commitTitleEdit = () => {
    const trimmed = localTitle.trim()
    if (!trimmed) { setLocalTitle(title); setEditingTitle(false); return }
    setEditingTitle(false)
    if (trimmed === title) return
    apiClient
      .patch(`/api/mindmaps/${mapId}`, { title: trimmed })
      .catch(console.error)
  }

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    // tabIndex makes the wrapper focusable so keyboard events (Delete key) are
    // captured even when no input inside the flow canvas has focus.
    <div
      style={{ width: '100vw', height: '100vh', display: 'flex', flexDirection: 'column' }}
      onKeyDown={handleKeyDown}
      tabIndex={-1}
    >
      {/* Toolbar */}
      <div style={toolbarStyle}>
        {editingTitle ? (
          <input
            autoFocus
            value={localTitle}
            onChange={(e) => setLocalTitle(e.target.value)}
            onBlur={commitTitleEdit}
            onKeyDown={(e) => {
              if (e.key === 'Enter') commitTitleEdit()
              if (e.key === 'Escape') { setLocalTitle(title); setEditingTitle(false) }
            }}
            style={titleInputStyle}
          />
        ) : (
          <span
            title="Click to rename"
            onClick={() => setEditingTitle(true)}
            style={titleStyle}
          >
            {localTitle}
          </span>
        )}
        <button onClick={handleAddNode} style={btnStyle}>+ New Node</button>
        <button
          onClick={onLogout}
          style={{ ...btnStyle, background: '#e5e7eb', color: '#374151' }}
        >
          Logout
        </button>
      </div>

      {/* Canvas */}
      <div style={{ flex: 1 }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeDragStop={handleNodeDragStop}
          onNodeDoubleClick={handleNodeDoubleClick}
          onConnect={handleConnect}
          deleteKeyCode={null}
          fitView
        >
          <Background />
          <Controls />
        </ReactFlow>
      </div>
    </div>
  )
}

// ── Styles ────────────────────────────────────────────────────────────────────

const toolbarStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 12,
  padding: '10px 16px',
  background: '#fff',
  borderBottom: '1px solid #e5e7eb',
  zIndex: 10,
}

const titleStyle: React.CSSProperties = {
  fontWeight: 700,
  fontSize: 16,
  color: '#6366f1',
  cursor: 'pointer',
  borderRadius: 4,
  padding: '2px 4px',
}

const titleInputStyle: React.CSSProperties = {
  fontWeight: 700,
  fontSize: 16,
  color: '#6366f1',
  border: '1px solid #6366f1',
  borderRadius: 4,
  padding: '2px 4px',
  outline: 'none',
  width: 200,
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

// Matches the visual style of react-flow-renderer's default node.
const rfNodeStyle: React.CSSProperties = {
  background: '#fff',
  border: '1px solid #1a192b',
  borderRadius: 3,
  padding: 10,
  fontSize: 12,
  textAlign: 'center',
  minWidth: 60,
}

// Always-visible connection handles — larger dot with a border so they stand out.
const handleStyle: React.CSSProperties = {
  width: 10,
  height: 10,
  background: '#6366f1',
  border: '2px solid #fff',
  borderRadius: '50%',
}

const rfNodeInputStyle: React.CSSProperties = {
  width: 120,
  fontSize: 12,
  padding: '2px 4px',
  border: '1px solid #6366f1',
  borderRadius: 3,
  outline: 'none',
}
