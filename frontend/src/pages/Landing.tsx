interface Props {
  onNavigateToLogin: () => void
  onNavigateToRegister: () => void
}

export default function Landing({ onNavigateToLogin, onNavigateToRegister }: Props) {
  return (
    <div className="min-h-screen bg-black text-white flex flex-col">

      {/* ── Navbar ── */}
      <nav className="flex items-center justify-between px-6 py-4 border-b border-white/10">
        <span className="text-lg font-bold tracking-tight">
          <span className="text-indigo-400">✦</span> MindMap Live
        </span>
        <div className="flex items-center gap-3">
          <button
            onClick={onNavigateToLogin}
            className="px-4 py-1.5 text-sm font-medium text-white/70 hover:text-white transition-colors"
          >
            Sign In
          </button>
          <button
            onClick={onNavigateToRegister}
            className="px-4 py-1.5 text-sm font-semibold bg-white text-black rounded-md hover:bg-white/90 transition-colors"
          >
            Get Started
          </button>
        </div>
      </nav>

      {/* ── Hero ── */}
      <section className="flex flex-col items-center justify-center text-center flex-1 px-6 py-24 gap-6">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-white/15 bg-white/5 text-xs text-white/60 mb-2">
          <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 inline-block" />
          Now with Claude AI
        </div>
        <h1 className="text-5xl sm:text-6xl font-extrabold tracking-tight leading-tight max-w-3xl">
          Think Together,{' '}
          <span className="text-indigo-400">In Real Time</span>
        </h1>
        <p className="text-lg text-white/50 max-w-xl leading-relaxed">
          A collaborative knowledge graph builder where your team maps ideas,
          discovers connections, and lets AI surface what you might have missed —
          all synced live via WebSockets.
        </p>
        <button
          onClick={onNavigateToRegister}
          className="mt-2 px-7 py-3 bg-indigo-500 hover:bg-indigo-400 text-white font-semibold rounded-lg text-base transition-colors shadow-lg shadow-indigo-900/40"
        >
          Start for Free →
        </button>
      </section>

      {/* ── Features ── */}
      <section className="px-6 pb-24 max-w-5xl mx-auto w-full">
        <p className="text-center text-xs font-semibold uppercase tracking-widest text-white/30 mb-10">
          Everything you need
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <FeatureCard
            icon="⚡"
            title="Real-Time Collaboration"
            description="Every node move, label edit, and new edge is broadcast instantly to all connected collaborators over WebSockets. No refresh needed."
          />
          <FeatureCard
            icon="✨"
            title="AI-Powered Connections"
            description="Claude analyzes your graph and suggests relationships between nodes you might have missed, helping you build denser, richer knowledge maps."
          />
          <FeatureCard
            icon="🔮"
            title="Semantic Clustering"
            description="Automatically group related ideas into clusters by meaning. Visualize the structure of your thinking with one click."
          />
        </div>
      </section>

      {/* ── Footer ── */}
      <footer className="border-t border-white/10 px-6 py-5 flex items-center justify-between text-xs text-white/30">
        <span className="font-semibold text-white/50">
          <span className="text-indigo-400">✦</span> MindMap Live
        </span>
        <span>© {new Date().getFullYear()} MindMap Live. All rights reserved.</span>
      </footer>

    </div>
  )
}

function FeatureCard({
  icon,
  title,
  description,
}: {
  icon: string
  title: string
  description: string
}) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.03] p-6 flex flex-col gap-3 hover:border-white/20 hover:bg-white/[0.06] transition-all">
      <span className="text-2xl">{icon}</span>
      <h3 className="text-sm font-semibold text-white">{title}</h3>
      <p className="text-sm text-white/50 leading-relaxed">{description}</p>
    </div>
  )
}
