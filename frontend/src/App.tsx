import { useState, useEffect } from 'react'
import Landing from './pages/Landing'
import Login from './pages/Login'
import Register from './pages/Register'
import MindMapCanvas from './components/MindMapCanvas'
import apiClient from './api/client'
import type { MindMap } from './types/api'

function getUserId(token: string): string {
  try {
    const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')))
    return payload.sub as string
  } catch {
    return ''
  }
}

type View = 'landing' | 'login' | 'register'

function navigate(to: View) {
  const paths: Record<View, string> = { landing: '/', login: '/login', register: '/register' }
  window.history.pushState({}, '', paths[to])
}

function initialView(): View {
  const path = window.location.pathname
  if (path === '/register') return 'register'
  if (path === '/login') return 'login'
  return 'landing'
}

export default function App() {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem('token'))
  const [view, setView] = useState<View>(initialView)
  const [mapId, setMapId] = useState<string | null>(null)
  const [mapTitle, setMapTitle] = useState('')
  const [loading, setLoading] = useState(false)

  function goTo(to: View) {
    navigate(to)
    setView(to)
  }

  useEffect(() => {
    if (!token) return
    const userId = getUserId(token)
    if (!userId) { setToken(null); return }

    setLoading(true)
    apiClient
      .get<MindMap[]>(`/api/mindmaps/?owner_id=${userId}`)
      .then((res) => {
        if (res.data.length > 0) {
          setMapId(res.data[0].id)
          setMapTitle(res.data[0].title)
        }
      })
      .catch(() => {
        localStorage.removeItem('token')
        setToken(null)
      })
      .finally(() => setLoading(false))
  }, [token])

  const handleLogin = (newToken: string) => {
    localStorage.setItem('token', newToken)
    setToken(newToken)
  }

  const handleLogout = () => {
    localStorage.removeItem('token')
    setToken(null)
    setMapId(null)
    setMapTitle('')
    goTo('landing')
  }

  const handleCreateMap = async () => {
    const userId = getUserId(token!)
    try {
      const res = await apiClient.post<MindMap>('/api/mindmaps/', {
        owner_id: userId,
        title: 'My Map',
      })
      setMapId(res.data.id)
      setMapTitle(res.data.title)
    } catch (err) {
      console.error('Failed to create map', err)
    }
  }

  if (!token) {
    if (view === 'register') {
      return (
        <Register
          onSuccess={() => goTo('login')}
          onNavigateToLogin={() => goTo('login')}
        />
      )
    }
    if (view === 'login') {
      return <Login onSuccess={handleLogin} onNavigateToRegister={() => goTo('register')} />
    }
    return (
      <Landing
        onNavigateToLogin={() => goTo('login')}
        onNavigateToRegister={() => goTo('register')}
      />
    )
  }

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh' }}>
        Loading…
      </div>
    )
  }

  if (!mapId) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100vh', gap: 16 }}>
        <p style={{ color: '#6b7280' }}>No mindmaps yet.</p>
        <button
          onClick={handleCreateMap}
          style={{ padding: '10px 24px', background: '#6366f1', color: '#fff', border: 'none', borderRadius: 6, fontSize: 15, fontWeight: 600, cursor: 'pointer' }}
        >
          Create my first map
        </button>
        <button onClick={handleLogout} style={{ color: '#9ca3af', background: 'none', border: 'none', cursor: 'pointer' }}>
          Logout
        </button>
      </div>
    )
  }

  return <MindMapCanvas mapId={mapId} title={mapTitle} onLogout={handleLogout} />
}
