/** A single node in the knowledge graph. */
export interface Node {
  id: string
  label: string
  description: string | null
  x: number
  y: number
  createdAt: string
  updatedAt: string
}

/** A directed relationship between two nodes. */
export interface Edge {
  id: string
  sourceId: string
  targetId: string
  label: string | null
  createdAt: string
}

/** An authenticated user account. */
export interface User {
  id: string
  email: string
  displayName: string
  isActive: boolean
  createdAt: string
}

/** WebSocket message envelope for real-time graph events. */
export interface WsMessage<T = unknown> {
  type: 'node:created' | 'node:updated' | 'node:deleted' | 'edge:created' | 'edge:deleted'
  payload: T
}
