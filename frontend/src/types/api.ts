/** API response types — mirror the backend Pydantic schemas (snake_case). */

export interface User {
  id: string
  email: string
  display_name: string
  is_active: boolean
  created_at: string
}

export interface MindMap {
  id: string
  owner_id: string
  title: string
  description: string | null
  is_public: boolean
  created_at: string
  updated_at: string
}

export interface ApiNode {
  id: string
  map_id: string
  label: string
  description: string | null
  color: string
  x: number
  y: number
  created_by: string | null
  created_at: string
  updated_at: string
}

export interface ApiEdge {
  id: string
  map_id: string
  source_id: string
  target_id: string
  label: string | null
  created_by: string | null
  created_at: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
  expires_in: number
}
