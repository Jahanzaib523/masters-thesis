import { useState, useRef, useEffect, useMemo } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import type { Step } from 'react-joyride'
import { api, getToken, userFriendlyMessage } from '../api'
import { PageTour } from '../tour/PageTour'
import { TOUR_STORAGE } from '../tour/storageKeys'

type RegisterType = 'text' | 'voice'

const SECRET_MAX_CHARS = 100

const TYPE_OPTIONS: { value: RegisterType; label: string; icon: string; hint: string }[] = [
  { value: 'text', label: 'Text', icon: '✏️', hint: 'Type a secret phrase' },
  { value: 'voice', label: 'Voice', icon: '🎤', hint: 'Speak your secret' },
]

export function Register() {
  const navigate = useNavigate()
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [type, setType] = useState<RegisterType>('text')
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [emailTouched, setEmailTouched] = useState(false)
  const [password, setPassword] = useState('')
  const [secretText, setSecretText] = useState('')
  const [recording, setRecording] = useState(false)
  const [audioUrl, setAudioUrl] = useState<string | null>(null)
  const mediaRecorder = useRef<MediaRecorder | null>(null)
  const chunks = useRef<Blob[]>([])
  const recordedBlob = useRef<Blob | null>(null)

  const registerSteps = useMemo<Step[]>(
    () => [
      {
        target: 'body',
        placement: 'center',
        title: 'Create your account',
        content:
          'You’ll set a password and a semantic secret (text or voice). At sign-in you’ll use both: password first, then describe your secret in your own words.',
        disableBeacon: true,
      },
      {
        target: '[data-tour="register-type"]',
        title: 'Text or voice secret',
        content: 'Choose whether to type your secret or speak it and upload audio. Pick what works best for you.',
      },
      {
        target: '[data-tour="register-account"]',
        title: 'Account details',
        content: 'Username is required. Email is optional. Password must be at least 8 characters—you’ll need it every time you sign in.',
      },
      {
        target: '[data-tour="register-secret"]',
        title: 'Semantic secret',
        content:
          `This is the idea the system will check later—not a second password. Keep it within ${SECRET_MAX_CHARS} characters. You can paraphrase freely at login.`,
      },
      {
        target: '[data-tour="register-submit"]',
        title: 'Register',
        content: 'After success, you can sign in from the login page.',
      },
    ],
    []
  )

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
      setError('Microphone access denied. Use file upload instead.')
    }
  }

  const stopRecording = () => {
    mediaRecorder.current?.stop()
    setRecording(false)
  }

  const emailInvalid = email.trim() !== '' && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())
  const passwordInvalid = password.length < 8

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (emailInvalid) return
    if (passwordInvalid) {
      setError('Password must be at least 8 characters. You need it every time you sign in.')
      return
    }
    if (type === 'text') {
      const t = secretText.trim()
      if (!t) {
        setError('Enter a secret phrase.')
        return
      }
      if (t.length > SECRET_MAX_CHARS) {
        setError(`Secret phrase must be at most ${SECRET_MAX_CHARS} characters.`)
        return
      }
    }
    setLoading(true)
    try {
      if (type === 'text') {
        await api.register({
          username,
          email: email || undefined,
          password,
          secret_text: secretText,
        })
      } else if (type === 'voice') {
        const form = new FormData()
        form.set('username', username)
        if (email) form.set('email', email)
        form.set('password', password)
        const fileInput = (e.target as HTMLFormElement).querySelector<HTMLInputElement>('input[name="voice-file"]')
        const file = fileInput?.files?.[0] ?? (recordedBlob.current ? new File([recordedBlob.current], 'recording.webm', { type: 'audio/webm' }) : null)
        if (!file) {
          setError('Please record or upload an audio file with your secret phrase.')
          setLoading(false)
          return
        }
        form.set('file', file)
        await api.registerVoice(form)
      }
      navigate('/login', { state: { registered: true } })
    } catch (err) {
      setError(userFriendlyMessage(err instanceof Error ? err.message : 'Registration failed', 'register'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      <PageTour storageKey={TOUR_STORAGE.register} steps={registerSteps} />
      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-lg transition-shadow hover:shadow-xl sm:p-8">
      <h2 className="text-xl font-semibold text-slate-800">Create account</h2>
      <p className="mt-1 text-sm text-slate-500">Choose how you want to set your secret: by text or voice.</p>

      {/* Type selector */}
      <div className="mt-6 flex gap-2 rounded-xl bg-slate-100 p-1.5" role="tablist" aria-label="Registration type" data-tour="register-type">
        {TYPE_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            type="button"
            role="tab"
            aria-selected={type === opt.value}
            onClick={() => { setType(opt.value); setError(null); }}
            className={`flex-1 rounded-lg py-3 px-4 text-sm font-medium transition-all duration-200 ${
              type === opt.value
                ? 'bg-white text-sky-600 shadow-sm'
                : 'text-slate-600 hover:bg-slate-200/60 hover:text-slate-800'
            }`}
          >
            <span className="block text-lg sm:inline sm:text-base sm:mr-1">{opt.icon}</span>
            <span className="hidden sm:inline">{opt.label}</span>
          </button>
        ))}
      </div>
      <p className="mt-2 text-center text-xs text-slate-500">{TYPE_OPTIONS.find((o) => o.value === type)?.hint}</p>

      {error && (
        <div className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700 ring-1 ring-red-100" role="alert">
          <p>{error}</p>
          <p className="mt-1 text-red-600/90">Fix the details above and try again.</p>
        </div>
      )}

      <form onSubmit={handleSubmit} className="mt-6 space-y-4">
        <div className="space-y-4" data-tour="register-account">
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label htmlFor="username" className="block text-sm font-medium text-slate-700">Username (required)</label>
            <input
              id="username"
              name="username"
              type="text"
              required
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 transition-colors focus:border-sky-500 focus:ring-2 focus:ring-sky-500/20"
              autoComplete="username"
            />
          </div>
          <div>
            <label htmlFor="email" className="block text-sm font-medium text-slate-700">Email (optional—you can add it later in Profile)</label>
            <input
              id="email"
              name="email"
              type="email"
              value={email}
              onChange={(e) => { setEmail(e.target.value); setEmailTouched(true); }}
              onBlur={() => setEmailTouched(true)}
              className={`mt-1 block w-full rounded-lg border px-3 py-2 transition-colors focus:ring-2 ${
                emailTouched && emailInvalid ? 'border-red-400 focus:border-red-500 focus:ring-red-500/20' : 'border-slate-300 focus:border-sky-500 focus:ring-sky-500/20'
              }`}
              autoComplete="email"
              aria-invalid={emailTouched && emailInvalid}
              aria-describedby={emailTouched && emailInvalid ? 'register-email-hint' : undefined}
            />
            {emailTouched && emailInvalid && (
              <p id="register-email-hint" className="mt-1 text-sm text-red-600">Enter a valid email address.</p>
            )}
          </div>
        </div>
        <div>
          <label htmlFor="password" className="block text-sm font-medium text-slate-700">Password (required, min 8 characters)</label>
          <input
            id="password"
            name="password"
            type="password"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className={`mt-1 block w-full rounded-lg border px-3 py-2 transition-colors focus:ring-2 ${
              password.length > 0 && passwordInvalid ? 'border-red-400 focus:border-red-500 focus:ring-red-500/20' : 'border-slate-300 focus:border-sky-500 focus:ring-sky-500/20'
            }`}
            autoComplete="new-password"
            aria-invalid={password.length > 0 && passwordInvalid}
          />
          {password.length > 0 && passwordInvalid && (
            <p className="mt-1 text-sm text-red-600">Use at least 8 characters.</p>
          )}
        </div>
        </div>

        {/* Secret input by type */}
        <div className="rounded-xl border border-slate-200 bg-slate-50/50 p-4 transition-all duration-200" data-tour="register-secret">
          <p className="text-xs text-slate-500 mb-3">You&apos;ll sign in later by describing this idea in your own words (or by speaking it)—no need to remember the exact phrase.</p>
          {type === 'text' && (
            <div>
              <label htmlFor="secret" className="block text-sm font-medium text-slate-700">
                Secret phrase (required, max {SECRET_MAX_CHARS} characters)
              </label>
              <textarea
                id="secret"
                required={type === 'text'}
                minLength={1}
                maxLength={SECRET_MAX_CHARS}
                rows={3}
                value={secretText}
                onChange={(e) => setSecretText(e.target.value)}
                className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 focus:border-sky-500 focus:ring-2 focus:ring-sky-500/20"
                placeholder="e.g. I know what you did last summer"
              />
              <p className="mt-1 text-xs text-slate-500" aria-live="polite">
                {secretText.length}/{SECRET_MAX_CHARS} characters
              </p>
            </div>
          )}
          {type === 'voice' && (
            <div className="space-y-3">
              <p className="text-sm font-medium text-slate-700">Speak or upload your secret phrase</p>
              <p className="text-xs text-slate-500">
                Your speech is transcribed; the text must be at most {SECRET_MAX_CHARS} characters.
              </p>
              <div className="flex flex-wrap items-center gap-3">
                {!recording ? (
                  <button type="button" onClick={startRecording} className="rounded-lg bg-red-500 px-4 py-2 text-sm font-medium text-white hover:bg-red-600 focus:ring-2 focus:ring-red-400">
                    Start recording
                  </button>
                ) : (
                  <button type="button" onClick={stopRecording} className="rounded-lg bg-slate-600 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 focus:ring-2 focus:ring-slate-400">
                    Stop recording
                  </button>
                )}
                {audioUrl && <audio src={audioUrl} controls className="max-w-full" />}
              </div>
              <div>
                <label className="block text-sm text-slate-600">Or upload audio file</label>
                <input type="file" name="voice-file" accept="audio/*" className="mt-1 block w-full text-sm text-slate-500 file:rounded-lg file:border-0 file:bg-sky-100 file:px-3 file:py-1.5 file:text-sky-700" />
              </div>
            </div>
          )}
        </div>

        <button
          type="submit"
          disabled={
            loading ||
            emailInvalid ||
            passwordInvalid ||
            (type === 'text' && (!secretText.trim() || secretText.length > SECRET_MAX_CHARS))
          }
          aria-busy={loading}
          data-tour="register-submit"
          className="w-full rounded-xl bg-sky-600 py-3 text-sm font-medium text-white shadow-sm transition hover:bg-sky-700 focus:ring-2 focus:ring-sky-500 focus:ring-offset-2 disabled:opacity-50 inline-flex items-center justify-center min-touch"
        >
          {loading && <span className="sas-spinner sas-spinner-sm" aria-hidden />}
          {loading ? 'Creating account…' : 'Register'}
        </button>
        <p className="mt-4 text-right text-sm text-slate-500">
          Already have an account? <Link to="/login" className="font-medium text-sky-600 hover:text-sky-700 hover:underline">Sign in</Link>
        </p>
      </form>
    </div>
    </>
  )
}
