import { useState, useEffect, useCallback, FormEvent } from 'react'
import apiClient from '../api/client'
import type { MindMap, ApiNode } from '../types/api'

interface Props {
  onSelectMap: (id: string, title: string) => void
  onLogout: () => void
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

export default function Dashboard({ onSelectMap, onLogout }: Props) {
  const [maps, setMaps] = useState<MindMap[]>([])
  const [nodeCounts, setNodeCounts] = useState<Record<string, number | null>>({})
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [newTitle, setNewTitle] = useState('')
  const [newDesc, setNewDesc] = useState('')
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)

  const loadMaps = useCallback(() => {
    setLoading(true)
    apiClient
      .get<MindMap[]>('/api/mindmaps/')
      .then((res) => {
        setMaps(res.data)
        setLoading(false)
        // Seed all counts as null (still loading), then resolve in parallel.
        const initial: Record<string, number | null> = {}
        res.data.forEach((m) => { initial[m.id] = null })
        setNodeCounts(initial)
        res.data.forEach((map) => {
          apiClient
            .get<ApiNode[]>(`/api/mindmaps/${map.id}/nodes`)
            .then((r) => setNodeCounts((prev) => ({ ...prev, [map.id]: r.data.length })))
            .catch(() => setNodeCounts((prev) => ({ ...prev, [map.id]: 0 })))
        })
      })
      .catch(() => setLoading(false))
  }, [])

  useEffect(() => { loadMaps() }, [loadMaps])

