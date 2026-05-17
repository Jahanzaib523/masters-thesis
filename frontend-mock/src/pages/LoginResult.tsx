import { useEffect, useState } from 'react'
import { useLocation, Link, useNavigate } from 'react-router-dom'
import { getToken } from '../api'

export function LoginResult() {
  const location = useLocation()
  const navigate = useNavigate()
  const [showDetails, setShowDetails] = useState(false)
  const result = (location.state as { result?: { success: boolean; message: string; token?: string; similarity_score?: number } })?.result

  useEffect(() => {
    if (getToken()) {
      navigate('/profile', { replace: true })
    }
  }, [navigate])

  if (!result) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <p className="text-slate-600">No result to show. <Link to="/login" className="text-sky-600 hover:underline">Go to sign in</Link>.</p>
      </div>
    )
  }

  const success = result.success
  const hasDetails = result.similarity_score != null

  return (
    <div className={`rounded-xl border p-6 shadow-sm ${success ? 'border-green-200 bg-green-50' : 'border-red-200 bg-red-50'}`}>
      <h2 className={`text-lg font-semibold ${success ? 'text-green-800' : 'text-red-800'}`}>
        {success ? 'Signed in successfully' : 'Sign-in failed'}
      </h2>
      <p className={`mt-2 text-sm ${success ? 'text-green-700' : 'text-red-700'}`}>{result.message}</p>
      {hasDetails && (
        <div className="mt-3">
          <button type="button" onClick={() => setShowDetails(!showDetails)} className="text-xs text-slate-500 hover:text-slate-700 underline">
            {showDetails ? 'Hide details' : 'Show details'}
          </button>
          {showDetails && <p className="mt-1 text-xs text-slate-500">Similarity score: {result.similarity_score}</p>}
        </div>
      )}
      <div className="mt-6 flex gap-3">
        {!success && <Link to="/login" className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50">Try again</Link>}
        <Link to="/" className="rounded-lg bg-slate-800 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700">Home</Link>
      </div>
    </div>
  )
}
