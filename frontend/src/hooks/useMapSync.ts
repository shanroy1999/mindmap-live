import { useCallback, useEffect, useRef } from 'react'

const WS_BASE = import.meta.env.VITE_WS_URL ?? 'ws://localhost:8000/ws'

type JsonObject = Record<string, unknown>

interface UseMapSyncOptions {
  /** Called with every JSON message received from the server. */
  onEvent: (event: JsonObject) => void
  /** Called when the connection opens. */
  onOpen?: () => void
  /** Called when the connection closes (cleanly or not). */
  onClose?: () => void
}

interface UseMapSyncResult {
  /** Send a JSON event to all other clients on this map. */
  sendEvent: (event: JsonObject) => void
}

/**
 * Opens a WebSocket to `/ws/mindmaps/{mindmapId}?token={jwt}` and keeps it
 * alive for the lifetime of the component.
 *
 * The socket is torn down and recreated whenever `mindmapId` or `token`
 * changes (e.g. after a token refresh or map switch).
 *
 * `sendEvent` is stable across renders and silently drops messages if the
 * socket is not yet open — callers do not need to guard against that case.
 */
export function useMapSync(
  mindmapId: string,
  token: string,
  { onEvent, onOpen, onClose }: UseMapSyncOptions,
): UseMapSyncResult {
  const wsRef = useRef<WebSocket | null>(null)

  // Keep callbacks in refs so the effect closure never goes stale.
  const onEventRef = useRef(onEvent)
  const onOpenRef = useRef(onOpen)
  const onCloseRef = useRef(onClose)
  useEffect(() => { onEventRef.current = onEvent }, [onEvent])
  useEffect(() => { onOpenRef.current = onOpen }, [onOpen])
  useEffect(() => { onCloseRef.current = onClose }, [onClose])

  useEffect(() => {
    if (!mindmapId || !token) return

    const url = `${WS_BASE}/mindmaps/${mindmapId}?token=${token}`
    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => onOpenRef.current?.()

    ws.onmessage = (ev: MessageEvent) => {
      try {
        const data = JSON.parse(ev.data as string) as JsonObject
        onEventRef.current(data)
      } catch {
        // Non-JSON frames are ignored.
      }
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

  return { sendEvent }
}
