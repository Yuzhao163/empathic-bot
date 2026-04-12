import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { LineChart, Line, XAxis, YAxis, ResponsiveContainer } from 'recharts'
import { Send, Trash2, Plus, MessageCircle, Menu, X, Sun, Moon, Monitor, ChevronDown } from 'lucide-react'
import { apiChatStream, getNickname, setNickname, getSuggestions } from './api'
import { useTheme } from './useTheme'
import type { Message, Session } from './types'
import { EMOTION_CONFIG } from './types'

// ============================================================================
// Constants
// ============================================================================

const GATEWAY_URL = import.meta.env.VITE_GATEWAY_URL || ''
const STORAGE_KEY = 'empathic_sessions'
const MAX_SESSIONS = 50

// User identity: 优先从URL参数读取飞书open_id，作为长记忆隔离键
// 格式: https://your-vercel.app?user_id=ou_xxx

const EMOTION_VALUES: Record<string, number> = {
  positive: 100, negative: 20, anxious: 40, angry: 15, sad: 30, neutral: 60,
}

// ============================================================================
// Session Storage
// ============================================================================

function loadSessions(): Record<string, Session> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return {}
    const sessions: Record<string, Session> = JSON.parse(raw)
    const sorted = Object.values(sessions).sort((a, b) => b.createdAt - a.createdAt)
    if (sorted.length > MAX_SESSIONS) sorted.slice(MAX_SESSIONS).forEach(s => delete sessions[s.id])
    return sessions
  } catch { return {} }
}

function saveSessions(sessions: Record<string, Session>) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions))
  } catch {
    const sorted = Object.values(sessions).sort((a, b) => b.createdAt - a.createdAt)
    if (sorted.length > 1) {
      const updated = { ...sessions }
      delete updated[sorted[sorted.length - 1].id]
      localStorage.setItem(STORAGE_KEY, JSON.stringify(updated))
    }
  }
}

// ============================================================================
// Emotion Detection
// ============================================================================

function detectEmotion(text: string): { emotion: string; prob: number } {
  const t = text.toLowerCase()
  const map: [string, string[], number][] = [
    ['positive', ['开心','高兴','快乐','棒','happy','great','wonderful','love','excited','joy'], 0.85],
    ['negative', ['难过','伤心','痛苦','抑郁','崩溃','sad','hurt','depressed','crying','misery'], 0.80],
    ['anxious',  ['焦虑','担心','害怕','紧张','不安','压力','anxious','worried','scared','nervous','stress'], 0.78],
    ['angry',    ['生气','愤怒','讨厌','烦','火','angry','hate','furious','mad'], 0.82],
  ]
  for (const [emotion, words, prob] of map) {
    for (const w of words) if (t.includes(w)) return { emotion, prob }
  }
  return { emotion: 'neutral', prob: 0.70 }
}

// ============================================================================
// Emotion Trend
// ============================================================================

function useEmotionTrend(messages: Message[]) {
  return useMemo(() => {
    const userMsgs = messages.filter(m => m.role === 'user').slice(-6)
    return userMsgs.map((m, i) => ({ index: i, value: EMOTION_VALUES[m.emotion] ?? 60, emotion: m.emotion }))
  }, [messages])
}

// ============================================================================
// Theme Icons
// ============================================================================

const ThemeIcon = ({ mode }: { mode: string }) => {
  if (mode === 'dark') return <Moon size={16} />
  if (mode === 'light') return <Sun size={16} />
  return <Monitor size={16} />
}

// ============================================================================
// Components
// ============================================================================

