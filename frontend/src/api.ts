/**
 * API Client — 统一封装，减少 fetch 重复代码
 */

import type { ChatResult } from './types'

const GATEWAY_URL = import.meta.env.VITE_GATEWAY_URL || ''

function checkUrl() {
  if (!GATEWAY_URL) {
    console.error('[EmpathicBot] VITE_GATEWAY_URL is not set. See .env.example for configuration.')
  }
}

export async function apiChat(
  sessionId: string,
  message: string,
  history: import('./types').Message[]
): Promise<ChatResult> {
  checkUrl()
  if (!GATEWAY_URL) throw new Error('VITE_GATEWAY_URL not configured')

  const res = await fetch(`${GATEWAY_URL}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, context: history.slice(-6), emotion: '', emotion_prob: 0.5 }),
  })

  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: `HTTP ${res.status}` }))
    throw new Error(err.error || `HTTP ${res.status}`)
  }

  return res.json()
}

export async function apiHealth(): Promise<{ healthy: boolean; python: boolean; redis: boolean }> {
  checkUrl()
  if (!GATEWAY_URL) return { healthy: false, python: false, redis: false }
  try {
    const res = await fetch(`${GATEWAY_URL}/health`)
    if (!res.ok) return { healthy: false, python: false, redis: false }
    return res.json()
  } catch {
    return { healthy: false, python: false, redis: false }
  }
}
