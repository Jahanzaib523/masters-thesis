import { Outlet, NavLink } from 'react-router-dom'
import { getToken } from '../api'

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  `rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
    isActive ? 'bg-slate-700 text-white' : 'text-slate-300 hover:bg-slate-800 hover:text-white'
  }`

export function Layout() {
  const token = getToken()
  return (
    <div className="min-h-screen flex flex-col">
      <header className="bg-slate-900 text-white shadow-sm pt-[env(safe-area-inset-top)]">
        <div className="max-w-4xl mx-auto px-4 py-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">Semantic Auth System</h1>
            <p className="text-slate-400 text-sm mt-0.5">AI-driven · Text & voice</p>
          </div>
          <nav className="flex flex-wrap items-center gap-1 sm:gap-2" aria-label="Main navigation">
            <NavLink to="/" end className={`${navLinkClass} min-touch inline-flex items-center`}>Home</NavLink>
            {token ? (
              <NavLink to="/profile" className={`${navLinkClass} min-touch inline-flex items-center`}>Profile</NavLink>
            ) : (
              <>
                <NavLink to="/login" className={`${navLinkClass} min-touch inline-flex items-center`}>Sign in</NavLink>
                <NavLink to="/register" className={`${navLinkClass} min-touch inline-flex items-center`}>Register</NavLink>
              </>
            )}
          </nav>
        </div>
      </header>

      <main className="flex-1 max-w-xl w-full min-w-0 mx-auto px-4 py-6 sm:py-8">
        <Outlet />
      </main>

      <footer className="border-t border-slate-200 bg-slate-50 py-4 pb-[max(1rem,env(safe-area-inset-bottom))] text-center text-sm text-slate-500">
        <span className="inline-block">Voice (TTS) for blind users · Text for everyone</span>
        {' · '}
        <NavLink to="/help" className="text-sky-600 hover:underline">Help</NavLink>
      </footer>
    </div>
  )
}
