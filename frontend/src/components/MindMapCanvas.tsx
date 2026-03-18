import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import ReactFlow, {
  addEdge,
  Background,
  Controls,
  MiniMap,
  Handle,
  Position,
  useNodesState,
  useEdgesState,
  useStore,
  type Connection,
  type Node as RFNode,
  type Edge as RFEdge,
  type NodeDragHandler,
  type NodeProps,
} from 'react-flow-renderer'
import 'react-flow-renderer/dist/style.css'
import apiClient from '../api/client'
import { useMapSync, type PresenceMap } from '../hooks/useMapSync'
import type { ApiNode, ApiEdge } from '../types/api'

// ── Types ─────────────────────────────────────────────────────────────────────

interface NodeMovedEvent {
  type: 'node_moved'
  nodeId: string
  x: number
  y: number
}

interface LayoutNode {
  id: string
  x: number
  y: number
  level: number
}

interface LayoutEdge {
  source_id: string
  target_id: string
  reason: string
}

interface LayoutCluster {
  cluster_name: string
  node_ids: string[]
  color: string
}

interface AutoLayoutResponse {
  nodes: LayoutNode[]
  edges_to_add: LayoutEdge[]
  clusters: LayoutCluster[]
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

interface ContextMenu {
  x: number
  y: number
  nodeId: string
}


interface Props {
  mapId: string
  title: string
  onLogout: () => void
  onBackToDashboard: () => void
}

// ── Node type config ───────────────────────────────────────────────────────────

type NodeType = 'idea' | 'decision' | 'question' | 'note'

const NODE_TYPE_CONFIG: Record<NodeType, { label: string; icon: string; accent: string }> = {
  idea:     { label: 'Idea',     icon: '💡', accent: '#6366f1' },
  decision: { label: 'Decision', icon: '✓',  accent: '#f59e0b' },
  question: { label: 'Question', icon: '?',  accent: '#ef4444' },
  note:     { label: 'Note',     icon: '📝', accent: '#71717a' },
}

// ── Editable custom node ──────────────────────────────────────────────────────
// Defined at module level so the nodeTypes object is a stable reference and
// React Flow never needlessly remounts nodes between renders.

function EditableNode({ id, data, selected }: NodeProps) {
  const label = data.label as string
  const editing = data.editing as boolean
  const onCommit = data.onCommit as (id: string, label: string) => void
  const bgColor = (data.bgColor as string | undefined) ?? '#27272a'
  const nodeType = ((data.nodeType as string | undefined) ?? 'idea') as NodeType
  const typeConfig = NODE_TYPE_CONFIG[nodeType]

  return (
    <div
      className={`relative rounded text-xs text-center min-w-[60px] px-2.5 py-2 border transition-colors ${
        selected
          ? 'border-indigo-400 shadow-lg shadow-indigo-900/40'
          : 'border-white/15'
      }`}
      style={{
        background: bgColor,
        color: '#fff',
        borderLeftColor: typeConfig.accent,
        borderLeftWidth: 3,
      }}
    >
      {/* Type badge — top-right corner */}
      <span
        className="absolute -top-2 -right-2 w-4 h-4 flex items-center justify-center bg-zinc-800 border border-white/10 rounded-full text-[8px] leading-none select-none"
        style={{ color: typeConfig.accent }}
      >
        {typeConfig.icon}
      </span>
      <Handle type="target" position={Position.Top} style={handleStyle} />
      {editing ? (
        <input
          autoFocus
          defaultValue={label}
          className="w-28 text-xs px-1 py-0.5 bg-zinc-700 border border-indigo-500 rounded outline-none text-white"
          onBlur={(e) => onCommit(id, e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') onCommit(id, e.currentTarget.value)
            if (e.key === 'Escape') onCommit(id, label)
          }}
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

// ── Presence overlay ──────────────────────────────────────────────────────────
// Rendered as a child of <ReactFlow> so it has access to the internal viewport
// transform via useStore.  Absolute-positioned cursors sit outside the
// .react-flow__viewport layer so they are unaffected by its CSS transform —
// we manually compute screen coords from canvas coords + the stored transform.

interface PresenceLayerProps {
  presenceMap: PresenceMap
  containerRef: React.RefObject<HTMLDivElement>
  sendCursorMove: (x: number, y: number) => void
}

function PresenceLayer({ presenceMap, containerRef, sendCursorMove }: PresenceLayerProps) {
  // transform = [panX, panY, zoom] — updates whenever the user pans or zooms.
  const transform = useStore(
    (s: { transform: [number, number, number] }) => s.transform,
  )

  // Keep transform in a ref so the mousemove listener reads the latest value
  // without needing to be re-attached on every pan/zoom.
  const transformRef = useRef(transform)
  useEffect(() => { transformRef.current = transform }, [transform])

  // Attach a single mousemove listener to the canvas wrapper div.
  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const handleMove = (e: MouseEvent) => {
      const rect = container.getBoundingClientRect()
      const [panX, panY, zoom] = transformRef.current
      sendCursorMove(
        (e.clientX - rect.left - panX) / zoom,
        (e.clientY - rect.top - panY) / zoom,
      )
    }
    container.addEventListener('mousemove', handleMove)
    return () => container.removeEventListener('mousemove', handleMove)
  }, [containerRef, sendCursorMove])

  return (
    <>
      {[...presenceMap.entries()]
        .filter(([, u]) => u.x !== undefined && u.y !== undefined)
        .map(([userId, u]) => {
          const [panX, panY, zoom] = transform
          const sx = u.x! * zoom + panX
          const sy = u.y! * zoom + panY
          return (
            <div
              key={userId}
              style={{
                position: 'absolute',
                left: sx,
                top: sy,
                pointerEvents: 'none',
                zIndex: 1000,
              }}
            >
              <svg
                width="16"
                height="20"
                viewBox="0 0 16 20"
                style={{ display: 'block', filter: 'drop-shadow(0 1px 2px rgba(0,0,0,0.5))' }}
              >
                <path
                  d="M0,0 L0,16 L4.5,12 L7.5,18.5 L9.5,17.5 L6.5,11 L12,11 Z"
                  fill={u.color}
                  stroke="#18181b"
                  strokeWidth="1.5"
                  strokeLinejoin="round"
                />
              </svg>
              <div
                style={{
                  position: 'absolute',
                  left: 14,
                  top: 0,
                  background: u.color,
                  color: '#fff',
                  fontSize: 10,
                  fontWeight: 600,
                  padding: '2px 6px',
                  borderRadius: 4,
                  whiteSpace: 'nowrap',
                  fontFamily: 'system-ui, sans-serif',
                  lineHeight: '14px',
                  boxShadow: '0 1px 3px rgba(0,0,0,0.4)',
                }}
              >
                {u.displayName}
              </div>
            </div>
          )
        })}
    </>
  )
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function toRFNode(
  n: ApiNode,
  onCommit: (id: string, label: string) => void,
): RFNode {
  return {
    id: n.id,
    type: 'editable',
    position: { x: n.x, y: n.y },
    data: { label: n.label, editing: false, onCommit, nodeType: n.node_type ?? 'idea' },
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

// ── Presence color ────────────────────────────────────────────────────────────
// Mirrors the Python backend algorithm: index = uuid_as_int % palette_length.
// Uses BigInt so the full 128-bit UUID value is preserved (matching the server).

const _PRESENCE_COLORS = ['#f472b6', '#34d399', '#60a5fa', '#fb923c', '#a78bfa', '#facc15']

function presenceColor(userId: string): string {
  try {
    const n = BigInt('0x' + userId.replace(/-/g, ''))
    return _PRESENCE_COLORS[Number(n % BigInt(_PRESENCE_COLORS.length))]
  } catch {
    return _PRESENCE_COLORS[0]
  }
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function MindMapCanvas({ mapId, title, onLogout, onBackToDashboard }: Props) {
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
  const [typePickerOpen, setTypePickerOpen] = useState(false)
  const [contextMenu, setContextMenu] = useState<ContextMenu | null>(null)
  const typePickerRef = useRef<HTMLDivElement>(null)
  const [layoutLoading, setLayoutLoading] = useState(false)
  const [toast, setToast] = useState<string | null>(null)
  const [shareModalOpen, setShareModalOpen] = useState(false)
  const [isPublic, setIsPublic] = useState<boolean | null>(null)
  const [copyConfirmed, setCopyConfirmed] = useState(false)

  // ── Presence state ─────────────────────────────────────────────────────────
  // presenceMap (remote peers) comes from the useMapSync hook.
  // currentUser (local user info for "You" pill) is fetched once from the API.
  const [currentUser, setCurrentUser] = useState<{ displayName: string; color: string } | null>(null)
  const canvasContainerRef = useRef<HTMLDivElement>(null)

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

  // ── Share modal ─────────────────────────────────────────────────────────────

  const openShareModal = useCallback(async () => {
    setShareModalOpen(true)
    if (isPublic === null) {
      try {
        const res = await apiClient.get<{ is_public: boolean }>(`/api/mindmaps/${mapId}`)
        setIsPublic(res.data.is_public)
      } catch {
        setIsPublic(false)
      }
    }
  }, [mapId, isPublic])

  const handleTogglePublic = useCallback(async () => {
    const next = !isPublic
    setIsPublic(next)
    try {
      console.log('[Share] PATCH /api/mindmaps/%s →', mapId, { is_public: next })
      const res = await apiClient.patch(`/api/mindmaps/${mapId}`, { is_public: next })
      console.log('[Share] PATCH response:', res.status, res.data)
    } catch (err: unknown) {
      console.error('[Share] PATCH failed:', err)
      setIsPublic(!next) // revert optimistic update
      setToast('Could not update sharing settings — try again')
      setTimeout(() => setToast(null), 3000)
    }
  }, [mapId, isPublic])

  const handleCopyLink = useCallback(() => {
    const url = `https://mindmap-live.vercel.app/maps/${mapId}`
    navigator.clipboard.writeText(url).catch(() => {})
    setCopyConfirmed(true)
    setTimeout(() => setCopyConfirmed(false), 2000)
  }, [mapId])

  // Close share modal on Escape.
  useEffect(() => {
    if (!shareModalOpen) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setShareModalOpen(false) }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [shareModalOpen])

  // Sync the displayed title whenever the prop changes (e.g. parent refetches).
  useEffect(() => { setLocalTitle(title) }, [title])

  // Load initial node and edge data.
  useEffect(() => {
    console.log('[loadMap] fetching mapId:', mapId)
    Promise.all([
      apiClient.get<ApiNode[]>(`/api/mindmaps/${mapId}/nodes`),
      apiClient.get<ApiEdge[]>(`/api/mindmaps/${mapId}/edges`),
    ])
      .then(([nodesRes, edgesRes]) => {
        console.log('[loadMap] nodes response:', nodesRes.data)
        console.log('[loadMap] edges response:', edgesRes.data)
        setNodes(nodesRes.data.map((n) => toRFNode(n, stableCommit)))
        setEdges(edgesRes.data.map(toRFEdge))
      })
      .catch((err) => {
        console.error('[loadMap] error:', err)
      })
  }, [mapId, setNodes, setEdges, stableCommit])

  // Close type picker when clicking outside.
  useEffect(() => {
    if (!typePickerOpen) return
    const handleMouseDown = (e: MouseEvent) => {
      if (typePickerRef.current && !typePickerRef.current.contains(e.target as Node)) {
        setTypePickerOpen(false)
      }
    }
    document.addEventListener('mousedown', handleMouseDown)
    return () => document.removeEventListener('mousedown', handleMouseDown)
  }, [typePickerOpen])

  // Fetch the current user's profile once so we can show "You" in the toolbar.
  useEffect(() => {
    apiClient
      .get<{ id: string; display_name: string }>('/api/auth/me')
      .then((res) => {
        setCurrentUser({
          displayName: res.data.display_name,
          color: presenceColor(res.data.id),
        })
      })
      .catch(console.error)
  }, [])

  // Apply incoming events from other users.
  // Presence events (cursor_move, user_joined, user_left, room_state) are handled
  // by useMapSync internally. Only non-presence events arrive here.
  // user_joined and user_left are also forwarded by the hook so we can show toasts.
  const handleEvent = useCallback(
    (event: Record<string, unknown>) => {
      const type = event.type as string
      if (type === 'node_moved') {
        const { nodeId, x, y } = event as unknown as NodeMovedEvent
        setNodes((prev) =>
          prev.map((n) => (n.id === nodeId ? { ...n, position: { x, y } } : n)),
        )
      } else if (type === 'user_joined') {
        const { displayName } = event as { displayName: string }
        setToast(`${displayName} joined the map`)
        setTimeout(() => setToast(null), 3000)
      } else if (type === 'user_left') {
        const { displayName } = event as { displayName: string }
        setToast(`${displayName} left the map`)
        setTimeout(() => setToast(null), 3000)
      }
    },
    [setNodes],
  )

  const { sendEvent, sendCursorMove, presenceMap } = useMapSync(mapId, token, { onEvent: handleEvent })

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
      if (e.key === 'Escape') {
        setContextMenu(null)
        setTypePickerOpen(false)
        return
      }
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

  // ── Feature 4: type picker → create node ───────────────────────────────────

  const createNode = useCallback(
    async (nodeType: NodeType) => {
      setTypePickerOpen(false)
      const body = {
        label: 'New Node',
        node_type: nodeType,
        x: 100 + Math.random() * 400,
        y: 100 + Math.random() * 300,
      }
      console.log('[createNode] selected type:', nodeType)
      console.log('[createNode] POST body:', body)
      try {
        const res = await apiClient.post<ApiNode>(`/api/mindmaps/${mapId}/nodes`, body)
        console.log('[createNode] response:', res.data)
        const node = toRFNode(res.data, stableCommit)
        console.log('[createNode] RFNode to add:', node)
        setNodes((prev) => {
          const next = [...prev, { ...node, data: { ...node.data, editing: true } }]
          console.log('[createNode] setNodes — total nodes now:', next.length)
          return next
        })
      } catch (err) {
        console.error('[createNode] error:', err)
      }
    },
    [mapId, stableCommit, setNodes],
  )

  // ── Feature 5: right-click context menu → change node type ─────────────────

  const handleNodeContextMenu = useCallback(
    (event: React.MouseEvent, node: RFNode) => {
      event.preventDefault()
      setContextMenu({ x: event.clientX, y: event.clientY, nodeId: node.id })
    },
    [],
  )

  const handleChangeNodeType = useCallback(
    (nodeId: string, nodeType: NodeType) => {
      setContextMenu(null)
      setNodes((prev) =>
        prev.map((n) =>
          n.id === nodeId ? { ...n, data: { ...n.data, nodeType } } : n,
        ),
      )
      apiClient.patch(`/api/nodes/${nodeId}`, { node_type: nodeType }).catch(console.error)
    },
    [setNodes],
  )

  // ── Feature 6: click title to rename ───────────────────────────────────────

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

  // ── Feature: auto-layout ───────────────────────────────────────────────────

  const handleAutoLayout = useCallback(async () => {
    setLayoutLoading(true)
    try {
      const res = await apiClient.post<AutoLayoutResponse>(
        `/api/mindmaps/${mapId}/auto-layout`,
      )
      const { nodes: layoutNodes, edges_to_add, clusters: layoutClusters } = res.data

      // Map from Claude's bright accent colours to dark node backgrounds.
      const LAYOUT_CLUSTER_BG: Record<string, string> = {
        '#6366f1': '#1e1b4b',
        '#f59e0b': '#451a03',
        '#ef4444': '#450a0a',
        '#10b981': '#022c22',
      }
      const colorMap = new Map<string, string>()
      layoutClusters.forEach((c) => {
        const bg = LAYOUT_CLUSTER_BG[c.color] ?? '#27272a'
        c.node_ids.forEach((id) => colorMap.set(id, bg))
      })

      // Sort by level so root animates first, then children, then grandchildren.
      const sortedByLevel = [...layoutNodes].sort((a, b) => a.level - b.level)
      const animOrder = new Map(sortedByLevel.map((n, i) => [n.id, i]))

      // Step 1: arm CSS transitions on all nodes (positions are still unchanged).
      setNodes((prev) =>
        prev.map((n) => ({
          ...n,
          style: {
            ...n.style,
            transition: `transform 600ms cubic-bezier(0.34,1.56,0.64,1) ${
              (animOrder.get(n.id) ?? 0) * 50
            }ms`,
          },
        })),
      )

      // Step 2: after two browser frames (guarantees transition is painted before
      // positions update) move every node to its new position and apply cluster colours.
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          const posMap = new Map(layoutNodes.map((n) => [n.id, n]))
          setNodes((prev) =>
            prev.map((n) => {
              const pos = posMap.get(n.id)
              return {
                ...n,
                position: pos ? { x: pos.x, y: pos.y } : n.position,
                data: { ...n.data, bgColor: colorMap.get(n.id) },
              }
            }),
          )
        })
      })

      // Persist every repositioned node to the backend (fire-and-forget).
      layoutNodes.forEach((ln) =>
        apiClient.patch(`/api/nodes/${ln.id}`, { x: ln.x, y: ln.y }).catch(console.error),
      )

      // Add suggested edges to canvas + backend.
      await Promise.allSettled(
        edges_to_add.map(async (e) => {
          try {
            const edgeRes = await apiClient.post<ApiEdge>(
              `/api/mindmaps/${mapId}/edges`,
              { source_id: e.source_id, target_id: e.target_id },
            )
            setEdges((prev) =>
              addEdge(
                { source: e.source_id, target: e.target_id, id: edgeRes.data.id },
                prev,
              ),
            )
          } catch {
            // Silently skip edges that already exist or reference unknown nodes.
          }
        }),
      )

      // After the last node finishes animating, remove the transition style
      // (so subsequent drags feel instant) and show the success toast.
      const totalMs = layoutNodes.length * 50 + 600 + 150
      setTimeout(() => {
        setNodes((prev) =>
          prev.map((n) => ({ ...n, style: { ...n.style, transition: undefined } })),
        )
        setToast('Map organized by AI ✨')
        setTimeout(() => setToast(null), 2500)
      }, totalMs)
    } catch (err) {
      console.error('Auto layout failed', err)
    } finally {
      setLayoutLoading(false)
    }
  }, [mapId, setNodes, setEdges])

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
      <div className="flex items-center gap-3 px-4 py-2.5 bg-zinc-900 border-b border-white/10 z-10 shrink-0">
        <button
          onClick={onBackToDashboard}
          className="px-3 py-1.5 text-xs font-semibold bg-zinc-800 hover:bg-zinc-700 text-white/60 hover:text-white border border-white/10 rounded-md transition-colors cursor-pointer"
        >
          ← My Maps
        </button>
        <div className="h-4 w-px bg-white/10" />
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
            className="text-sm font-bold text-indigo-400 bg-zinc-800 border border-indigo-500 rounded px-2 py-0.5 outline-none w-48"
          />
        ) : (
          <span
            title="Click to rename"
            onClick={() => setEditingTitle(true)}
            className="text-sm font-bold text-indigo-400 cursor-pointer px-2 py-0.5 rounded hover:bg-white/5 transition-colors select-none"
          >
            <span className="mr-1 opacity-70">✦</span>{localTitle}
          </span>
        )}
        <div className="h-4 w-px bg-white/10" />

        {/* New Node button with type picker popover */}
        <div className="relative" ref={typePickerRef}>
          <button
            onClick={() => setTypePickerOpen((o) => !o)}
            className={`px-3 py-1.5 text-xs font-semibold border rounded-md transition-colors cursor-pointer ${
              typePickerOpen
                ? 'bg-zinc-700 border-white/20 text-white'
                : 'bg-zinc-800 hover:bg-zinc-700 border-white/10 text-white'
            }`}
          >
            + New Node
          </button>
          {typePickerOpen && (
            <div className="absolute top-full left-0 mt-1.5 bg-zinc-900 border border-white/10 rounded-lg p-1.5 flex flex-col gap-0.5 z-50 shadow-xl min-w-[140px]">
              {(Object.entries(NODE_TYPE_CONFIG) as [NodeType, typeof NODE_TYPE_CONFIG[NodeType]][]).map(
                ([type, cfg]) => (
                  <button
                    key={type}
                    onClick={() => createNode(type)}
                    className="flex items-center gap-2 px-2.5 py-1.5 text-xs text-white/70 hover:text-white hover:bg-zinc-800 rounded-md transition-colors cursor-pointer text-left"
                  >
                    <span
                      className="w-2 h-2 rounded-full shrink-0"
                      style={{ background: cfg.accent }}
                    />
                    <span className="flex-1">{cfg.label}</span>
                    <span className="text-white/40">{cfg.icon}</span>
                  </button>
                ),
              )}
            </div>
          )}
        </div>

        <button
          onClick={handleAutoLayout}
          disabled={layoutLoading}
          className="px-3 py-1.5 text-xs font-semibold bg-zinc-800 hover:bg-zinc-700 disabled:opacity-50 disabled:cursor-not-allowed text-white border border-white/10 rounded-md transition-colors cursor-pointer"
        >
          ✦ Auto Layout
        </button>
        <button
          onClick={() => setSidebarOpen((o) => !o)}
          className={`px-3 py-1.5 text-xs font-semibold border rounded-md transition-colors cursor-pointer ${
            sidebarOpen
              ? 'bg-indigo-500 hover:bg-indigo-400 border-indigo-400 text-white'
              : 'bg-zinc-800 hover:bg-zinc-700 border-white/10 text-white'
          }`}
        >
          ✨ AI Suggest
        </button>
        <button
          onClick={openShareModal}
          className="px-3 py-1.5 text-xs font-semibold bg-zinc-800 hover:bg-zinc-700 text-white border border-white/10 rounded-md transition-colors cursor-pointer"
        >
          Share
        </button>
        <div className="flex-1" />

        {/* Online users indicator */}
        {(currentUser || presenceMap.size > 0) && (
          <div className="flex items-center gap-1.5">
            {/* Current user — always shown first, labeled "You" */}
            {currentUser && (
              <div
                title={currentUser.displayName}
                className="flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10px] font-semibold border select-none"
                style={{
                  borderColor: `${currentUser.color}50`,
                  background: `${currentUser.color}20`,
                  color: currentUser.color,
                }}
              >
                <span
                  className="w-1.5 h-1.5 rounded-full shrink-0"
                  style={{ background: currentUser.color }}
                />
                <span>You</span>
              </div>
            )}
            {/* Remote peers — up to 4 alongside "You" */}
            {[...presenceMap.entries()].slice(0, 4).map(([userId, u]) => (
              <div
                key={userId}
                title={u.displayName}
                className="flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10px] font-semibold border select-none"
                style={{
                  borderColor: `${u.color}50`,
                  background: `${u.color}20`,
                  color: u.color,
                }}
              >
                <span
                  className="w-1.5 h-1.5 rounded-full shrink-0 animate-pulse"
                  style={{ background: u.color }}
                />
                <span className="max-w-[64px] truncate">{u.displayName}</span>
              </div>
            ))}
            {presenceMap.size > 4 && (
              <span className="text-[10px] text-white/40">+{presenceMap.size - 4}</span>
            )}
          </div>
        )}

        <div className="h-4 w-px bg-white/10" />
        <button
          onClick={onLogout}
          className="px-3 py-1.5 text-xs font-semibold bg-zinc-800 hover:bg-zinc-700 text-white/60 hover:text-white border border-white/10 rounded-md transition-colors cursor-pointer"
        >
          Logout
        </button>
      </div>

      {/* Canvas + Sidebar row */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {/* Canvas — bg-color set on the wrapper; Background component colours the dot pattern */}
        <div className="flex-1 bg-[#09090b] relative" ref={canvasContainerRef}>

          {/* Auto-layout loading overlay */}
          {layoutLoading && (
            <div className="absolute inset-0 z-50 flex flex-col items-center justify-center gap-3 bg-black/55 backdrop-blur-[2px]">
              <div
                style={{
                  width: 28,
                  height: 28,
                  border: '3px solid rgba(255,255,255,0.2)',
                  borderTopColor: '#a5b4fc',
                  borderRadius: '50%',
                  animation: 'spin 0.8s linear infinite',
                }}
              />
              <p className="text-sm font-medium text-white/80 select-none">
                AI is organizing your map…
              </p>
            </div>
          )}

          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeDragStop={handleNodeDragStop}
            onNodeDoubleClick={handleNodeDoubleClick}
            onNodeContextMenu={handleNodeContextMenu}
            onConnect={handleConnect}
            onPaneClick={() => setContextMenu(null)}
            deleteKeyCode={null}
            fitView
          >
            <Background color="#27272a" />
            <MiniMap
              style={{ background: '#18181b' }}
              nodeColor="#6366f1"
              maskColor="rgba(0,0,0,0.4)"
              position="bottom-right"
            />
            <Controls position="bottom-right" />
            <PresenceLayer
              presenceMap={presenceMap}
              containerRef={canvasContainerRef}
              sendCursorMove={sendCursorMove}
            />
          </ReactFlow>
        </div>

        {/* AI Sidebar */}
        {sidebarOpen && (
          <div className="w-72 shrink-0 bg-zinc-900 border-l border-white/10 flex flex-col overflow-y-auto">
            {/* ── Relationship Suggestions ── */}
            <div className="p-4 border-b border-white/10">
              <h3 className="text-[10px] font-bold uppercase tracking-widest text-white/30 mb-3">
                Relationship Suggestions
              </h3>
              <button
                onClick={handleSuggest}
                disabled={loadingSuggestions}
                className="w-full px-3 py-2 text-xs font-semibold bg-zinc-800 hover:bg-zinc-700 disabled:opacity-50 text-white border border-white/10 rounded-md transition-colors cursor-pointer mb-3"
              >
                {loadingSuggestions ? <Spinner /> : 'Find Connections'}
              </button>
              {suggestions.length === 0 && !loadingSuggestions && (
                <p className="text-xs text-white/25 text-center py-2">
                  Click &quot;Find Connections&quot; to get AI suggestions.
                </p>
              )}
              <div className="flex flex-col gap-2">
                {suggestions.map((s, i) => (
                  <div key={i} className="bg-zinc-800 border border-white/10 rounded-lg p-3 flex flex-col gap-2">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span className="bg-indigo-950 text-indigo-300 border border-indigo-800/50 rounded px-1.5 py-0.5 text-[11px] font-medium max-w-[90px] truncate">
                        {nodeById.get(s.source_id) ?? s.source_id}
                      </span>
                      <span className="text-white/30 text-xs">→</span>
                      <span className="bg-indigo-950 text-indigo-300 border border-indigo-800/50 rounded px-1.5 py-0.5 text-[11px] font-medium max-w-[90px] truncate">
                        {nodeById.get(s.target_id) ?? s.target_id}
                      </span>
                    </div>
                    <p className="text-[11px] text-white/40 leading-relaxed">{s.reason}</p>
                    <button
                      onClick={() => handleAddSuggestionEdge(s)}
                      className="self-start px-2.5 py-1 text-[11px] font-semibold bg-indigo-500 hover:bg-indigo-400 text-white rounded transition-colors cursor-pointer"
                    >
                      Add Edge
                    </button>
                  </div>
                ))}
              </div>
            </div>

            {/* ── Semantic Clusters ── */}
            <div className="p-4">
              <h3 className="text-[10px] font-bold uppercase tracking-widest text-white/30 mb-3">
                Semantic Clusters
              </h3>
              <button
                onClick={handleCluster}
                disabled={loadingClusters}
                className="w-full px-3 py-2 text-xs font-semibold bg-zinc-800 hover:bg-zinc-700 disabled:opacity-50 text-white border border-white/10 rounded-md transition-colors cursor-pointer mb-2"
              >
                {loadingClusters ? <Spinner /> : 'Cluster Nodes'}
              </button>
              {clusters.length > 0 && (
                <button
                  onClick={handleClearClusters}
                  className="w-full px-3 py-2 text-xs font-semibold bg-transparent hover:bg-white/5 text-white/40 hover:text-white/70 border border-white/10 rounded-md transition-colors cursor-pointer mb-3"
                >
                  Clear Clusters
                </button>
              )}
              {clusters.length === 0 && !loadingClusters && (
                <p className="text-xs text-white/25 text-center py-2">
                  Click &quot;Cluster Nodes&quot; to group by topic.
                </p>
              )}
              <div className="flex flex-col gap-2">
                {clusters.map((c, ci) => (
                  <div
                    key={ci}
                    className="bg-zinc-800 border border-white/10 rounded-lg p-3"
                    style={{ borderLeftColor: CLUSTER_DOT_COLORS[ci % CLUSTER_DOT_COLORS.length], borderLeftWidth: 3 }}
                  >
                    <p className="text-xs font-semibold text-white mb-2">{c.cluster_name}</p>
                    <div className="flex flex-col gap-1">
                      {c.node_ids.map((id) => (
                        <div key={id} className="flex items-center gap-2">
                          <span
                            className="w-1.5 h-1.5 rounded-full shrink-0"
                            style={{ background: CLUSTER_DOT_COLORS[ci % CLUSTER_DOT_COLORS.length] }}
                          />
                          <span className="text-[11px] text-white/60 truncate">
                            {nodeById.get(id) ?? id}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Toast notification */}
      {toast && (
        <div
          className="fixed bottom-6 left-1/2 z-[200] px-4 py-2.5 bg-zinc-800 border border-white/10 rounded-lg text-sm text-white font-medium shadow-xl pointer-events-none"
          style={{ animation: 'toastSlideUp 0.3s ease forwards' }}
        >
          {toast}
        </div>
      )}

      {/* Share modal */}
      {shareModalOpen && (
        <div
          className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 px-4"
          onClick={() => setShareModalOpen(false)}
        >
          <div
            className="w-full max-w-sm bg-zinc-900 border border-white/10 rounded-2xl p-6 shadow-2xl flex flex-col gap-5"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="flex items-center justify-between">
              <h2 className="text-base font-bold text-white">Share Map</h2>
              <button
                onClick={() => setShareModalOpen(false)}
                className="text-white/40 hover:text-white transition-colors cursor-pointer leading-none text-lg"
              >
                ✕
              </button>
            </div>

            {/* URL + copy */}
            <div className="flex flex-col gap-2">
              <label className="text-[11px] font-semibold uppercase tracking-widest text-white/30">
                Map Link
              </label>
              <div className="flex gap-2">
                <input
                  readOnly
                  value={`https://mindmap-live.vercel.app/maps/${mapId}`}
                  onFocus={(e) => e.target.select()}
                  className="flex-1 min-w-0 text-xs bg-zinc-800 border border-white/10 rounded-md px-3 py-2 text-white/70 outline-none"
                />
                <button
                  onClick={handleCopyLink}
                  className={`shrink-0 px-3 py-2 text-xs font-semibold rounded-md border transition-colors cursor-pointer ${
                    copyConfirmed
                      ? 'bg-emerald-500/20 border-emerald-500/40 text-emerald-400'
                      : 'bg-zinc-800 hover:bg-zinc-700 border-white/10 text-white'
                  }`}
                >
                  {copyConfirmed ? 'Copied!' : 'Copy Link'}
                </button>
              </div>
            </div>

            {/* Public toggle */}
            <div className="flex items-center justify-between gap-4 pt-3 border-t border-white/10">
              <div className="flex flex-col gap-1">
                <span className="text-sm font-medium text-white">Anyone with the link can join</span>
                <span className="text-xs text-white/40">
                  {isPublic
                    ? 'Map is public — any authenticated user can view and edit.'
                    : 'Map is private — only you can access it.'}
                </span>
              </div>
              <button
                onClick={handleTogglePublic}
                disabled={isPublic === null}
                aria-pressed={isPublic ?? false}
                className="shrink-0 relative rounded-full transition-colors cursor-pointer disabled:opacity-40"
                style={{
                  width: 40,
                  height: 22,
                  background: isPublic ? '#6366f1' : '#3f3f46',
                }}
              >
                <span
                  className="absolute top-0.5 bg-white rounded-full shadow"
                  style={{
                    width: 18,
                    height: 18,
                    left: 2,
                    transform: isPublic ? 'translateX(18px)' : 'translateX(0)',
                    transition: 'transform 0.2s',
                  }}
                />
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Right-click context menu */}
      {contextMenu && (
        <>
          {/* Invisible overlay to catch outside clicks */}
          <div
            className="fixed inset-0 z-40"
            onClick={() => setContextMenu(null)}
          />
          <div
            className="fixed z-50 bg-zinc-900 border border-white/10 rounded-lg shadow-xl py-1 min-w-[160px]"
            style={{ top: contextMenu.y, left: contextMenu.x }}
          >
            <p className="px-3 py-1 text-[10px] uppercase font-bold tracking-wider text-white/30">
              Change type
            </p>
            {(Object.entries(NODE_TYPE_CONFIG) as [NodeType, typeof NODE_TYPE_CONFIG[NodeType]][]).map(
              ([type, cfg]) => (
                <button
                  key={type}
                  onClick={() => handleChangeNodeType(contextMenu.nodeId, type)}
                  className="w-full flex items-center gap-2.5 px-3 py-1.5 text-xs text-white/70 hover:text-white hover:bg-zinc-800 transition-colors cursor-pointer"
                >
                  <span
                    className="w-2 h-2 rounded-full shrink-0"
                    style={{ background: cfg.accent }}
                  />
                  <span>{cfg.icon}</span>
                  <span>{cfg.label}</span>
                </button>
              ),
            )}
          </div>
        </>
      )}
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
// BG: dark saturated versions for canvas nodes (white text remains readable).
// DOT: brighter versions used for sidebar legend dots and card accents.
const CLUSTER_BG_COLORS = ['#3730a3', '#134e4a', '#7f1d1d', '#78350f', '#1e3a8a', '#14532d']
const CLUSTER_DOT_COLORS = ['#818cf8', '#2dd4bf', '#f87171', '#fbbf24', '#60a5fa', '#4ade80']

// ── Styles ────────────────────────────────────────────────────────────────────

// Always-visible connection handles — indigo dot, dark border.
const handleStyle: React.CSSProperties = {
  width: 10,
  height: 10,
  background: '#6366f1',
  border: '2px solid #18181b',
  borderRadius: '50%',
}
