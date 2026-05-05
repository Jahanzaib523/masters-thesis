import { useState, useEffect, useRef, useMemo } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import type { Step } from 'react-joyride'
import { api, ApiError, clearToken, getToken, userFriendlyMessage } from '../api'
import type { ProfileResponse } from '../api'
import { PageTour } from '../tour/PageTour'
import { TOUR_STORAGE } from '../tour/storageKeys'

type SecretTab = 'text' | 'voice'

const SECRET_MAX_CHARS = 100

export function Profile() {
  const navigate = useNavigate()
  const [profile, setProfile] = useState<ProfileResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [emailTouched, setEmailTouched] = useState(false)
  const [newPassword, setNewPassword] = useState('')
  const [accountSaving, setAccountSaving] = useState(false)
  const [accountSuccess, setAccountSuccess] = useState(false)

  const [secretText, setSecretText] = useState('')
  const [secretSaving, setSecretSaving] = useState(false)
  const [secretSuccess, setSecretSuccess] = useState(false)
  const [confirmSecretReplace, setConfirmSecretReplace] = useState<'text' | 'voice' | null>(null)
  const [secretTab, setSecretTab] = useState<SecretTab>('text')
  const [greetingImageText, setGreetingImageText] = useState('')
  const [greetingSaving, setGreetingSaving] = useState(false)
  const [greetingSuccess, setGreetingSuccess] = useState(false)
  const [currentGreetingUrl, setCurrentGreetingUrl] = useState<string | null>(null)
  const [loginMode, setLoginMode] = useState<'both' | 'image_only'>('both')
  const [modeSaving, setModeSaving] = useState(false)
  const [recording, setRecording] = useState(false)
  const [audioUrl, setAudioUrl] = useState<string | null>(null)
  const mediaRecorder = useRef<MediaRecorder | null>(null)
  const pendingVoiceFile = useRef<File | null>(null)
  const chunks = useRef<Blob[]>([])
  const recordedBlob = useRef<Blob | null>(null)

  useEffect(() => {
    const t = getToken()
    if (!t) {
      navigate('/login', { replace: true })
      return
    }
    api.getProfile()
      .then((p) => {
        setProfile(p)
        setUsername(p.username)
        setEmail(p.email ?? '')
        setLoginMode(p.login_mode ?? 'both')
        setSecretTab((p.secret_type as SecretTab) === 'voice' ? 'voice' : 'text')
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) {
          clearToken()
          navigate('/login', { replace: true })
          return
        }
        setError(userFriendlyMessage(err instanceof Error ? err.message : 'Failed to load profile', 'profile'))
      })
      .finally(() => setLoading(false))
  }, [navigate])

  useEffect(() => {
    const token = getToken()
    if (!token || !profile) return
    fetch(api.getProfileGreetingImageUrl(), {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(async (res) => {
        if (!res.ok) throw new Error(await res.text())
        return res.blob()
      })
      .then((blob) => {
        setCurrentGreetingUrl((prev) => {
          if (prev) URL.revokeObjectURL(prev)
          return URL.createObjectURL(blob)
        })
      })
      .catch(() => {
        setCurrentGreetingUrl(null)
      })
  }, [profile])

  useEffect(() => {
    return () => {
      if (currentGreetingUrl) URL.revokeObjectURL(currentGreetingUrl)
    }
  }, [currentGreetingUrl])

  const emailInvalid = profile ? (email.trim() !== '' && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) : false

  const handleUpdateAccount = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (emailInvalid) return
    setAccountSuccess(false)
    setAccountSaving(true)
    try {
      const p = await api.updateProfile({
        username: username.trim(),
        email: email.trim() === '' ? null : email.trim(),
        new_password: newPassword || undefined,
      })
      setProfile(p)
      setAccountSuccess(true)
      if (newPassword) setNewPassword('')
    } catch (err) {
      setError(userFriendlyMessage(err instanceof Error ? err.message : 'Update failed', 'profile'))
    } finally {
      setAccountSaving(false)
    }
  }

  const handleUpdateSecretText = (e: React.FormEvent) => {
    e.preventDefault()
    const t = secretText.trim()
    if (!t) {
      setError('Enter a secret phrase.')
      return
    }
    if (t.length > SECRET_MAX_CHARS) {
      setError(`Secret phrase must be at most ${SECRET_MAX_CHARS} characters.`)
      return
    }
    setError(null)
    setConfirmSecretReplace('text')
  }

  const handleUpdateSecretVoice = (e: React.FormEvent) => {
    e.preventDefault()
    const fileInput = (e.target as HTMLFormElement).querySelector<HTMLInputElement>('input[name="profile-voice-file"]')
    const file = fileInput?.files?.[0] ?? (recordedBlob.current ? new File([recordedBlob.current], 'recording.webm', { type: 'audio/webm' }) : null)
    if (!file) {
      setError('Please record or upload an audio file with your secret phrase.')
      return
    }
    setError(null)
    pendingVoiceFile.current = file
    setConfirmSecretReplace('voice')
  }

  const cancelReplaceSecret = () => {
    setConfirmSecretReplace(null)
    pendingVoiceFile.current = null
  }

  const handleUpdateGreetingImage = async (e: React.FormEvent) => {
    e.preventDefault()
    const t = greetingImageText.trim()
    if (!t) {
      setError('Enter text to generate your new security image.')
      return
    }
    if (t.length > SECRET_MAX_CHARS) {
      setError(`Image text must be at most ${SECRET_MAX_CHARS} characters.`)
      return
    }
    setError(null)
    setGreetingSuccess(false)
    setGreetingSaving(true)
    try {
      const p = await api.updateProfileGreetingImage(t)
      setProfile(p)
      setGreetingSuccess(true)
      setGreetingImageText('')
    } catch (err) {
      setError(userFriendlyMessage(err instanceof Error ? err.message : 'Update failed', 'profile'))
    } finally {
      setGreetingSaving(false)
    }
  }

  const handleUpdateLoginMode = async (mode: 'both' | 'image_only') => {
    setError(null)
    setModeSaving(true)
    try {
      const p = await api.updateLoginMode(mode)
      setProfile(p)
      setLoginMode(p.login_mode)
    } catch (err) {
      setError(userFriendlyMessage(err instanceof Error ? err.message : 'Mode update failed', 'profile'))
    } finally {
      setModeSaving(false)
    }
  }

  const confirmReplaceSecret = async () => {
    if (confirmSecretReplace === 'text') {
      setSecretSuccess(false)
      setSecretSaving(true)
      setConfirmSecretReplace(null)
      try {
        const p = await api.updateProfileSecretText(secretText.trim())
        setProfile(p)
        setSecretSuccess(true)
        setSecretText('')
      } catch (err) {
        setError(userFriendlyMessage(err instanceof Error ? err.message : 'Update failed', 'profile'))
      } finally {
        setSecretSaving(false)
      }
    } else if (confirmSecretReplace === 'voice' && pendingVoiceFile.current) {
      const form = new FormData()
      form.set('file', pendingVoiceFile.current)
      pendingVoiceFile.current = null
      setSecretSuccess(false)
      setSecretSaving(true)
      setConfirmSecretReplace(null)
      try {
        const p = await api.updateProfileSecretVoice(form)
        setProfile(p)
        setSecretSuccess(true)
        setSecretTab('voice')
        recordedBlob.current = null
        setAudioUrl(null)
      } catch (err) {
        setError(userFriendlyMessage(err instanceof Error ? err.message : 'Update failed', 'profile'))
      } finally {
        setSecretSaving(false)
      }
    }
  }

  const startRecording = () => {
    navigator.mediaDevices.getUserMedia({ audio: true }).then((stream) => {
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
    }).catch(() => setError('Microphone access denied.'))
  }

  const stopRecording = () => {
    mediaRecorder.current?.stop()
    setRecording(false)
  }

  const profileSteps = useMemo<Step[]>(
    () => [
      {
        target: 'body',
        placement: 'center',
        title: 'Your profile',
        content:
          'Manage your account details and your semantic secret. The secret is how you prove identity after entering your password.',
        disableBeacon: true,
      },
      {
        target: '[data-tour="profile-header"]',
        title: 'Header',
        content: 'Your profile title. Use Sign out in the top navigation to end this device’s session.',
      },
      {
        target: '[data-tour="profile-account"]',
        title: 'Account',
        content: 'Update username, optional email, or set a new password. Leave password blank to keep the current one.',
      },
      {
        target: '[data-tour="profile-secret"]',
        title: 'Semantic secret',
        content:
          'Change your sign-in phrase here (text or voice). Replacing it overwrites the old one—you’ll use the new phrase next time you sign in.',
      },
    ],
    []
  )

  if (loading) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-6 flex items-center gap-3" aria-live="polite">
        <span className="sas-spinner text-sky-600" aria-hidden />
        <p className="text-slate-600">Loading profile…</p>
      </div>
    )
  }

  if (!profile) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-6">
        <p className="text-slate-600">Could not load profile. <Link to="/login" className="text-sky-600 hover:underline">Sign in</Link>.</p>
      </div>
    )
  }

  return (
    <div className="space-y-8">
      <PageTour storageKey={TOUR_STORAGE.profile} steps={profileSteps} />
      <div data-tour="profile-header">
        <h1 className="text-2xl font-semibold text-slate-800">Profile</h1>
      </div>

      {error && (
        <div className="rounded-lg bg-red-50 p-3 text-sm text-red-700 ring-1 ring-red-100" role="alert">
          <p>{error}</p>
          <p className="mt-1 text-red-600/90">Fix the details above and try again.</p>
        </div>
      )}

      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm" data-tour="profile-account">
        <h2 className="text-lg font-semibold text-slate-800">Account</h2>
        <p className="mt-1 text-sm text-slate-500">Update username, email, or password. Email must be unique.</p>
        <form onSubmit={handleUpdateAccount} className="mt-4 space-y-4">
          <div>
            <label htmlFor="profile-username" className="block text-sm font-medium text-slate-700">Username (required)</label>
            <input
              id="profile-username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2"
              required
            />
          </div>
          <div>
            <label htmlFor="profile-email" className="block text-sm font-medium text-slate-700">Email (optional, leave blank to clear)</label>
            <input
              id="profile-email"
              type="email"
              value={email}
              onChange={(e) => { setEmail(e.target.value); setEmailTouched(true); }}
              onBlur={() => setEmailTouched(true)}
              className={`mt-1 block w-full rounded-lg border px-3 py-2 ${
                emailTouched && emailInvalid ? 'border-red-400' : 'border-slate-300'
              }`}
              aria-invalid={emailTouched && emailInvalid}
              aria-describedby={emailTouched && emailInvalid ? 'profile-email-hint' : undefined}
            />
            {emailTouched && emailInvalid && (
              <p id="profile-email-hint" className="mt-1 text-sm text-red-600">Enter a valid email address.</p>
            )}
          </div>
          <div>
            <label htmlFor="profile-password" className="block text-sm font-medium text-slate-700">New password (optional—leave blank to keep current)</label>
            <input
              id="profile-password"
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2"
              placeholder="Leave blank to keep current"
            />
          </div>
          <button
            type="submit"
            disabled={accountSaving || emailInvalid}
            aria-busy={accountSaving}
            className="rounded-xl bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-700 disabled:opacity-50 inline-flex items-center min-touch"
          >
            {accountSaving && <span className="sas-spinner sas-spinner-sm" aria-hidden />}
            {accountSaving ? 'Saving…' : 'Update account'}
          </button>
          {accountSuccess && <p className="text-sm text-green-600" role="status">Account updated.</p>}
        </form>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm" data-tour="profile-secret">
        <h2 className="text-lg font-semibold text-slate-800">Secret (sign-in phrase)</h2>
        <p className="mt-1 text-sm text-slate-500">
          You sign in by describing this idea in your own words (or by speaking it). Current type: <strong>{profile.secret_type}</strong>. One per account; changing overwrites the previous.
        </p>
        <div className="mt-4 flex gap-2 rounded-xl bg-slate-100 p-1.5" role="tablist" aria-label="Secret type">
          <button
            type="button"
            role="tab"
            aria-selected={secretTab === 'text'}
            onClick={() => { setSecretTab('text'); setError(null); }}
            className={`flex-1 rounded-lg py-2 px-3 text-sm font-medium ${secretTab === 'text' ? 'bg-white text-sky-600 shadow-sm' : 'text-slate-600 hover:bg-slate-200/60'}`}
          >
            Text
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={secretTab === 'voice'}
            onClick={() => { setSecretTab('voice'); setError(null); }}
            className={`flex-1 rounded-lg py-2 px-3 text-sm font-medium ${secretTab === 'voice' ? 'bg-white text-sky-600 shadow-sm' : 'text-slate-600 hover:bg-slate-200/60'}`}
          >
            Voice
          </button>
        </div>

        {confirmSecretReplace && (
          <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-4 space-y-3" role="alert">
            <p className="text-sm text-amber-900">
              This will replace your current secret. You&apos;ll use the new phrase to sign in next time. Continue?
            </p>
            <div className="flex flex-wrap gap-2">
              <button type="button" onClick={confirmReplaceSecret} disabled={secretSaving} aria-busy={secretSaving} className="rounded-lg bg-amber-600 px-4 py-2 text-sm font-medium text-white hover:bg-amber-700 disabled:opacity-50 inline-flex items-center">
                {secretSaving && <span className="sas-spinner sas-spinner-sm" aria-hidden />}
                {secretSaving ? 'Saving…' : 'Yes, replace secret'}
              </button>
              <button type="button" onClick={cancelReplaceSecret} disabled={secretSaving} className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50">
                Cancel
              </button>
            </div>
          </div>
        )}

        {secretTab === 'text' && (
          <form onSubmit={handleUpdateSecretText} className="mt-4 space-y-3">
            <label htmlFor="profile-secret" className="block text-sm font-medium text-slate-700">
              New secret phrase (required, max {SECRET_MAX_CHARS} characters)
            </label>
            <textarea
              id="profile-secret"
              rows={3}
              value={secretText}
              onChange={(e) => setSecretText(e.target.value)}
              className="block w-full rounded-lg border border-slate-300 px-3 py-2"
              placeholder="Type your new secret phrase"
              minLength={1}
              maxLength={SECRET_MAX_CHARS}
            />
            <p className="text-xs text-slate-500" aria-live="polite">
              {secretText.length}/{SECRET_MAX_CHARS} characters
            </p>
            <button
              type="submit"
              disabled={
                secretSaving ||
                !secretText.trim() ||
                secretText.trim().length > SECRET_MAX_CHARS
              }
              aria-busy={secretSaving}
              className="rounded-xl bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-700 disabled:opacity-50 inline-flex items-center"
            >
              {secretSaving && <span className="sas-spinner sas-spinner-sm" aria-hidden />}
              {secretSaving ? 'Saving…' : 'Update secret (text)'}
            </button>
          </form>
        )}

        {secretTab === 'voice' && (
          <form onSubmit={handleUpdateSecretVoice} className="mt-4 space-y-3">
            <p className="text-sm font-medium text-slate-700">Record or upload audio with your new secret phrase</p>
            <p className="text-xs text-slate-500">
              Transcribed text must be at most {SECRET_MAX_CHARS} characters.
            </p>
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
              <label className="block text-sm text-slate-600">Or upload audio file</label>
              <input type="file" name="profile-voice-file" accept="audio/*" className="mt-1 block w-full text-sm text-slate-500 file:rounded-lg file:border-0 file:bg-sky-100 file:px-3 file:py-1.5 file:text-sky-700" />
            </div>
            <button
              type="submit"
              disabled={secretSaving}
              aria-busy={secretSaving}
              className="rounded-xl bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-700 disabled:opacity-50 inline-flex items-center"
            >
              {secretSaving && <span className="sas-spinner sas-spinner-sm" aria-hidden />}
              {secretSaving ? 'Saving…' : 'Update secret (voice)'}
            </button>
          </form>
        )}

        {secretSuccess && <p className="mt-3 text-sm text-green-600" role="status">Secret updated.</p>}
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-lg font-semibold text-slate-800">Login mode</h2>
        <p className="mt-1 text-sm text-slate-500">Choose whether login requires both image + semantic step, or image-only.</p>
        <div className="mt-3 flex gap-2 rounded-xl bg-slate-100 p-1.5">
          <button
            type="button"
            disabled={modeSaving}
            onClick={() => void handleUpdateLoginMode('both')}
            className={`flex-1 rounded-lg py-2 px-3 text-sm font-medium ${loginMode === 'both' ? 'bg-white text-sky-600 shadow-sm' : 'text-slate-600 hover:bg-slate-200/60'}`}
          >
            Both (image + semantic)
          </button>
          <button
            type="button"
            disabled={modeSaving}
            onClick={() => void handleUpdateLoginMode('image_only')}
            className={`flex-1 rounded-lg py-2 px-3 text-sm font-medium ${loginMode === 'image_only' ? 'bg-white text-sky-600 shadow-sm' : 'text-slate-600 hover:bg-slate-200/60'}`}
          >
            Image only
          </button>
        </div>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-lg font-semibold text-slate-800">Security greeting image</h2>
        <p className="mt-1 text-sm text-slate-500">
          The image you recognize at sign-in (six-tile pick). Updating only changes this image—your semantic secret phrase stays the same until you change it above.
        </p>
        <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-3">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Current security image</p>
          {currentGreetingUrl ? (
            <img
              src={currentGreetingUrl}
              alt="Current security greeting"
              className="mt-2 h-32 w-32 rounded-md border border-slate-200 object-cover"
            />
          ) : (
            <p className="mt-2 text-sm text-slate-500">No image preview available.</p>
          )}
        </div>
        <form onSubmit={handleUpdateGreetingImage} className="mt-4 space-y-3">
          <label htmlFor="profile-greeting-image" className="block text-sm font-medium text-slate-700">
            New image text (required, max {SECRET_MAX_CHARS} characters)
          </label>
          <textarea
            id="profile-greeting-image"
            rows={2}
            value={greetingImageText}
            onChange={(e) => setGreetingImageText(e.target.value)}
            className="block w-full rounded-lg border border-slate-300 px-3 py-2"
            placeholder="Describe the illustration you will recognize at login"
            minLength={1}
            maxLength={SECRET_MAX_CHARS}
          />
          <p className="text-xs text-slate-500" aria-live="polite">
            {greetingImageText.length}/{SECRET_MAX_CHARS} characters
          </p>
          <button
            type="submit"
            disabled={
              greetingSaving ||
              !greetingImageText.trim() ||
              greetingImageText.trim().length > SECRET_MAX_CHARS
            }
            aria-busy={greetingSaving}
            className="rounded-xl bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-700 disabled:opacity-50 inline-flex items-center"
          >
            {greetingSaving && <span className="sas-spinner sas-spinner-sm" aria-hidden />}
            {greetingSaving ? 'Generating…' : 'Update security image'}
          </button>
          {greetingSuccess && (
            <p className="text-sm text-green-600" role="status">Security image updated. Use this image next time you sign in.</p>
          )}
        </form>
      </section>
    </div>
  )
}