  // Close modal on Escape key.
  useEffect(() => {
    if (!showModal) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') closeModal() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [showModal]) // eslint-disable-line react-hooks/exhaustive-deps

  const closeModal = () => {
    setShowModal(false)
    setNewTitle('')
    setNewDesc('')
    setCreateError(null)
  }

  const handleCreate = async (e: FormEvent) => {
    e.preventDefault()
    if (!newTitle.trim()) return
    setCreating(true)
    setCreateError(null)
    try {
      const res = await apiClient.post<MindMap>('/api/mindmaps/', {
        title: newTitle.trim(),
        description: newDesc.trim() || undefined,
      })
      onSelectMap(res.data.id, res.data.title)
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setCreateError(typeof msg === 'string' ? msg : 'Failed to create map.')
      setCreating(false)
    }
  }

  const handleDelete = async (map: MindMap, e: React.MouseEvent) => {
    e.stopPropagation()
    if (!window.confirm(`Delete "${map.title}"? This cannot be undone.`)) return
    try {
      await apiClient.delete(`/api/mindmaps/${map.id}`)
      setMaps((prev) => prev.filter((m) => m.id !== map.id))
    } catch {
      console.error('Failed to delete map')
    }
  }

  return (
    <div className="min-h-screen bg-zinc-950 text-white flex flex-col">

      {/* ── Navbar ── */}
      <nav className="flex items-center justify-between px-6 py-3.5 bg-zinc-900 border-b border-white/10 shrink-0">
        <span className="text-sm font-bold tracking-tight">
          <span className="text-indigo-400 mr-1">✦</span>MindMap Live
        </span>
        <button
          onClick={onLogout}
          className="px-3 py-1.5 text-xs font-semibold bg-zinc-800 hover:bg-zinc-700 text-white/60 hover:text-white border border-white/10 rounded-md transition-colors cursor-pointer"
        >
          Logout
        </button>
      </nav>

      {/* ── Main ── */}
      <main className="flex-1 px-6 py-8 w-full max-w-6xl mx-auto">

        {/* Header row */}
        <div className="flex items-start justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold text-white">My Maps</h1>
            <p className="text-sm text-white/40 mt-0.5">
              {loading
                ? 'Loading…'
                : `${maps.length} map${maps.length !== 1 ? 's' : ''}`}
            </p>
          </div>
          <button
            onClick={() => setShowModal(true)}
            className="flex items-center gap-1.5 px-4 py-2 bg-indigo-500 hover:bg-indigo-400 text-white text-sm font-semibold rounded-lg transition-colors cursor-pointer shadow-lg shadow-indigo-900/30"
          >
            <span className="text-base leading-none">+</span> New Map
          </button>
        </div>

        {/* Loading skeleton */}
        {loading && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {[...Array(4)].map((_, i) => (
              <div
                key={i}
                className="h-40 rounded-xl bg-zinc-900 border border-white/10 animate-pulse"
              />
            ))}
          </div>
        )}

        {/* Empty state */}
        {!loading && maps.length === 0 && (
          <div className="flex flex-col items-center justify-center py-28 gap-4 text-center">
            <div className="w-16 h-16 rounded-2xl bg-zinc-900 border border-white/10 flex items-center justify-center text-3xl select-none">
              🗺️
            </div>
            <div>
              <p className="text-white font-semibold text-lg">No maps yet</p>
              <p className="text-white/40 text-sm mt-1">
                Create your first mind map to start building knowledge graphs.
              </p>
            </div>
            <button
              onClick={() => setShowModal(true)}
              className="mt-1 px-5 py-2.5 bg-indigo-500 hover:bg-indigo-400 text-white font-semibold text-sm rounded-lg transition-colors cursor-pointer"
            >
              + Create your first map
            </button>
          </div>
        )}

        {/* Map grid */}
        {!loading && maps.length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {maps.map((map) => (
              <MapCard
                key={map.id}
                map={map}
                nodeCount={nodeCounts[map.id] ?? null}
                onOpen={() => onSelectMap(map.id, map.title)}
                onDelete={(e) => handleDelete(map, e)}
              />
            ))}
          </div>
        )}
      </main>

      {/* ── New Map Modal ── */}
      {showModal && (
        <div
          className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 px-4"
          onClick={closeModal}
        >
          <div
            className="w-full max-w-md bg-zinc-900 border border-white/10 rounded-2xl p-6 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="text-lg font-bold text-white mb-5">New Map</h2>
            <form onSubmit={handleCreate} className="flex flex-col gap-4">
              {createError && (
                <p className="text-red-400 text-sm bg-red-950/40 border border-red-900/50 rounded-lg px-3 py-2">
                  {createError}
                </p>
              )}
              <label className="flex flex-col gap-1.5 text-sm font-medium text-white/60">
                Title <span className="text-red-400/70 font-normal text-xs">required</span>
                <input
                  autoFocus
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  placeholder="e.g. Product Roadmap"
                  required
                  className="bg-zinc-800 border border-white/10 rounded-lg px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500/30 transition-colors placeholder:text-white/20"
                />
              </label>
              <label className="flex flex-col gap-1.5 text-sm font-medium text-white/60">
                Description
                <span className="text-white/30 font-normal text-xs -mt-1">Optional</span>
                <textarea
                  value={newDesc}
                  onChange={(e) => setNewDesc(e.target.value)}
                  placeholder="What is this map for?"
                  rows={3}
                  className="bg-zinc-800 border border-white/10 rounded-lg px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500/30 transition-colors placeholder:text-white/20 resize-none"
                />
              </label>
              <div className="flex gap-3 pt-1">
                <button
                  type="submit"
                  disabled={creating || !newTitle.trim()}
                  className="flex-1 py-2.5 bg-indigo-500 hover:bg-indigo-400 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-semibold rounded-lg transition-colors cursor-pointer"
                >
                  {creating ? 'Creating…' : 'Create Map'}
                </button>
                <button
                  type="button"
                  onClick={closeModal}
                  className="flex-1 py-2.5 bg-zinc-800 hover:bg-zinc-700 text-white/60 hover:text-white text-sm font-semibold rounded-lg border border-white/10 transition-colors cursor-pointer"
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}

// ── MapCard ───────────────────────────────────────────────────────────────────

function MapCard({
  map,
  nodeCount,
  onOpen,
  onDelete,
}: {
  map: MindMap
  nodeCount: number | null
  onOpen: () => void
  onDelete: (e: React.MouseEvent) => void
}) {
  return (
    <div
      onClick={onOpen}
      className="group relative bg-zinc-900 border border-white/10 rounded-xl p-5 flex flex-col gap-3 cursor-pointer hover:border-white/20 hover:bg-zinc-800/60 transition-all"
    >
      {/* Delete button — appears on hover */}
      <button
        onClick={onDelete}
        title="Delete map"
        className="absolute top-3 right-3 opacity-0 group-hover:opacity-100 p-1.5 rounded-md bg-zinc-800 hover:bg-red-950 border border-white/10 hover:border-red-900/60 text-white/30 hover:text-red-400 transition-all cursor-pointer"
      >
        <TrashIcon />
      </button>

      {/* Map icon */}
      <div className="w-8 h-8 rounded-lg bg-indigo-950/60 border border-indigo-800/30 flex items-center justify-center text-indigo-400 text-sm select-none">
        ✦
      </div>

      {/* Title + description */}
      <div className="flex-1 min-h-0 pr-4">
        <p className="font-semibold text-sm text-white leading-snug line-clamp-2">
          {map.title}
        </p>
        {map.description && (
          <p className="text-xs text-white/40 mt-1 line-clamp-2 leading-relaxed">
            {map.description}
          </p>
        )}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between pt-2 border-t border-white/5">
        <span className="text-[11px] text-white/30">{formatDate(map.created_at)}</span>
        <span className="text-[11px] text-white/30">
          {nodeCount === null
            ? '…'
            : `${nodeCount} node${nodeCount !== 1 ? 's' : ''}`}
        </span>
      </div>
    </div>
  )
}

// ── Icons ─────────────────────────────────────────────────────────────────────

function TrashIcon() {
  return (
    <svg
      width="13"
      height="13"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <polyline points="3 6 5 6 21 6" />
      <path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6" />
      <path d="M10 11v6M14 11v6" />
      <path d="M9 6V4a1 1 0 011-1h4a1 1 0 011 1v2" />
    </svg>
  )
}
