import { useState, FormEvent } from 'react'
import apiClient from '../api/client'
import type { User } from '../types/api'

interface Props {
  onSuccess: () => void
  onNavigateToLogin: () => void
}

export default function Register({ onSuccess, onNavigateToLogin }: Props) {
  const [email, setEmail] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      await apiClient.post<User>('/api/users/', {
        email,
        display_name: displayName,
        password,
      })
      onSuccess()
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(typeof msg === 'string' ? msg : 'Registration failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={styles.wrapper}>
      <form onSubmit={handleSubmit} style={styles.card}>
        <h1 style={styles.title}>Create account</h1>
        {error && <p style={styles.error}>{error}</p>}
        <label style={styles.label}>
          Display name
          <input
            type="text"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            required
            autoFocus
            style={styles.input}
          />
        </label>
        <label style={styles.label}>
          Email
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            style={styles.input}
          />
        </label>
        <label style={styles.label}>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={8}
            style={styles.input}
          />
        </label>
        <button type="submit" disabled={loading} style={styles.button}>
          {loading ? 'Creating account…' : 'Create account'}
        </button>
        <p style={styles.footer}>
          Already have an account?{' '}
          <button type="button" onClick={onNavigateToLogin} style={styles.link}>
            Sign in
          </button>
        </p>
      </form>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  wrapper: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    height: '100vh',
    background: '#f4f4f8',
  },
  card: {
    display: 'flex',
    flexDirection: 'column',
    gap: 16,
    padding: 32,
    borderRadius: 12,
    background: '#fff',
    boxShadow: '0 4px 24px rgba(0,0,0,0.1)',
    width: 360,
  },
  title: {
    margin: 0,
    fontSize: 24,
    fontWeight: 700,
    textAlign: 'center',
    color: '#6366f1',
  },
  error: {
    margin: 0,
    color: '#ef4444',
    fontSize: 14,
    textAlign: 'center',
  },
  label: {
    display: 'flex',
    flexDirection: 'column',
    gap: 4,
    fontSize: 14,
    fontWeight: 500,
    color: '#374151',
  },
  input: {
    padding: '8px 12px',
    border: '1px solid #d1d5db',
    borderRadius: 6,
    fontSize: 14,
    outline: 'none',
  },
  button: {
    padding: '10px 0',
    background: '#6366f1',
    color: '#fff',
    border: 'none',
    borderRadius: 6,
    fontSize: 15,
    fontWeight: 600,
    cursor: 'pointer',
  },
  footer: {
    margin: 0,
    textAlign: 'center',
    fontSize: 14,
    color: '#6b7280',
  },
  link: {
    background: 'none',
    border: 'none',
    color: '#6366f1',
    fontWeight: 600,
    fontSize: 14,
    cursor: 'pointer',
    padding: 0,
  },
}
