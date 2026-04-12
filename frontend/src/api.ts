/**
 * API Client — 统一封装，支持 SSE 流式
 * user_id: 从 URL ?user_id=ou_xxx 参数传入，用于长记忆隔离
 */

import type { ChatResult } from './types'

const GATEWAY_URL = import.meta.env.VITE_GATEWAY_URL || ''

// User identity for long-term memory isolation
const USER_ID = (() => {
  const params = new URLSearchParams(window.location.search)
  return params.get('user_id') || 'anonymous'
})()

// 昵称缓存
let CACHED_NICKNAME = ''

function buildBody(sessionId: string, message: string, emotion: string, emotionProb: number, history: import('./types').Message[]) {
  return {
    session_id: sessionId,
    user_id: USER_ID,
    message,
    context: history.slice(-6),
    emotion,
    emotion_prob: emotionProb,
  }
}

// 获取用户昵称
export async function getNickname(): Promise<string> {
  if (!GATEWAY_URL) return ''
  try {
    const res = await fetch(`${GATEWAY_URL}/profile/${USER_ID}`)
    if (!res.ok) return ''
    const data = await res.json()
    CACHED_NICKNAME = data.nickname || ''
    return CACHED_NICKNAME
  } catch { return '' }
}

// 更新昵称
export async function setNickname(nickname: string): Promise<void> {
  if (!GATEWAY_URL) return
  await fetch(`${GATEWAY_URL}/profile/${USER_ID}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ nickname }),
  })
  CACHED_NICKNAME = nickname
}

// 获取情绪建议问题
export async function getSuggestions(emotion: string): Promise<string[]> {
  if (!GATEWAY_URL) return []
  try {
    const res = await fetch(`${GATEWAY_URL}/profile/${USER_ID}/suggestions?emotion=${emotion}`)
    if (!res.ok) return []
    const data = await res.json()
    return data.suggestions || []
  } catch { return [] }
}

// 删除记忆
export async function deleteMemory(level: string = 'all'): Promise<void> {
  if (!GATEWAY_URL) return
  await fetch(`${GATEWAY_URL}/memory/${USER_ID}?level=${level}`, { method: 'DELETE' })
}

function checkUrl() {
  if (!GATEWAY_URL) {
    console.error('[EmpathicBot] VITE_GATEWAY_URL is not configured.')
  }
}

function buildBody(sessionId: string, message: string, emotion: string, emotionProb: number, history: import('./types').Message[]) {
  return {
    session_id: sessionId,
    user_id: USER_ID,
    message,
    context: history.slice(-6),
    emotion,
    emotion_prob: emotionProb,
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
    body: JSON.stringify(buildBody(sessionId, message, '', 0.5, history)),
  })

  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: `HTTP ${res.status}` }))
    throw new Error(err.error || `HTTP ${res.status}`)
  }

  return res.json()
}

/**
 * SSE 流式聊天 — 增量渲染
 */
export async function apiChatStream(
  sessionId: string,
  message: string,
  emotion: string,
  emotionProb: number,
  history: import('./types').Message[],
  onToken: (token: string) => void,
  onDone: (result: { emotion: string; advice?: string }) => void,
  onError: (err: Error) => void
) {
  checkUrl()
  if (!GATEWAY_URL) {
    onError(new Error('VITE_GATEWAY_URL not configured'))
    return
  }

  try {
    const res = await fetch(`${GATEWAY_URL}/api/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(buildBody(sessionId, message, emotion, emotionProb, history)),
    })

    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: `HTTP ${res.status}` }))
      throw new Error(err.error || `HTTP ${res.status}`)
    }

    const reader = res.body?.getReader()
    if (!reader) throw new Error('ReadableStream not supported')

    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const data = line.slice(6).trim()
        if (!data) continue

        try {
          const parsed = JSON.parse(data)
          if (parsed.done) {
            onDone({ emotion: parsed.emotion || emotion, advice: parsed.advice })
          } else if (parsed.token) {
            onToken(parsed.token)
          }
        } catch {
          // skip malformed JSON
        }
      }
    }
  } catch (e) {
    onError(e instanceof Error ? e : new Error(String(e)))
  }
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