function EmotionBadge({ emotion, prob, size = 'md' }: { emotion: string; prob: number; size?: 'sm' | 'md' | 'lg' }) {
  const config = EMOTION_CONFIG[emotion] ?? EMOTION_CONFIG.neutral
  const fontSize = size === 'lg' ? '2rem' : size === 'md' ? '1.25rem' : '0.875rem'
  const padding  = size === 'lg' ? '0.75rem 1.25rem' : size === 'md' ? '0.5rem 1rem' : '0.25rem 0.625rem'
  return (
    <motion.div style={{ background: config.bg, color: config.color, padding, borderRadius: '9999px', display: 'inline-flex', alignItems: 'center', gap: '0.5rem', fontSize }}
      animate={{ scale: [1, 1.05, 1] }} transition={{ duration: 0.3 }}>
      <span>{config.emoji}</span>
      <span>{config.label}</span>
      <span style={{ opacity: 0.7, fontSize: '0.75em' }}>{Math.round(prob * 100)}%</span>
    </motion.div>
  )
}

function EmotionTrendChart({ data }: { data: ReturnType<typeof useEmotionTrend> }) {
  const { theme } = useTheme()
  if (data.length < 2) return null
  return (
    <div style={{ height: 60, marginTop: '0.5rem' }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data}>
          <XAxis dataKey="index" hide />
          <YAxis domain={[0, 100]} hide />
          <Line type="monotone" dataKey="value" stroke={theme.trendColor} strokeWidth={2} dot={{ r: 4, fill: theme.trendColor }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

function AdviceCard({ emotion }: { emotion: string }) {
  const config = EMOTION_CONFIG[emotion] ?? EMOTION_CONFIG.neutral
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
      style={{ background: config.bg, borderLeft: `3px solid ${config.color}`, padding: '0.75rem 1rem', borderRadius: '0 0.5rem 0.5rem 0', fontSize: '0.875rem', color: config.color, marginTop: '0.5rem' }}>
      💡 {config.advice}
    </motion.div>
  )
}

function SuggestionChips({ onSelect, suggestions: initSuggestions }: { onSelect: (text: string) => void; suggestions?: string[] }) {
  const { theme } = useTheme()
  const [dynSuggestions, setDynSuggestions] = useState<string[]>(initSuggestions || [])

  useEffect(() => {
    if (dynSuggestions.length === 0 && initSuggestions?.length) {
      setDynSuggestions(initSuggestions)
    }
  }, [initSuggestions])

  const toShow = dynSuggestions.length > 0 ? dynSuggestions : (initSuggestions || [])

  if (toShow.length === 0) return null

  return (
    <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginTop: '0.5rem' }}>
      {toShow.map(s => (
        <button key={s} onClick={() => onSelect(s)}
          style={{ padding: '0.375rem 0.75rem', borderRadius: '9999px', border: `1px solid ${theme.border}`, background: theme.surface, color: theme.text, fontSize: '0.8125rem', cursor: 'pointer' }}>
          {s}
        </button>
      ))}
    </div>
  )
}

