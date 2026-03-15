import { useState } from 'react'
import Landing from './pages/Landing'
import Login from './pages/Login'
import Register from './pages/Register'
import Dashboard from './pages/Dashboard'
import MindMapCanvas from './components/MindMapCanvas'

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

  function goTo(to: View) {
    navigate(to)
    setView(to)
  }

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

  const handleSelectMap = (id: string, title: string) => {
    setMapId(id)
    setMapTitle(title)
  }

  const handleBackToDashboard = () => {
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
