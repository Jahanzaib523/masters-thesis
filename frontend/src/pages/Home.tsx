import { useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { getToken } from '../api'

export function Home() {
  const navigate = useNavigate()

  useEffect(() => {
    if (getToken()) {
      navigate('/profile', { replace: true })
    }
  }, [navigate])

  return (
    <div className="text-center py-8">
      <h2 className="text-2xl font-semibold text-slate-800">Welcome</h2>
      <p className="mt-2 text-slate-600 max-w-md mx-auto">
        Sign in by meaning: use text or voice. One account, one place to register and sign in.
      </p>
      <div className="mt-8 flex flex-col sm:flex-row justify-center gap-4">
        <Link
          to="/register"
          className="inline-flex items-center justify-center rounded-xl bg-sky-600 px-6 py-3.5 min-h-[44px] text-sm font-medium text-white shadow-sm hover:bg-sky-700 focus:ring-2 focus:ring-sky-500 focus:ring-offset-2 transition"
        >
          Create account
        </Link>
        <Link
          to="/login"
          className="inline-flex items-center justify-center rounded-xl border-2 border-slate-300 bg-white px-6 py-3.5 min-h-[44px] text-sm font-medium text-slate-700 hover:bg-slate-50 focus:ring-2 focus:ring-slate-400 focus:ring-offset-2 transition"
        >
          Sign in
        </Link>
      </div>
      <p className="mt-6 text-xs text-slate-500">
        On Register and Sign in you can switch between <strong>Text</strong> and <strong>Voice</strong> in one page.
      </p>
    </div>
  )
}
