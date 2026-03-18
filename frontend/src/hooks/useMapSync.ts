import { useCallback, useEffect, useRef, useState } from 'react'

// Derive the WebSocket base URL from VITE_API_URL by replacing http(s) with ws(s).
// Falls back to a relative path so same-origin deployments work without any env var.
const _apiUrl: string = import.meta.env.VITE_API_URL ?? ''
const WS_BASE = (_apiUrl
  ? _apiUrl.replace(/^https:\/\//, 'wss://').replace(/^http:\/\//, 'ws://')
  : '') + '/ws'

type JsonObject = Record<string, unknown>

/** Presence data for a single remote user. x/y are absent until their first cursor_move. */
export interface PresenceUser {
  displayName: string
  color: string
  x?: number
  y?: number
}

/** userId → PresenceUser for every peer in the room (never includes the local user). */
export type PresenceMap = Map<string, PresenceUser>

interface UseMapSyncOptions {
  /** Called with every JSON message that is NOT handled internally (e.g. node_moved). */
  onEvent: (event: JsonObject) => void
  /** Called when the connection opens. */
  onOpen?: () => void
  /** Called when the connection closes (cleanly or not). */
  onClose?: () => void
}

interface UseMapSyncResult {
  /** Send a JSON event to all other clients on this map. */
  sendEvent: (event: JsonObject) => void
  /** Send a cursor_move event, throttled to once every 50 ms. */
  sendCursorMove: (x: number, y: number) => void
  /** Live map of every connected peer keyed by userId. */
  presenceMap: PresenceMap
}

/** Decode a JWT and return the `sub` claim (user id), or '' on failure. */
function getTokenSub(token: string): string {
  try {
    return (JSON.parse(atob(token.split('.')[1])) as { sub?: string }).sub ?? ''
  } catch {
    return ''
  }
}

/**
 * Opens a WebSocket to `/ws/mindmaps/{mindmapId}?token={jwt}` and keeps it
 * alive for the lifetime of the component.
 *
 * Presence events (`room_state`, `user_joined`, `user_left`, `cursor_move`)
 * are handled internally — they update `presenceMap` and are NOT forwarded
 * to `onEvent` (except `user_joined` and `user_left`, which are also forwarded
 * so the component can show toast notifications).
 *
 * All other events (e.g. `node_moved`) are forwarded to `onEvent` unchanged.
 */
export function useMapSync(
  mindmapId: string,
  token: string,
  { onEvent, onOpen, onClose }: UseMapSyncOptions,
): UseMapSyncResult {
  const wsRef = useRef<WebSocket | null>(null)
  const [presenceMap, setPresenceMap] = useState<PresenceMap>(new Map())

  // Keep the decoded user id in a ref so the message handler always reads the
  // latest value without needing to be recreated on every token change.
  const currentUserIdRef = useRef(getTokenSub(token))
  useEffect(() => { currentUserIdRef.current = getTokenSub(token) }, [token])

  // Keep callbacks in refs so the effect closure never goes stale.
  const onEventRef = useRef(onEvent)
  const onOpenRef = useRef(onOpen)
  const onCloseRef = useRef(onClose)
  useEffect(() => { onEventRef.current = onEvent }, [onEvent])
  useEffect(() => { onOpenRef.current = onOpen }, [onOpen])
  useEffect(() => { onCloseRef.current = onClose }, [onClose])

  useEffect(() => {
    if (!mindmapId || !token) return

    // Start each connection with a clean presence slate.
    setPresenceMap(new Map())

    const url = `${WS_BASE}/mindmaps/${mindmapId}?token=${token}`
    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => onOpenRef.current?.()

    ws.onmessage = (ev: MessageEvent) => {
      let data: JsonObject
      try {
        data = JSON.parse(ev.data as string) as JsonObject
      } catch {
        return // Ignore non-JSON frames.
      }

      const type = data.type as string

      // ── room_state: full snapshot sent to new joiners ─────────────────────
      if (type === 'room_state') {
        const users = (data.users as Array<{ userId: string; displayName: string; color: string }>) ?? []
        setPresenceMap(
          new Map(
            users
              .filter((u) => u.userId !== currentUserIdRef.current)
              .map((u) => [u.userId, { displayName: u.displayName, color: u.color }]),
          ),
        )
        return // Internal only — no toast needed.
      }

      // ── user_joined: peer entered the room ────────────────────────────────
      if (type === 'user_joined') {
        const { userId, displayName, color } = data as {
          userId: string; displayName: string; color: string
        }
        if (userId !== currentUserIdRef.current) {
          setPresenceMap((prev) => {
            const next = new Map(prev)
            next.set(userId, { displayName, color })
            return next
          })
        }
        onEventRef.current(data) // Forward for toast notification.
        return
      }

      // ── user_left: peer left the room ──────────────────────────────────────
      if (type === 'user_left') {
        const { userId } = data as { userId: string }
        setPresenceMap((prev) => {
          const next = new Map(prev)
          next.delete(userId)
          return next
        })
        onEventRef.current(data) // Forward for toast notification.
        return
      }

      // ── cursor_move: update peer's position ───────────────────────────────
      if (type === 'cursor_move') {
        const { userId, displayName, x, y, color } = data as {
          userId: string; displayName: string; x: number; y: number; color: string
        }
        if (userId === currentUserIdRef.current) return // Never render own cursor.
        setPresenceMap((prev) => {
          const next = new Map(prev)
          const existing = prev.get(userId)
          // Merge with existing entry to preserve any fields not in this event.
          next.set(userId, { ...existing, displayName, color, x, y })
          return next
        })
        return // Internal only — canvas reads presenceMap directly.
      }

      // All other events (node_moved, etc.) are forwarded to the component.
      onEventRef.current(data)
    }

    ws.onclose = () => {
      onCloseRef.current?.()
      wsRef.current = null
    }

    return () => {
      ws.onopen = null
      ws.onmessage = null
      ws.onclose = null
      if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
        ws.close()
      }
      wsRef.current = null
    }
  }, [mindmapId, token])

  const sendEvent = useCallback((event: JsonObject) => {
    const ws = wsRef.current
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(event))
    }
  }, [])

  // Timestamp of the last cursor_move sent — used for 50 ms throttle.
  const lastCursorRef = useRef(0)

  const sendCursorMove = useCallback((x: number, y: number) => {
    const now = Date.now()
    if (now - lastCursorRef.current < 50) return
    lastCursorRef.current = now
    const ws = wsRef.current
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'cursor_move', x, y }))
    }
  }, [])

  return { sendEvent, sendCursorMove, presenceMap }
}
