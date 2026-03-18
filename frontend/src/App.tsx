import { useState, useEffect } from 'react'
import apiClient from './api/client'
import type { MindMap } from './types/api'
import Landing from './pages/Landing'
import Login from './pages/Login'
import Register from './pages/Register'
import Dashboard from './pages/Dashboard'
import MindMapCanvas from './components/MindMapCanvas'

type View = 'landing' | 'login' | 'register'

// Matches /maps/<uuid>
const MAP_PATH_RE =
  /^\/maps\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$/i

function extractMapId(path = window.location.pathname): string | null {
  const m = path.match(MAP_PATH_RE)
  return m ? m[1] : null
}

function navigate(to: View) {
  const paths: Record<View, string> = { landing: '/', login: '/login', register: '/register' }
  window.history.pushState({}, '', paths[to])
}

function initialView(): View {
  const path = window.location.pathname
  if (path === '/register') return 'register'
  if (path === '/login') return 'login'
  // Deep link to a shared map without a session — send to login, not landing.
  if (extractMapId(path) && !localStorage.getItem('token')) return 'login'
  return 'landing'
}

export default function App() {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem('token'))
  const [view, setView] = useState<View>(initialView)

  // Initialise mapId from the URL synchronously so the first render goes
  // straight to the canvas when the user is already logged in.
  const [mapId, setMapId] = useState<string | null>(() => {
    const urlMapId = extractMapId()
    if (!urlMapId) return null
    if (localStorage.getItem('token')) {
      // Logged in — skip the dashboard and open this map directly.
      return urlMapId
    }
    // Not logged in — park the target map so we can redirect after login.
    localStorage.setItem('redirect_map_id', urlMapId)
    return null
  })

  const [mapTitle, setMapTitle] = useState('')

  // When mapId is set from a direct URL we don't know the title yet — fetch it.
  useEffect(() => {
    if (!mapId || mapTitle) return
    apiClient
      .get<MindMap>(`/api/mindmaps/${mapId}`)
      .then((res) => setMapTitle(res.data.title))
      .catch(() => {}) // Canvas still works with an empty title
  }, [mapId, mapTitle])

  function goTo(to: View) {
    navigate(to)
    setView(to)
  }

  const handleLogin = (newToken: string) => {
    localStorage.setItem('token', newToken)
    setToken(newToken)
    // If the user arrived via a share link, send them straight to that map.
    const redirectMapId = localStorage.getItem('redirect_map_id')
    if (redirectMapId) {
      localStorage.removeItem('redirect_map_id')
      window.history.pushState({}, '', `/maps/${redirectMapId}`)
      setMapId(redirectMapId)
    }
  }

  const handleLogout = () => {
    localStorage.removeItem('token')
    setToken(null)
    setMapId(null)
    setMapTitle('')
    goTo('landing')
  }

  const handleSelectMap = (id: string, title: string) => {
    window.history.pushState({}, '', `/maps/${id}`)
    setMapId(id)
    setMapTitle(title)
  }

  const handleBackToDashboard = () => {
    window.history.pushState({}, '', '/')
    setMapId(null)
    setMapTitle('')
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

  if (mapId) {
    return (
      <MindMapCanvas
        mapId={mapId}
        title={mapTitle}
        onLogout={handleLogout}
        onBackToDashboard={handleBackToDashboard}
      />
    )
  }

  return (
    <Dashboard
      onSelectMap={handleSelectMap}
      onLogout={handleLogout}
    />
  )
}
