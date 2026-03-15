import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
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

interface RelationshipSuggestion {
  source_id: string
  target_id: string
  reason: string
}

interface NodeCluster {
  cluster_name: string
  node_ids: string[]
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
  const bgColor = (data.bgColor as string | undefined) ?? '#fff'

  return (
    <div style={{ ...rfNodeStyle, background: bgColor }}>
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
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [suggestions, setSuggestions] = useState<RelationshipSuggestion[]>([])
  const [clusters, setClusters] = useState<NodeCluster[]>([])
  const [loadingSuggestions, setLoadingSuggestions] = useState(false)
  const [loadingClusters, setLoadingClusters] = useState(false)

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

  // ── AI sidebar ──────────────────────────────────────────────────────────────

  // Fast label lookup for rendering suggestion / cluster cards.
  const nodeById = useMemo(
    () => new Map(nodes.map((n) => [n.id, n.data.label as string])),
    [nodes],
  )

  const handleSuggest = async () => {
    setLoadingSuggestions(true)
    try {
      const res = await apiClient.post<RelationshipSuggestion[]>(
        `/api/mindmaps/${mapId}/suggest-relationships`,
      )
      setSuggestions(res.data)
    } catch (err) {
      console.error('AI suggest failed', err)
    } finally {
      setLoadingSuggestions(false)
    }
  }

  const handleCluster = async () => {
    setLoadingClusters(true)
    try {
      const res = await apiClient.get<NodeCluster[]>(
        `/api/mindmaps/${mapId}/clusters`,
      )
      setClusters(res.data)
      // Build nodeId → bg color map and apply to canvas nodes.
      const colorMap = new Map<string, string>()
      res.data.forEach((c, ci) => {
        c.node_ids.forEach((id) =>
          colorMap.set(id, CLUSTER_BG_COLORS[ci % CLUSTER_BG_COLORS.length]),
        )
      })
      setNodes((prev) =>
        prev.map((n) => ({ ...n, data: { ...n.data, bgColor: colorMap.get(n.id) } })),
      )
    } catch (err) {
      console.error('AI cluster failed', err)
    } finally {
      setLoadingClusters(false)
    }
  }

  const handleClearClusters = () => {
    setClusters([])
    setNodes((prev) =>
      prev.map((n) => ({ ...n, data: { ...n.data, bgColor: undefined } })),
    )
  }

  const handleAddSuggestionEdge = async (s: RelationshipSuggestion) => {
    try {
      const res = await apiClient.post<ApiEdge>(
        `/api/mindmaps/${mapId}/edges`,
        { source_id: s.source_id, target_id: s.target_id },
      )
      setEdges((prev) =>
        addEdge({ source: s.source_id, target: s.target_id, id: res.data.id }, prev),
      )
      setSuggestions((prev) => prev.filter((x) => x !== s))
    } catch (err) {
      console.error('Failed to add suggested edge', err)
    }
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
          onClick={() => setSidebarOpen((o) => !o)}
          style={{ ...btnStyle, background: sidebarOpen ? '#4f46e5' : '#6366f1' }}
        >
          ✨ AI Suggest
        </button>
        <button
          onClick={onLogout}
          style={{ ...btnStyle, background: '#e5e7eb', color: '#374151' }}
        >
          Logout
        </button>
      </div>

      {/* Canvas + Sidebar row */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
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

        {/* AI Sidebar */}
        {sidebarOpen && (
          <div style={sidebarStyle}>
            {/* ── Relationship Suggestions ── */}
            <div style={sidebarSectionStyle}>
              <h3 style={sidebarHeadingStyle}>Relationship Suggestions</h3>
              <button
                onClick={handleSuggest}
                disabled={loadingSuggestions}
                style={{ ...btnStyle, width: '100%', marginBottom: 10 }}
              >
                {loadingSuggestions ? <Spinner /> : 'Find Connections'}
              </button>
              {suggestions.length === 0 && !loadingSuggestions && (
                <p style={emptyTextStyle}>Click "Find Connections" to get AI suggestions.</p>
              )}
              {suggestions.map((s, i) => (
                <div key={i} style={cardStyle}>
                  <div style={cardRowStyle}>
                    <span style={nodePillStyle}>{nodeById.get(s.source_id) ?? s.source_id}</span>
                    <span style={{ color: '#9ca3af', fontSize: 12 }}>→</span>
                    <span style={nodePillStyle}>{nodeById.get(s.target_id) ?? s.target_id}</span>
                  </div>
                  <p style={cardReasonStyle}>{s.reason}</p>
                  <button
                    onClick={() => handleAddSuggestionEdge(s)}
                    style={{ ...btnStyle, fontSize: 12, padding: '4px 10px' }}
                  >
                    Add Edge
                  </button>
                </div>
              ))}
            </div>

            {/* ── Semantic Clusters ── */}
            <div style={sidebarSectionStyle}>
              <h3 style={sidebarHeadingStyle}>Semantic Clusters</h3>
              <button
                onClick={handleCluster}
                disabled={loadingClusters}
                style={{ ...btnStyle, width: '100%', marginBottom: 10 }}
              >
                {loadingClusters ? <Spinner /> : 'Cluster Nodes'}
              </button>
              {clusters.length === 0 && !loadingClusters && (
                <p style={emptyTextStyle}>Click "Cluster Nodes" to group by topic.</p>
              )}
              {clusters.length > 0 && (
                <button
                  onClick={handleClearClusters}
                  style={{ ...btnStyle, background: '#e5e7eb', color: '#374151', width: '100%', marginBottom: 10 }}
                >
                  Clear Clusters
                </button>
              )}
              {clusters.map((c, ci) => (
                <div
                  key={ci}
                  style={{ ...cardStyle, borderLeft: `3px solid ${CLUSTER_DOT_COLORS[ci % CLUSTER_DOT_COLORS.length]}` }}
                >
                  <p style={{ margin: '0 0 6px', fontWeight: 600, fontSize: 13, color: '#111827' }}>
                    {c.cluster_name}
                  </p>
                  {c.node_ids.map((id) => (
                    <div key={id} style={clusterNodeRowStyle}>
                      <span
                        style={{
                          ...clusterDotStyle,
                          background: CLUSTER_DOT_COLORS[ci % CLUSTER_DOT_COLORS.length],
                        }}
                      />
                      <span style={{ fontSize: 12, color: '#374151' }}>
                        {nodeById.get(id) ?? id}
                      </span>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Spinner ───────────────────────────────────────────────────────────────────

function Spinner() {
  return (
    <span style={{
      display: 'inline-block',
      width: 14,
      height: 14,
      border: '2px solid rgba(255,255,255,0.4)',
      borderTopColor: '#fff',
      borderRadius: '50%',
      animation: 'spin 0.7s linear infinite',
      verticalAlign: 'middle',
    }} />
  )
}

// ── Constants ─────────────────────────────────────────────────────────────────

// 6-color palette: purple, teal, coral, amber, blue, green
// BG: soft pastels applied to canvas nodes.
// DOT: saturated versions used for sidebar legend dots.
const CLUSTER_BG_COLORS = ['#ede9fe', '#ccfbf1', '#fee2e2', '#fef3c7', '#dbeafe', '#dcfce7']
const CLUSTER_DOT_COLORS = ['#7c3aed', '#0d9488', '#dc2626', '#d97706', '#2563eb', '#16a34a']

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

const sidebarStyle: React.CSSProperties = {
  width: 300,
  flexShrink: 0,
  overflowY: 'auto',
  background: '#f9fafb',
  borderLeft: '1px solid #e5e7eb',
  display: 'flex',
  flexDirection: 'column',
  gap: 0,
}

const sidebarSectionStyle: React.CSSProperties = {
  padding: '14px 14px 10px',
  borderBottom: '1px solid #e5e7eb',
}

const sidebarHeadingStyle: React.CSSProperties = {
  margin: '0 0 10px',
  fontSize: 13,
  fontWeight: 700,
  color: '#374151',
  textTransform: 'uppercase',
  letterSpacing: '0.04em',
}

const cardStyle: React.CSSProperties = {
  background: '#fff',
  border: '1px solid #e5e7eb',
  borderRadius: 8,
  padding: '10px 12px',
  marginBottom: 8,
}

const cardRowStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 6,
  marginBottom: 6,
  flexWrap: 'wrap',
}

const nodePillStyle: React.CSSProperties = {
  background: '#ede9fe',
  color: '#4f46e5',
  borderRadius: 4,
  padding: '2px 6px',
  fontSize: 12,
  fontWeight: 500,
  maxWidth: 100,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
}

const cardReasonStyle: React.CSSProperties = {
  margin: '0 0 8px',
  fontSize: 12,
  color: '#6b7280',
  lineHeight: 1.4,
}

const emptyTextStyle: React.CSSProperties = {
  margin: 0,
  fontSize: 12,
  color: '#9ca3af',
  textAlign: 'center',
  padding: '8px 0',
}

const clusterNodeRowStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 6,
  marginBottom: 4,
}

const clusterDotStyle: React.CSSProperties = {
  width: 8,
  height: 8,
  borderRadius: '50%',
  flexShrink: 0,
}
