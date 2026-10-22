import { reactive } from 'vue'
import { api, setCsrfToken } from './api'
import type { Session } from '../types'

export const auth = reactive<Session>({ user: null, setup_required: false, csrf_token: '' })
let loaded = false
let pending: Promise<void> | null = null
function apply(session: Session) {
  Object.assign(auth, session)
  setCsrfToken(session.csrf_token)
  loaded = true
}
export async function ensureSession(force = false): Promise<void> {
  if (loaded && !force) return
  if (!pending) pending = api<Session>('auth/session').then(apply).finally(() => { pending = null })
  return pending
}
export async function signIn(email: string, password: string, name?: string) {
  const endpoint = auth.setup_required ? 'auth/setup' : 'auth/login'
  const data = name === undefined ? { email, password } : { email, password, name }
  apply(await api<Session>(endpoint, 'POST', data))
}
export async function signOut() { apply(await api<Session>('auth/logout', 'POST')) }
export function expireSession() { auth.user = null; loaded = false }
