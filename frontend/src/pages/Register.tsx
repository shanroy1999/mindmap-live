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
    const body = { email, display_name: displayName, password }
    console.log('[Register] request body:', body)
    try {
      const res = await apiClient.post<User>('/api/users/', body)
      console.log('[Register] response:', res.status, res.data)
      onSuccess()
    } catch (err: unknown) {
      console.error('[Register] error:', err)
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(typeof msg === 'string' ? msg : 'Registration failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-zinc-950 flex items-center justify-center px-4">
      <form onSubmit={handleSubmit} className="w-full max-w-sm bg-zinc-900 border border-white/10 rounded-xl p-8 flex flex-col gap-5 shadow-2xl">
        <div className="text-center mb-1">
          <span className="text-indigo-400 text-xl">✦</span>
          <h1 className="text-2xl font-bold text-white mt-1">Create account</h1>
          <p className="text-sm text-white/40 mt-0.5">Join MindMap Live</p>
        </div>
        {error && (
          <p className="text-red-400 text-sm text-center bg-red-950/40 border border-red-900/50 rounded-lg py-2 px-3">
            {error}
          </p>
        )}
        <label className="flex flex-col gap-1.5 text-sm font-medium text-white/60">
          Display name
          <input
            type="text"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            required
            autoFocus
            className="bg-zinc-800 border border-white/10 rounded-lg px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500/30 transition-colors"
          />
        </label>
        <label className="flex flex-col gap-1.5 text-sm font-medium text-white/60">
          Email
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            className="bg-zinc-800 border border-white/10 rounded-lg px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500/30 transition-colors"
          />
        </label>
        <label className="flex flex-col gap-1.5 text-sm font-medium text-white/60">
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={8}
            className="bg-zinc-800 border border-white/10 rounded-lg px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500/30 transition-colors"
          />
        </label>
        <button
          type="submit"
          disabled={loading}
          className="bg-indigo-500 hover:bg-indigo-400 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold rounded-lg py-2.5 text-sm transition-colors mt-1 cursor-pointer"
        >
          {loading ? 'Creating account…' : 'Create account'}
        </button>
        <p className="text-sm text-center text-white/40">
          Already have an account?{' '}
          <button
            type="button"
            onClick={onNavigateToLogin}
            className="text-indigo-400 font-semibold hover:text-indigo-300 transition-colors cursor-pointer"
          >
            Sign in
          </button>
        </p>
      </form>
    </div>
  )
}
