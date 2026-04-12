import { useEffect, useState } from 'react'
import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import { clearToken, getToken, SEMANTIC_LLM_USE_OPENAI_KEY } from '../api'

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  `rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
    isActive ? 'bg-slate-700 text-white' : 'text-slate-300 hover:bg-slate-800 hover:text-white'
  }`

function SemanticLlmToggle() {
  const [useOpenAI, setUseOpenAI] = useState(() => {
    try {
      return typeof localStorage !== 'undefined' && localStorage.getItem(SEMANTIC_LLM_USE_OPENAI_KEY) === '1'
    } catch {
      return false
    }
  })

  useEffect(() => {
    try {
      if (useOpenAI) localStorage.setItem(SEMANTIC_LLM_USE_OPENAI_KEY, '1')
      else localStorage.removeItem(SEMANTIC_LLM_USE_OPENAI_KEY)
    } catch {
      /* ignore */
    }
  }, [useOpenAI])

  const toggle = () => setUseOpenAI((v) => !v)

  return (
    <div
      className="fixed right-3 z-[10001] flex flex-col items-end gap-1 sm:right-4"
      style={{ top: 'max(0.75rem, env(safe-area-inset-top, 0px))' }}
      role="group"
      aria-label="Semantic AI provider"
    >
      <span className="text-[10px] font-medium uppercase tracking-wide text-slate-400">Semantic AI</span>
      <div className="flex items-center gap-2 rounded-full border border-slate-600/90 bg-slate-900/95 py-1 pl-2.5 pr-1 shadow-lg ring-1 ring-white/5 backdrop-blur-sm">
        <div className="flex items-baseline gap-1 pr-0.5 text-[11px] leading-none">
          <span className={useOpenAI ? 'text-slate-500' : 'font-semibold text-white'}>Groq</span>
          <span className="text-slate-600" aria-hidden>
            |
          </span>
          <span className={useOpenAI ? 'font-semibold text-sky-300' : 'text-slate-500'}>OpenAI</span>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={useOpenAI}
          aria-label={useOpenAI ? 'Using OpenAI for semantic scoring; switch to Groq' : 'Using Groq for semantic scoring; switch to OpenAI'}
          onClick={toggle}
          className={`relative inline-flex h-7 w-12 shrink-0 cursor-pointer rounded-full border border-transparent transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-400 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-900 ${
            useOpenAI ? 'bg-sky-600' : 'bg-slate-600'
          }`}
        >
          <span
            className={`pointer-events-none absolute top-0.5 left-0.5 h-6 w-6 rounded-full bg-white shadow-md ring-1 ring-black/5 transition-transform duration-200 ease-out ${
              useOpenAI ? 'translate-x-5' : 'translate-x-0'
            }`}
            aria-hidden
          />
        </button>
      </div>
      <p className="max-w-[11rem] text-right text-[10px] leading-tight text-slate-500">
        Summary and login match only. Voice STT/TTS stay on Groq.
      </p>
    </div>
  )
}

export function Layout() {
  const navigate = useNavigate()
  const token = getToken()

  const handleSignOut = () => {
    clearToken()
    navigate('/', { replace: true })
  }

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
              <>
                <NavLink to="/profile" className={`${navLinkClass} min-touch inline-flex items-center`}>Profile</NavLink>
                <button
                  type="button"
                  onClick={handleSignOut}
                  className="rounded-lg border border-slate-500 px-3 py-1.5 text-sm font-medium text-slate-100 hover:bg-slate-800 min-touch"
                >
                  Sign out
                </button>
              </>
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

      <SemanticLlmToggle />
    </div>
  )
}