function MessageBubble({ msg }: { msg: Message }) {
  const { theme } = useTheme()
  const isUser = msg.role === 'user'
  const [showThink, setShowThink] = useState(false)

  const raw = msg.content || ''
  // Strip <think>...</think> tags from display (handle both Chinese and English tags)
  const thinkMatch = raw.match(/<think>[\s\S]*?<\/think>/)
  const displayContent = (() => {
    if (!thinkMatch) return raw
    const withoutThink = raw.replace(/<think>[\s\S]*?<\/think>/, '').trim()
    // If only think content so far, show a subtle indicator
    if (!withoutThink) return null
    return withoutThink
  })()

  const isLoading = isUser === false && msg.content === ''

  return (
    <motion.div initial={{ opacity: 0, y: 12, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }}
      style={{ display: 'flex', flexDirection: isUser ? 'row-reverse' : 'row', alignItems: 'flex-start', gap: '0.75rem' }}>
      <div style={{ width: 36, height: 36, borderRadius: '50%', flexShrink: 0, background: isUser ? theme.accent : '#10B981', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '1rem' }}>
        {isUser ? '😊' : '🤖'}
      </div>
      <div style={{ maxWidth: '72%' }}>
        {thinkMatch && !isLoading && (
          <div style={{ fontSize: '0.75rem', color: theme.textMuted, marginBottom: '0.25rem', display: 'flex', alignItems: 'center', gap: '0.25rem', cursor: 'pointer', userSelect: 'none' }} onClick={() => setShowThink(v => !v)}>
            <ChevronDown size={14} style={{ transform: showThink ? 'rotate(0deg)' : 'rotate(-90deg)', transition: 'transform 0.2s', opacity: 0.7 }} />
            <span style={{ opacity: 0.7 }}>💭 思考过程</span>
          </div>
        )}
        {thinkMatch && showThink && (
          <div style={{ fontSize: '0.75rem', color: theme.textMuted, background: theme.surface, border: '1px solid ' + theme.border, borderRadius: '0.5rem', padding: '0.5rem 0.75rem', marginBottom: '0.375rem', fontFamily: 'monospace', whiteSpace: 'pre-wrap', maxHeight: 200, overflowY: 'auto', lineHeight: 1.5 }}>
            {thinkMatch[0].replace(/<think>\s*/, '').replace(/<\/think>/, '').trim()}
          </div>
        )}
        {isLoading ? (
          <div style={{ padding: '0.875rem 1.125rem', borderRadius: '1rem 1rem 1rem 0.25rem', background: theme.assistantBubble, boxShadow: '0 1px 4px rgba(0,0,0,0.08)', fontSize: '0.9375rem', color: theme.textMuted, fontStyle: 'italic' }}>
            思考中...
          </div>
        ) : (
          <div style={{ padding: '0.875rem 1.125rem', borderRadius: isUser ? '1rem 1rem 0.25rem 1rem' : '1rem 1rem 1rem 0.25rem', background: isUser ? theme.userBubble : theme.assistantBubble, color: isUser ? theme.userText : theme.assistantText, boxShadow: '0 1px 4px rgba(0,0,0,0.08)', fontSize: '0.9375rem', lineHeight: 1.6 }}>
            {displayContent || <span style={{ opacity: 0.5, fontStyle: 'italic' }}>思考中...</span>}
          </div>
        )}
        <div style={{ fontSize: '0.75rem', color: theme.textMuted, marginTop: '0.375rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          {msg.role === 'assistant' && <EmotionBadge emotion={msg.emotion} prob={msg.emotionProb} size="sm" />}
          <span>{new Date(msg.timestamp).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}</span>
        </div>
        {msg.role === 'assistant' && msg.emotion !== 'neutral' && <AdviceCard emotion={msg.emotion} />}
      </div>
    </motion.div>
  )
}

function TypingIndicator() {
  const { theme } = useTheme()
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} style={{ display: 'flex', gap: '0.75rem', alignItems: 'flex-start' }}>
      <div style={{ width: 36, height: 36, borderRadius: '50%', background: '#10B981', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '1rem' }}>🤖</div>
      <div style={{ padding: '0.875rem 1.125rem', background: theme.assistantBubble, borderRadius: '1rem 1rem 1rem 0.25rem', boxShadow: '0 1px 4px rgba(0,0,0,0.08)' }}>
        <span style={{ display: 'inline-flex', gap: 4 }}>
          {[0, 0.2, 0.4].map(d => <span key={d} style={{ width: 6, height: 6, borderRadius: '50%', background: theme.textMuted, animation: `bounce 1.2s ${d}s infinite` }} />)}
        </span>
      </div>
    </motion.div>
  )
}

