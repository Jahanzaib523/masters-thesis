import { useState, useRef, useEffect } from 'react'
import { useNavigate, useLocation, Link } from 'react-router-dom'
import { api, getToken, setToken, userFriendlyMessage } from '../api'
import type { LoginResult } from '../api'

type ResponseType = 'text' | 'voice'

const RESPONSE_OPTIONS: { value: ResponseType; label: string; icon: string }[] = [
  { value: 'text', label: 'Type response', icon: '✏️' },
  { value: 'voice', label: 'Speak response', icon: '🎤' },
]

export function Login() {
  const navigate = useNavigate()
  const location = useLocation()
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [step, setStep] = useState<'id' | 'response'>('id')
  const [identifier, setIdentifier] = useState('')
  const [challengeId, setChallengeId] = useState<number | null>(null)
  const [prompt, setPrompt] = useState('')
  const [secretType, setSecretType] = useState<string>('text')
  const [responseType, setResponseType] = useState<ResponseType>('text')
  const [responseText, setResponseText] = useState('')
  const [recording, setRecording] = useState(false)
  const [audioUrl, setAudioUrl] = useState<string | null>(null)
  const [locked, setLocked] = useState(false)
  const mediaRecorder = useRef<MediaRecorder | null>(null)
  const chunks = useRef<Blob[]>([])
  const recordedBlob = useRef<Blob | null>(null)

  const registered = (location.state as { registered?: boolean })?.registered

  useEffect(() => {
    if (getToken()) {
      navigate('/profile', { replace: true })
    }
  }, [navigate])

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mr = new MediaRecorder(stream)
      mediaRecorder.current = mr
      chunks.current = []
      mr.ondataavailable = (e) => e.data.size && chunks.current.push(e.data)
      mr.onstop = () => {
        const blob = new Blob(chunks.current, { type: 'audio/webm' })
        recordedBlob.current = blob
        setAudioUrl(URL.createObjectURL(blob))
        stream.getTracks().forEach((t) => t.stop())
      }
      mr.start()
      setRecording(true)
    } catch {
      setError('Microphone access denied. Use file upload.')
    }
  }

  const stopRecording = () => {
    mediaRecorder.current?.stop()
    setRecording(false)
  }

  const playPrompt = () => {
    if (challengeId == null) return
    const audio = new Audio(api.getPromptAudio(challengeId))
    audio.play()
  }

  const handleInit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const res = await api.loginInit(identifier)
      setChallengeId(res.challenge_id)
      setPrompt(res.prompt)
      setSecretType(res.secret_type ?? 'text')
      setResponseType((res.secret_type as ResponseType) === 'voice' ? 'voice' : 'text')
      setStep('response')
    } catch (err) {
      setError(userFriendlyMessage(err instanceof Error ? err.message : 'Could not start sign-in', 'auth'))
    } finally {
      setLoading(false)
    }
  }

  const handleResponseTypeChange = (next: ResponseType) => {
    setResponseType(next)
    setError(null)
  }

  const handleComplete = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      let result: LoginResult
      if (responseType === 'text' && challengeId != null) {
        result = await api.loginComplete(challengeId, responseText)
      } else if (responseType === 'voice' && challengeId != null) {
        const form = new FormData()
        const fileInput = (e.target as HTMLFormElement).querySelector<HTMLInputElement>('input[name="voice-file"]')
        const file = fileInput?.files?.[0] ?? (recordedBlob.current ? new File([recordedBlob.current], 'recording.webm', { type: 'audio/webm' }) : null)
        if (!file) {
          setError('Please record or upload your voice response.')
          setLoading(false)
          return
        }
        form.set('file', file)
        result = await api.loginVoiceComplete(challengeId, form)
      } else {
        setError('Please choose how to respond.')
        setLoading(false)
        return
      }

      if (result.success && result.token) {
        setToken(result.token)
        navigate('/profile', { replace: true })
        return
      }

      // Continuous feedback: show error on this step, do not go back to start
      const isLocked = result.message.toLowerCase().includes('too many')
      setError(result.message)
      if (responseType === 'voice') {
        recordedBlob.current = null
        setAudioUrl(null)
      }
      if (isLocked) {
        setLocked(true)
      }
    } catch (err) {
      setError(userFriendlyMessage(err instanceof Error ? err.message : 'Sign-in failed', 'auth'))
    } finally {
      setLoading(false)
    }
  }

  if (step === 'response') {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-lg transition-shadow hover:shadow-xl sm:p-8">
        <div className="mb-4 flex items-center gap-2 text-sm text-slate-500">
          <span className="rounded-full bg-sky-100 px-2 py-0.5 font-medium text-sky-700">Step 2 of 2</span>
        </div>
        {registered && (
          <p className="mb-4 rounded-lg bg-green-50 p-3 text-sm text-green-800 ring-1 ring-green-100">Registration successful. Complete sign in below.</p>
        )}
        <h2 className="text-xl font-semibold text-slate-800">Verify your secret</h2>
        <p className="mt-2 text-slate-600">{prompt}</p>

        {(secretType === 'voice' || responseType === 'voice') && (
          <div className="mt-4">
            <button
              type="button"
              onClick={playPrompt}
              className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 focus:ring-2 focus:ring-emerald-500"
            >
              🔊 Listen to prompt (TTS)
            </button>
          </div>
        )}

        <div className="mt-6 flex gap-2 rounded-xl bg-slate-100 p-1.5" role="tablist" aria-label="Response type">
          {RESPONSE_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              role="tab"
              aria-selected={responseType === opt.value}
              onClick={() => handleResponseTypeChange(opt.value)}
              className={`flex-1 rounded-lg py-3 px-4 text-sm font-medium transition-all duration-200 ${
                responseType === opt.value ? 'bg-white text-sky-600 shadow-sm' : 'text-slate-600 hover:bg-slate-200/60 hover:text-slate-800'
              }`}
            >
              <span className="block text-lg sm:inline sm:text-base sm:mr-1">{opt.icon}</span>
              <span className="hidden sm:inline">{opt.label}</span>
            </button>
          ))}
        </div>

        {error && (
          <div className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700 ring-1 ring-red-100" role="alert">
            <p>{error}</p>
            <p className="mt-1 text-red-600/90">Check the details above and try again.</p>
          </div>
        )}

        {locked && (
          <div className="mt-4 flex justify-end">
            <button
              type="button"
              onClick={() => {
                setStep('id')
                setChallengeId(null)
                setPrompt('')
                setLocked(false)
                setError(null)
                setResponseText('')
                recordedBlob.current = null
                setAudioUrl(null)
              }}
              className="rounded-lg bg-amber-600 px-4 py-2 text-sm font-medium text-white hover:bg-amber-700 focus:ring-2 focus:ring-amber-500"
            >
              Start over (enter username again)
            </button>
          </div>
        )}

        <form onSubmit={handleComplete} className="mt-6 space-y-4">
          {responseType === 'text' && (
            <div>
              <label htmlFor="response" className="block text-sm font-medium text-slate-700">Your response (required, same meaning in your words)</label>
              <textarea
                id="response"
                required
                minLength={3}
                rows={4}
                value={responseText}
                onChange={(e) => setResponseText(e.target.value)}
                className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 focus:border-sky-500 focus:ring-2 focus:ring-sky-500/20"
                placeholder="Describe the idea in your own words"
              />
            </div>
          )}
          {responseType === 'voice' && (
            <div className="rounded-xl border border-slate-200 bg-slate-50/50 p-4 space-y-3">
              <p className="text-sm font-medium text-slate-700">Speak or upload your response</p>
              <div className="flex flex-wrap items-center gap-3">
                {!recording ? (
                  <button type="button" onClick={startRecording} className="rounded-lg bg-red-500 px-4 py-2 text-sm font-medium text-white hover:bg-red-600">
                    Start recording
                  </button>
                ) : (
                  <button type="button" onClick={stopRecording} className="rounded-lg bg-slate-600 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700">
                    Stop recording
                  </button>
                )}
                {audioUrl && <audio src={audioUrl} controls className="max-w-full" />}
              </div>
              <div>
                <label className="block text-sm text-slate-600">Or upload audio</label>
                <input type="file" name="voice-file" accept="audio/*" className="mt-1 block w-full text-sm text-slate-500 file:rounded-lg file:border-0 file:bg-sky-100 file:px-3 file:py-1.5 file:text-sky-700" />
              </div>
            </div>
          )}

          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={() => {
                setStep('id')
                setLocked(false)
                setError(null)
              }}
              className="rounded-lg border border-slate-300 px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50 focus:ring-2 focus:ring-slate-400"
            >
              Back
            </button>
            <button
              type="submit"
              disabled={loading || locked}
              aria-busy={loading}
              className="flex-1 rounded-xl bg-sky-600 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-sky-700 focus:ring-2 focus:ring-sky-500 focus:ring-offset-2 disabled:opacity-50 inline-flex items-center justify-center min-touch"
            >
              {loading && <span className="sas-spinner sas-spinner-sm" aria-hidden />}
              {loading ? 'Checking…' : locked ? 'Start over above' : 'Sign in'}
            </button>
          </div>
          <p className="mt-4 text-right text-sm text-slate-500">
            No account? <Link to="/register" className="font-medium text-sky-600 hover:text-sky-700 hover:underline">Register</Link>
          </p>
        </form>
      </div>
    )
  }

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-lg transition-shadow hover:shadow-xl sm:p-8">
      <div className="mb-4 flex items-center gap-2 text-sm text-slate-500">
        <span className="rounded-full bg-sky-100 px-2 py-0.5 font-medium text-sky-700">Step 1 of 2</span>
      </div>
      {registered && (
        <p className="mb-4 rounded-lg bg-green-50 p-3 text-sm text-green-800 ring-1 ring-green-100">Registration successful. Sign in below.</p>
      )}
      <h2 className="text-xl font-semibold text-slate-800">Sign in</h2>
      <p className="mt-1 text-sm text-slate-500">Enter your username or email to continue.</p>

      {error && (
        <div className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700 ring-1 ring-red-100" role="alert">
          <p>{error}</p>
          <p className="mt-1 text-red-600/90">Check your username or email, or register first.</p>
        </div>
      )}

      <form onSubmit={handleInit} className="mt-6 space-y-4">
        <div>
          <label htmlFor="identifier" className="block text-sm font-medium text-slate-700">Username or email (required)</label>
          <input
            id="identifier"
            type="text"
            required
            value={identifier}
            onChange={(e) => setIdentifier(e.target.value)}
            className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 transition-colors focus:border-sky-500 focus:ring-2 focus:ring-sky-500/20"
            autoComplete="username"
            placeholder="e.g. alice or alice@example.com"
          />
        </div>
        <button
          type="submit"
          disabled={loading}
          aria-busy={loading}
          className="w-full rounded-xl bg-sky-600 py-3 text-sm font-medium text-white shadow-sm transition hover:bg-sky-700 focus:ring-2 focus:ring-sky-500 focus:ring-offset-2 disabled:opacity-50 inline-flex items-center justify-center min-touch"
        >
          {loading && <span className="sas-spinner sas-spinner-sm" aria-hidden />}
          {loading ? 'Loading…' : 'Continue'}
        </button>
        <p className="mt-4 text-right text-sm text-slate-500">
          No account? <Link to="/register" className="font-medium text-sky-600 hover:text-sky-700 hover:underline">Register</Link>
        </p>
      </form>
    </div>
  )
}
