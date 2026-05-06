import { useEffect, useState } from 'react'
import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import { clearToken, getToken, SEMANTIC_LLM_USE_OPENAI_KEY } from '../api'

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
    <div className="flex flex-col items-center gap-1" role="group" aria-label="Semantic AI provider">
      <span className="text-[10px] font-medium uppercase tracking-wide text-slate-400 text-center">Semantic AI</span>
      <div className="flex items-center gap-2 rounded-full border border-slate-600 bg-slate-800 py-1 pl-2.5 pr-1 ring-1 ring-white/5">
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
        <div className="relative w-full px-4 py-4">
          <div className="max-w-4xl mx-auto">
            <h1 className="text-xl font-semibold tracking-tight">Semantic Auth System</h1>
            <p className="text-slate-400 text-sm mt-0.5">AI-driven · Text & voice</p>
          </div>
          <nav className="mt-3 flex items-end justify-end gap-1 sm:mt-0 sm:absolute sm:right-4 sm:top-1/2 sm:-translate-y-1/2 sm:gap-2" aria-label="Main navigation">
            {token ? (
              <>
                <button
                  type="button"
                  onClick={handleSignOut}
                  className="inline-flex h-[34px] items-center rounded-full border border-slate-600 bg-slate-800 px-3 text-sm font-medium text-slate-100 ring-1 ring-white/5 hover:bg-slate-700 hover:text-white"
                >
                  Sign out
                </button>
              </>
            ) : null}
            <div className="ml-5 flex items-end pl-5 border-l border-slate-700">
              <SemanticLlmToggle />
            </div>
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
