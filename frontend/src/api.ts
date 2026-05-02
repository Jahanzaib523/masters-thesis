const API_BASE = ''

const TOKEN_KEY = 'sas_token'

/** When set to `'1'`, API calls that use semantic LLM send `X-Semantic-LLM-Provider: openai` (requires server OPENAI_API_KEY). */
export const SEMANTIC_LLM_USE_OPENAI_KEY = 'sas_use_openai_llm'

export function semanticLlmHeaders(): Record<string, string> {
  try {
    if (typeof localStorage !== 'undefined' && localStorage.getItem(SEMANTIC_LLM_USE_OPENAI_KEY) === '1') {
      return { 'X-Semantic-LLM-Provider': 'openai' }
    }
  } catch {
    /* private mode */
  }
  return {}
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY)
}

function authHeaders(): HeadersInit {
  const t = getToken()
  return t ? { Authorization: `Bearer ${t}` } : {}
}

export type RegisterPayload = {
  username: string
  email?: string
  password: string
  secret_text: string
  image_text: string
  secret_type?: 'text' | 'voice'
}

export type LoginInitResponse = {
  challenge_id: number
  prompt: string
  secret_type: string
  audio_prompt_available: boolean
  greeting_image_url?: string | null
}

export type LoginResult = {
  success: boolean
  message: string
  similarity_score?: number
  token?: string
  retry_after_seconds?: number
}

export type UserPublic = { id: number; username: string; email?: string; created_at: string }

export type ProfileResponse = {
  id: number
  username: string
  email?: string | null
  created_at: string
  secret_type: 'text' | 'voice'
}

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

/** Map technical backend messages to user-friendly wording (Match system & real world). */
export function userFriendlyMessage(message: string, _context?: 'auth' | 'profile' | 'register'): string {
  const m = message.toLowerCase()
  if (m.includes('transcribe') || m.includes('unable to transcribe'))
    return "We couldn't understand the recording. Try again or type your answer instead."
  if (m.includes('username or email already exists'))
    return "That username or email is already in use. Sign in or use different details."
  if (m.includes('user with this username'))
    return "That username is already in use. Please choose another or sign in."
  if (m.includes('user with this email') || m.includes('email already exists'))
    return "That email is already in use. Sign in or use a different email."
  if (m.includes('incorrect password'))
    return "That password doesn't match. Try again or reset it from Profile if you're signed in elsewhere."
  if (m.includes('no password on file'))
    return "This account was created without a password. Register again with a password, or set one if you can open Profile another way."
  if (m.includes('unable to start login') || m.includes('identifier'))
    return "We don't have an account with that username or email. Check the spelling or register first."
  if (m.includes('invalid or expired token') || m.includes('not authenticated'))
    return "Your session has expired. Please sign in again."
  if (m.includes('too many'))
    return "Too many wrong answers. Use \"Start over\" below and try again with your username."
  if (m.includes('try again in') || m.includes('please wait'))
    return 'Too many attempts. Please wait for the cooldown period and try again.'
  if (m.includes('account locked') || m.includes('recovery via email'))
    return 'This account is locked for security. Use account recovery via your email.'
  if (m.includes('could not match') || m.includes('similarity'))
    return "That didn't match what we have on file. You can try again with a different way of describing your secret."
  if (m.includes('openai') && m.includes('not configured'))
    return 'OpenAI was selected but the server is not configured for it. Turn off “Use OpenAI” or ask the administrator to set OPENAI_API_KEY.'
  if (m.includes('hugging face') || m.includes('hf_api_token'))
    return 'Image generation is not configured on the server. Ask the administrator to set HF_API_TOKEN.'
  return message
}

async function handleRes(r: Response) {
  const text = await r.text()
  if (!r.ok) {
    let msg: string = text
    try {
      const j = JSON.parse(text) as { detail?: string | unknown[] }
      if (Array.isArray(j.detail)) {
        msg = j.detail.map((d: unknown) => (d && typeof d === 'object' && 'msg' in d ? (d as { msg: string }).msg : String(d))).join('. ')
      } else if (typeof j.detail === 'string') {
        msg = j.detail
      }
    } catch {
      // use text as is
    }
    throw new ApiError(msg, r.status)
  }
  return text ? JSON.parse(text) : null
}

export const api = {
  async register(payload: RegisterPayload): Promise<UserPublic> {
    const r = await fetch(`${API_BASE}/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...semanticLlmHeaders() },
      body: JSON.stringify(payload),
    })
    return handleRes(r)
  },

  async registerVoice(form: FormData): Promise<UserPublic> {
    const r = await fetch(`${API_BASE}/auth/voice/register`, {
      method: 'POST',
      headers: semanticLlmHeaders(),
      body: form,
    })
    return handleRes(r)
  },

  async loginInit(identifier: string, password: string, mode?: 'text' | 'voice'): Promise<LoginInitResponse> {
    const r = await fetch(`${API_BASE}/auth/login/init`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ identifier, password, mode: mode ?? 'text' }),
    })
    return handleRes(r)
  },

  async loginComplete(challengeId: number, responseText: string): Promise<LoginResult> {
    const r = await fetch(`${API_BASE}/auth/login/complete`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...semanticLlmHeaders() },
      body: JSON.stringify({ challenge_id: challengeId, response_text: responseText }),
    })
    return handleRes(r)
  },

  async loginVoiceComplete(challengeId: number, form: FormData): Promise<LoginResult> {
    form.set('challenge_id', String(challengeId))
    const r = await fetch(`${API_BASE}/auth/voice/login/complete`, {
      method: 'POST',
      headers: semanticLlmHeaders(),
      body: form,
    })
    return handleRes(r)
  },

  voiceLoginInit(identifier: string, password: string): Promise<LoginInitResponse> {
    return this.loginInit(identifier, password, 'voice')
  },

  getPromptAudio(challengeId: number): string {
    return `${API_BASE}/auth/tts/prompt/${challengeId}`
  },

  async getProfile(): Promise<ProfileResponse> {
    const r = await fetch(`${API_BASE}/auth/profile`, { headers: authHeaders() })
    return handleRes(r)
  },

  async updateProfile(payload: { username?: string; email?: string | null; new_password?: string }): Promise<ProfileResponse> {
    const r = await fetch(`${API_BASE}/auth/profile`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify(payload),
    })
    return handleRes(r)
  },

  async updateProfileSecretText(secret_text: string): Promise<ProfileResponse> {
    const r = await fetch(`${API_BASE}/auth/profile/secret`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders(), ...semanticLlmHeaders() },
      body: JSON.stringify({ secret_text }),
    })
    return handleRes(r)
  },

  async updateProfileSecretVoice(form: FormData): Promise<ProfileResponse> {
    const r = await fetch(`${API_BASE}/auth/profile/secret/voice`, {
      method: 'POST',
      headers: { ...authHeaders(), ...semanticLlmHeaders() },
      body: form,
    })
    return handleRes(r)
  },
}
