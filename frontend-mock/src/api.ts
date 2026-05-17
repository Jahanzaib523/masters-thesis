const API_BASE = ''

const TOKEN_KEY = 'sas_token'

export const SEMANTIC_LLM_USE_OPENAI_KEY = 'sas_use_openai_llm'

export function semanticLlmHeaders(): Record<string, string> {
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
  greeting_gallery_urls?: string[]
  semantic_required?: boolean
}

export type GreetingImagePickResult = {
  success: boolean
  message: string
  token?: string
  remaining_attempts?: number | null
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
  login_mode: 'both' | 'image_only'
}

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export function userFriendlyMessage(message: string, _context?: 'auth' | 'profile' | 'register'): string {
  return message
}

// Helper to simulate network delay
const delay = (ms: number) => new Promise(resolve => setTimeout(resolve, ms))

// Mock state
let mockProfile: ProfileResponse = {
  id: 1,
  username: 'mockuser',
  email: 'mock@example.com',
  created_at: new Date().toISOString(),
  secret_type: 'text',
  login_mode: 'both'
}

function createMockImageBlob(text: string, bgColor: string = '0ea5e9', fgColor: string = 'ffffff'): Blob {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="300" height="300" viewBox="0 0 300 300">
    <rect width="100%" height="100%" fill="#${bgColor}"/>
    <text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" font-family="sans-serif" font-weight="bold" font-size="20" fill="#${fgColor}">${text}</text>
  </svg>`;
  return new Blob([svg], { type: 'image/svg+xml' });
}

function createMockImageUrl(text: string, bgColor: string = '0ea5e9', fgColor: string = 'ffffff'): string {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="300" height="300" viewBox="0 0 300 300">
    <rect width="100%" height="100%" fill="#${bgColor}"/>
    <text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" font-family="sans-serif" font-weight="bold" font-size="20" fill="#${fgColor}">${text}</text>
  </svg>`;
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}

let mockGreetingImageUrl = createMockImageUrl('Mock Greeting')

export const api = {
  async register(payload: RegisterPayload): Promise<UserPublic> {
    await delay(1000)
    return { id: 1, username: payload.username, email: payload.email, created_at: new Date().toISOString() }
  },

  async previewGreetingImage(image_text: string): Promise<Blob> {
    await delay(1000)
    return createMockImageBlob(image_text || 'Preview')
  },

  async registerVoice(form: FormData): Promise<UserPublic> {
    await delay(1000)
    return { id: 1, username: form.get('username') as string, created_at: new Date().toISOString() }
  },

  async loginInit(identifier: string, password: string, mode?: 'text' | 'voice'): Promise<LoginInitResponse> {
    await delay(1000)
    return {
      challenge_id: 1,
      prompt: 'Describe your mock secret',
      secret_type: mode || 'text',
      audio_prompt_available: true,
      greeting_gallery_urls: [
        createMockImageUrl('Decoy 1', 'f43f5e'),
        mockGreetingImageUrl,
        createMockImageUrl('Decoy 2', '10b981'),
        createMockImageUrl('Decoy 3', '6366f1'),
        createMockImageUrl('Decoy 4', 'eab308'),
        createMockImageUrl('Decoy 5', 'd946ef'),
      ],
      semantic_required: true,
    }
  },

  async pickGreetingImage(challengeId: number, selectedSlot: number): Promise<GreetingImagePickResult> {
    await delay(800)
    if (selectedSlot === 1) {
      if (mockProfile.login_mode === 'image_only') {
         setToken('mock_token_abc123')
         return { success: true, message: 'Authentication successful.', token: 'mock_token_abc123' }
      }
      return { success: true, message: 'Correct security image. You can now complete the semantic step.' }
    }
    return { success: false, message: 'That is not your security image. Try another tile.', remaining_attempts: 2 }
  },

  async loginComplete(challengeId: number, responseText: string): Promise<LoginResult> {
    await delay(1000)
    if (responseText.length < 3) {
      return { success: false, message: "We could not match your description closely enough. You can try again.", similarity_score: 0.2 }
    }
    setToken('mock_token_abc123')
    return { success: true, message: 'Authentication successful.', similarity_score: 0.9, token: 'mock_token_abc123' }
  },

  async loginVoiceComplete(challengeId: number, form: FormData): Promise<LoginResult> {
    await delay(1500)
    setToken('mock_token_abc123')
    return { success: true, message: 'Authentication successful.', similarity_score: 0.9, token: 'mock_token_abc123' }
  },

  voiceLoginInit(identifier: string, password: string): Promise<LoginInitResponse> {
    return this.loginInit(identifier, password, 'voice')
  },

  getPromptAudio(challengeId: number): string {
    return ''
  },

  async getProfile(): Promise<ProfileResponse> {
    await delay(800)
    return { ...mockProfile }
  },

  getProfileGreetingImageUrl(): string {
    return mockGreetingImageUrl
  },

  async updateProfile(payload: { username?: string; email?: string | null; new_password?: string }): Promise<ProfileResponse> {
    await delay(1000)
    if (payload.username) mockProfile.username = payload.username
    if (payload.email !== undefined) mockProfile.email = payload.email
    return { ...mockProfile }
  },

  async updateProfileSecretText(secret_text: string): Promise<ProfileResponse> {
    await delay(1000)
    mockProfile.secret_type = 'text'
    return { ...mockProfile }
  },

  async updateProfileSecretVoice(form: FormData): Promise<ProfileResponse> {
    await delay(1500)
    mockProfile.secret_type = 'voice'
    return { ...mockProfile }
  },

  async updateProfileGreetingImage(image_text: string): Promise<ProfileResponse> {
    await delay(1500)
    mockGreetingImageUrl = createMockImageUrl(image_text)
    return { ...mockProfile }
  },

  async updateLoginMode(login_mode: 'both' | 'image_only'): Promise<ProfileResponse> {
    await delay(800)
    mockProfile.login_mode = login_mode
    return { ...mockProfile }
  },
}