function EmptyState() {
  const { theme } = useTheme()
  return (
    <div style={{ textAlign: 'center', padding: '3rem 1rem', color: theme.textMuted }}>
      <MessageCircle size={48} style={{ margin: '0 auto 1rem', opacity: 0.5 }} />
      <p style={{ fontSize: '1rem', fontWeight: 500, color: theme.text }}>在这里说出你的心情</p>
      <p style={{ fontSize: '0.875rem', marginTop: '0.5rem' }}>我会用心倾听，温暖陪伴</p>
      {!GATEWAY_URL && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
          style={{ marginTop: '1.5rem', padding: '1rem', background: theme.errorBg, borderRadius: '0.75rem', color: theme.errorColor, fontSize: '0.875rem' }}>
          ⚠️ 未配置后端地址（VITE_GATEWAY_URL）<br />
          请在 Vercel 环境变量中设置
        </motion.div>
      )}
    </div>
  )
}

// ============================================================================
// App
// ============================================================================

export default function App() {
  const { theme, mode, toggleTheme } = useTheme()
  const [sessions, setSessions] = useState<Record<string, Session>>(() => loadSessions())
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null)
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [CACHED_NICK, setCACHED_NICK] = useState('')
  const [suggestions, setSuggestions] = useState<string[]>([])
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // 初始化加载昵称和建议
  useEffect(() => {
    getNickname().then(nick => { if (nick) setCACHED_NICK(nick) })
    getSuggestions('neutral').then(s => { if (s?.length) setSuggestions(s) })
  }, [])

  // 情绪变化时重新加载建议
  useEffect(() => {
    getSuggestions('neutral').then(s => { if (s?.length) setSuggestions(s) })
  }, ['neutral'])

  const currentSession = currentSessionId ? sessions[currentSessionId] : null
  const messages = currentSession?.messages ?? []
  const trendData = useEmotionTrend(messages)

  useEffect(() => {
    if (Object.keys(sessions).length > 0) saveSessions(sessions)
  }, [sessions])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = useCallback(async () => {
    if (!input.trim() || streaming) return
    const text = input.trim()
    setInput('')
    setError(null)

    let sessionId = currentSessionId
    if (!sessionId) {
      sessionId = Date.now().toString(36) + Math.random().toString(36).slice(2)
      setCurrentSessionId(sessionId)
      setSessions(prev => ({
        ...prev,
        [sessionId!]: { id: sessionId!, title: text.slice(0, 20), messages: [], createdAt: Date.now() },
      }))
    }

    const { emotion, prob } = detectEmotion(text)
    const userMsg: Message = { id: Date.now().toString(36) + Math.random().toString(36).slice(2), role: 'user', content: text, emotion, emotionProb: prob, timestamp: Date.now() }

    // 先插入用户消息
    setSessions(prev => ({
      ...prev,
      [sessionId!]: { ...prev[sessionId!], messages: [...prev[sessionId!].messages, userMsg] },
    }))

    // 创建助手空消息（用于流式增量更新）
    const assistantId = Date.now().toString(36) + Math.random().toString(36).slice(2)
    const assistantMsg: Message = { id: assistantId, role: 'assistant', content: '', emotion, emotionProb: prob, timestamp: Date.now() }
    setSessions(prev => ({
      ...prev,
      [sessionId!]: { ...prev[sessionId!], messages: [...prev[sessionId!].messages, assistantMsg] },
    }))

    setStreaming(true)

    // 流式追加 token
    const appendToken = (token: string) => {
      setSessions(prev => {
        const msgs = prev[sessionId!]?.messages ?? []
        return {
          ...prev,
          [sessionId!]: {
            ...prev[sessionId!],
            messages: msgs.map(m => m.id === assistantId ? { ...m, content: m.content + token } : m),
          },
        }
      })
    }

    // 结束流式
    const finishStream = (result: { emotion?: string; advice?: string }) => {
      setSessions(prev => {
        const msgs = prev[sessionId!]?.messages ?? []
        return {
          ...prev,
          [sessionId!]: {
            ...prev[sessionId!],
            messages: msgs.map(m => m.id === assistantId
              ? { ...m, emotion: result.emotion || emotion, advice: result.advice }
              : m),
          },
        }
      })
      setStreaming(false)
    }

    // 流式出错
    const streamError = (errMsg: string | Error) => {
      setError(String(errMsg))
      const fallback = EMOTION_CONFIG[emotion]?.advice || '我在这里，愿意听你说。'
      setSessions(prev => {
        const msgs = prev[sessionId!]?.messages ?? []
        return {
          ...prev,
          [sessionId!]: {
            ...prev[sessionId!],
            messages: msgs.map(m => m.id === assistantId ? { ...m, content: fallback } : m),
          },
        }
      })
      setStreaming(false)
    }

    // 存一份历史（流式过程中避免闭包陷阱）
    const savedMessages = sessions[sessionId!]?.messages ?? []

    await apiChatStream(
      sessionId!,
      text,
      emotion,
      prob,
      savedMessages,
      appendToken,
      finishStream,
      streamError
    )
  }, [input, streaming, currentSessionId, sessions])

  const currentEmotion = messages.length > 0 ? (messages[messages.length - 1].emotion || 'neutral') : 'neutral'

  return (
    <div className="app" style={{ background: theme.bg }}>
      <AnimatePresence>
        {sidebarOpen && <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setSidebarOpen(false)}
          style={{ position: 'fixed', inset: 0, background: theme.overlay, zIndex: 99 }} />}
      </AnimatePresence>

      {/* Sidebar */}
      <motion.aside initial={{ x: -280 }} animate={{ x: sidebarOpen ? 0 : -280 }}
        style={{ position: 'fixed', left: 0, top: 0, bottom: 0, width: 280, zIndex: 100, background: theme.sidebar, boxShadow: '2px 0 16px rgba(0,0,0,0.1)', padding: '1.5rem', overflowY: 'auto' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.5rem' }}>
          <h2 style={{ fontSize: '1.125rem', fontWeight: 600, color: theme.text }}>对话历史</h2>
          <button onClick={() => setSidebarOpen(false)} style={{ background: 'none', border: 'none', cursor: 'pointer' }}><X size={20} color={theme.textMuted} /></button>
        </div>
        <button onClick={() => { setCurrentSessionId(null); setSidebarOpen(false) }}
          style={{ width: '100%', padding: '0.625rem', background: theme.accent, color: 'white', border: 'none', borderRadius: '0.75rem', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem', fontWeight: 500, marginBottom: '1rem' }}>
          <Plus size={18} /> 新对话
        </button>
        <div>
          {Object.values(sessions).sort((a, b) => b.createdAt - a.createdAt).map(session => (
            <button key={session.id} onClick={() => { setCurrentSessionId(session.id); setSidebarOpen(false) }}
              style={{ width: '100%', padding: '0.75rem', marginBottom: '0.5rem', background: session.id === currentSessionId ? `${theme.accent}20` : 'transparent', border: 'none', borderRadius: '0.5rem', cursor: 'pointer', textAlign: 'left' as const }}>
              <div style={{ fontSize: '0.875rem', fontWeight: 500, color: theme.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{session.title}</div>
              <div style={{ fontSize: '0.75rem', color: theme.textMuted, marginTop: '0.25rem' }}>{session.messages.length} 条消息</div>
            </button>
          ))}
        </div>
      </motion.aside>

      {/* Main */}
      <div className="main">
        <header style={{ padding: '1rem 1.5rem', borderBottom: `1px solid ${theme.border}`, display: 'flex', alignItems: 'center', gap: '1rem', background: theme.headerBg }}>
          <button onClick={() => setSidebarOpen(true)} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '0.25rem' }}><Menu size={24} color={theme.text} /></button>
          <div style={{ flex: 1 }}>
            <h1 style={{ fontSize: '1rem', fontWeight: 600, color: theme.text }}>情感对话</h1>
            <EmotionBadge emotion={currentEmotion} prob={0.8} size="sm" />
          </div>
          <button onClick={toggleTheme} title={`主题: ${mode === 'auto' ? '跟随系统' : mode === 'dark' ? '深色' : '浅色'}`}
            style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '0.25rem', display: 'flex', alignItems: 'center', color: theme.textMuted }}>
            <ThemeIcon mode={mode} />
          </button>
          {currentSessionId && (
            <button onClick={() => {
              const updated = { ...sessions }
              delete updated[currentSessionId]
              setSessions(updated)
              setCurrentSessionId(null)
            }} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '0.25rem' }} title="清空对话">
              <Trash2 size={20} color={theme.textMuted} />
            </button>
          )}
          <button onClick={() => {
            const nick = window.prompt('设置你的昵称（留空清除）', CACHED_NICK || '')
            if (nick !== null) {
              setNickname(nick).then(() => {
                setCACHED_NICK(nick || '')
              })
            }
          }} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '0.25rem', fontSize: '0.8rem', color: theme.textMuted, borderRadius: '0.5rem' }}>
            {(CACHED_NICK || '设置昵称')}
          </button>
        </header>

        <div style={{ padding: '0.75rem 1.5rem', background: theme.trendBg }}>
          <div style={{ fontSize: '0.75rem', color: theme.trendColor, fontWeight: 500, marginBottom: '0.25rem' }}>情绪趋势</div>
          <EmotionTrendChart data={trendData} />
        </div>

        {/* Messages */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          {messages.length === 0 ? <EmptyState /> : (
            <AnimatePresence>{messages.map(msg => <MessageBubble key={msg.id} msg={msg} />)}</AnimatePresence>
          )}
          {streaming && <TypingIndicator />}
          {!streaming && messages.length > 0 && (
            <SuggestionChips onSelect={(text) => { setInput(text); }} suggestions={suggestions} />
          )}
          {error && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
              style={{ textAlign: 'center', padding: '0.5rem', color: theme.errorColor, fontSize: '0.875rem' }}>
              ⚠️ {error}
            </motion.div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <div style={{ padding: '1rem 1.5rem', borderTop: `1px solid ${theme.border}`, background: theme.headerBg }}>
          {error && <div style={{ fontSize: '0.75rem', color: theme.errorColor, marginBottom: '0.5rem' }}>⚠️ {error}</div>}
          <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'flex-end' }}>
            <textarea value={input} onChange={e => setInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() } }}
              placeholder="说出你的心情..." rows={1}
              style={{ flex: 1, padding: '0.75rem 1rem', borderRadius: '1.25rem', border: `1.5px solid ${theme.border}`, fontSize: '0.9375rem', resize: 'none', outline: 'none', fontFamily: 'inherit', lineHeight: 1.5, maxHeight: '8rem', overflowY: 'auto', transition: 'border-color 0.2s', background: theme.inputBg, color: theme.text }} />
            <motion.button onClick={handleSend} disabled={!input.trim() || streaming} whileTap={{ scale: 0.95 }}
              style={{ width: 48, height: 48, borderRadius: '50%', background: input.trim() && !streaming ? theme.accent : theme.border, border: 'none', cursor: input.trim() && !streaming ? 'pointer' : 'not-allowed', display: 'flex', alignItems: 'center', justifyContent: 'center', transition: 'background 0.2s' }}>
              <Send size={20} color="white" />
            </motion.button>
          </div>
          <p style={{ fontSize: '0.75rem', color: theme.textMuted, textAlign: 'center', marginTop: '0.5rem' }}>按 Enter 发送 · Shift+Enter 换行</p>
        </div>
      </div>

      <style>{`
        @keyframes bounce { 0%, 80%, 100% { transform: translateY(0); } 40% { transform: translateY(-6px); } }
        .app { display: flex; height: 100vh; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
        .main { flex: 1; display: flex; flex-direction: column; min-width: 0; }
        textarea:focus { border-color: #8B5CF6 !important; }
      `}</style>
    </div>
  )
}
