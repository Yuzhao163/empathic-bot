import { useState, useEffect, useCallback, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Send, Trash2, Plus, Menu, X, Sun, Moon, Monitor, ChevronDown, Square, Wrench, Search, Zap, Check, AlertCircle, RefreshCw } from 'lucide-react'
import { apiChatStream, getNickname, setNickname, getSuggestions, generateToolCode } from './api'

// ===================== Theme =====================
type ThemeMode = 'light' | 'dark' | 'auto'
const themes = {
  light: { bg: '#F8F7FF', text: '#1F1F1F', textMuted: '#6B6B6B', accent: '#8B5CF6', headerBg: '#FFFFFF', sidebar: '#FFFFFF', border: '#E5E4F0', inputBg: '#FFFFFF', userBubble: '#8B5CF6', userText: '#FFFFFF', assistantBubble: '#F1EEFF', assistantText: '#1F1F1F', errorColor: '#DC2626', errorBg: '#FEE2E2', trendBg: '#F1EEFF', trendColor: '#8B5CF6', overlay: 'rgba(0,0,0,0.3)', surface: '#F8F7FF' },
  dark:  { bg: '#0F0F1A', text: '#E8E8F0', textMuted: '#888899', accent: '#A78BFA', headerBg: '#1A1A2E', sidebar: '#1A1A2E', border: '#2A2A3E', inputBg: '#1A1A2E', userBubble: '#6D28D9', userText: '#FFFFFF', assistantBubble: '#1E1E3A', assistantText: '#E8E8F0', errorColor: '#F87171', errorBg: '#7F1D1D', trendBg: '#1E1E3A', trendColor: '#A78BFA', overlay: 'rgba(0,0,0,0.6)', surface: '#1A1A2E' },
}

function useTheme() {
  const saved = (typeof window !== 'undefined' && (localStorage.getItem('theme') as ThemeMode)) || 'auto'
  const [mode, setMode] = useState<ThemeMode>(saved)
  const systemDark = typeof window !== 'undefined' ? window.matchMedia('(prefers-color-scheme: dark)').matches : false
  const effective = mode === 'auto' ? (systemDark ? 'dark' : 'light') : mode
  const theme = themes[effective]
  const toggleTheme = () => setMode(m => {
    const next = m === 'light' ? 'dark' : m === 'dark' ? 'auto' : 'light'
    localStorage.setItem('theme', next)
    return next
  })
  return { theme, mode, toggleTheme }
}

function ThemeIcon({ mode }: { mode: ThemeMode }) {
  if (mode === 'dark') return <Moon size={20} />
  if (mode === 'light') return <Sun size={20} />
  return <Monitor size={20} />
}

// ===================== Types =====================
interface Message { id: string; role: 'user' | 'assistant'; content: string; emotion: string; emotionProb: number; advice?: string; timestamp: number }
interface Session { id: string; title: string; messages: Message[]; createdAt: number }
interface Tool { id: string; name: string; display_name: string; description: string; category: string; icon: string; is_builtin: boolean; enabled: boolean }
interface EvolutionStatus { tools_count: number; skills_count: number; tools: Tool[]; skills: any[] }

// ===================== Emotion =====================
const EMOTION_CONFIG: Record<string, { color: string; label: string; emoji: string; advice: string }> = {
  neutral: { color: '#6B7280', label: '平静', emoji: '🌿', advice: '继续说吧，我在这里。' },
  happy: { color: '#10B981', label: '开心', emoji: '☀️', advice: '真高兴你有这样的心情！发生了什么好事？' },
  sad: { color: '#3B82F6', label: '难过', emoji: '🌧️', advice: '我在这里，愿意听你说说。' },
  anxious: { color: '#F59E0B', label: '焦虑', emoji: '🌪️', advice: '深呼吸。我陪着你，慢慢说。' },
  angry: { color: '#EF4444', label: '生气', emoji: '🔥', advice: '听起来你真的很不容易。先冷静一下，我在这里。' },
  positive: { color: '#10B981', label: '积极', emoji: '✨', advice: '很好！是什么让你有这样的好心情？' },
  negative: { color: '#6B7280', label: '低落', emoji: '🌙', advice: '没关系，这种时候我陪着你。' },
}

function loadSessions(): Record<string, Session> {
  try { return JSON.parse(localStorage.getItem('sessions') || '{}') } catch { return {} }
}
function saveSessions(sessions: Record<string, Session>) {
  localStorage.setItem('sessions', JSON.stringify(sessions))
}

function detectEmotion(text: string): { emotion: string; prob: number } {
  if (/开心|高兴|快乐|幸福|棒|不错真好/.test(text)) return { emotion: 'happy', prob: 0.8 }
  if (/难过|伤心|痛苦|抑郁|沮丧/.test(text)) return { emotion: 'sad', prob: 0.8 }
  if (/焦虑|担心|紧张|害怕|不安/.test(text)) return { emotion: 'anxious', prob: 0.8 }
  if (/生气|愤怒|恼火|烦躁|火大/.test(text)) return { emotion: 'angry', prob: 0.8 }
  return { emotion: 'neutral', prob: 0.7 }
}

function useEmotionTrend(messages: Message[]) {
  return messages.filter(m => m.role === 'assistant').slice(-7).map(m => ({
    emotion: m.emotion || 'neutral',
    prob: m.emotionProb || 0.5,
    time: new Date(m.timestamp).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }),
  }))
}

// ===================== Sub-components =====================
function EmotionBadge({ emotion, prob, size = 'md' }: { emotion: string; prob: number; size?: 'sm' | 'md' | 'lg' }) {
  const { theme } = useTheme()
  const cfg = EMOTION_CONFIG[emotion] || EMOTION_CONFIG.neutral
  const fs = size === 'sm' ? '0.7rem' : size === 'lg' ? '0.9rem' : '0.8rem'
  return (
    <span style={{ fontSize: fs, color: cfg.color, fontWeight: 500, background: cfg.color + '18', padding: '0.15rem 0.5rem', borderRadius: '999px' }}>
      {cfg.emoji} {cfg.label} {Math.round(prob * 100)}%
    </span>
  )
}

function EmotionTrendChart({ data }: { data: ReturnType<typeof useEmotionTrend> }) {
  const { theme } = useTheme()
  if (data.length === 0) return <span style={{ fontSize: '0.75rem', color: theme.textMuted }}>暂无趋势</span>
  return (
    <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', overflowX: 'auto', paddingBottom: '0.25rem' }}>
      {data.map((d, i) => {
        const cfg = EMOTION_CONFIG[d.emotion] || EMOTION_CONFIG.neutral
        return (
          <div key={i} style={{ textAlign: 'center', minWidth: '2.5rem' }}>
            <div style={{ width: 32, height: 32, borderRadius: '50%', background: cfg.color + '30', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.9rem', margin: '0 auto 0.25rem' }}>
              {cfg.emoji}
            </div>
            <div style={{ fontSize: '0.65rem', color: theme.textMuted }}>{d.time}</div>
          </div>
        )
      })}
    </div>
  )
}

function AdviceCard({ emotion }: { emotion: string }) {
  const { theme } = useTheme()
  const cfg = EMOTION_CONFIG[emotion] || EMOTION_CONFIG.neutral
  if (!cfg.advice) return null
  return (
    <motion.div initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} style={{ marginTop: '0.25rem', padding: '0.5rem 0.75rem', background: cfg.color + '12', borderRadius: '0.5rem', fontSize: '0.8rem', color: cfg.color }}>
      💡 {cfg.advice}
    </motion.div>
  )
}

function SuggestionChips({ onSelect, suggestions: initSuggestions }: { onSelect: (text: string) => void; suggestions?: string[] }) {
  const { theme } = useTheme()
  const [suggestions, setSuggestions] = useState<string[]>(initSuggestions || [])
  useEffect(() => { if (initSuggestions) setSuggestions(initSuggestions) }, [initSuggestions])
  if (suggestions.length === 0) return null
  return (
    <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
      {suggestions.map((s, i) => (
        <button key={i} onClick={() => onSelect(s)} style={{ padding: '0.35rem 0.85rem', background: theme.accent + '18', color: theme.accent, border: `1px solid ${theme.accent}30`, borderRadius: '999px', fontSize: '0.8rem', cursor: 'pointer' }}>
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
  const thinkMatch = raw.match(/<think>[\s\S]*?<\/think>/)
  const displayContent = thinkMatch
    ? raw.replace(/<think>[\s\S]*?<\/think>/, '').trim()
    : raw
  const isEmpty = msg.content === ''

  return (
    <motion.div initial={{ opacity: 0, y: 12, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }}
      style={{ display: 'flex', flexDirection: isUser ? 'row-reverse' : 'row', alignItems: 'flex-start', gap: '0.75rem' }}>
      <div style={{ width: 36, height: 36, borderRadius: '50%', flexShrink: 0, background: isUser ? theme.accent : '#10B981', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '1rem' }}>
        {isUser ? '😊' : '🤖'}
      </div>
      <div style={{ maxWidth: '72%' }}>
        {thinkMatch && !isEmpty && (
          <div style={{ fontSize: '0.75rem', color: theme.textMuted, marginBottom: '0.25rem', display: 'flex', alignItems: 'center', gap: '0.25rem', cursor: 'pointer', userSelect: 'none' }} onClick={() => setShowThink(v => !v)}>
            <ChevronDown size={14} style={{ transform: showThink ? 'rotate(0deg)' : 'rotate(-90deg)', transition: 'transform 0.2s', opacity: 0.7 }} />
            <span style={{ opacity: 0.7 }}>💭 思考过程</span>
          </div>
        )}
        {thinkMatch && showThink && (
          <div style={{ fontSize: '0.75rem', color: theme.textMuted, background: theme.surface, border: '1px solid ' + theme.border, borderRadius: '0.5rem', padding: '0.5rem 0.75rem', marginBottom: '0.375rem', fontFamily: 'monospace', whiteSpace: 'pre-wrap', maxHeight: 200, overflowY: 'auto', lineHeight: 1.5 }}>
            {String(thinkMatch[0]).replace(/<think>\s*/, '').replace(/<\/think>/, '').trim()}
          </div>
        )}
        <div style={{ padding: '0.875rem 1.125rem', borderRadius: isUser ? '1rem 1rem 0.25rem 1rem' : '1rem 1rem 1rem 0.25rem', background: isUser ? theme.userBubble : theme.assistantBubble, color: isUser ? theme.userText : theme.assistantText, boxShadow: '0 1px 4px rgba(0,0,0,0.08)', fontSize: '0.9375rem', lineHeight: 1.6 }}>
          {isEmpty
            ? <span style={{ opacity: 0.4, fontStyle: 'italic' }}>思考中...</span>
            : displayContent ? displayContent : null}
        </div>
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
  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} style={{ display: 'flex', gap: '0.75rem', alignItems: 'flex-start' }}>
      <div style={{ width: 36, height: 36, borderRadius: '50%', background: '#10B981', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '1rem' }}>🤖</div>
      <div style={{ padding: '0.875rem 1.125rem', borderRadius: '1rem 1rem 1rem 0.25rem', background: '#F1EEFF', display: 'flex', gap: '0.35rem', alignItems: 'center', minWidth: '3.5rem' }}>
        {[0, 1, 2].map(i => <motion.div key={i} style={{ width: 8, height: 8, borderRadius: '50%', background: '#8B5CF6' }} animate={{ y: [0, -4, 0] }} transition={{ duration: 0.6, repeat: Infinity, delay: i * 0.15 }} />)}
      </div>
    </motion.div>
  )
}

function EmptyState() {
  const { theme } = useTheme()
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '1rem', padding: '3rem 1rem', color: theme.textMuted }}>
      <div style={{ fontSize: '3rem' }}>🌿</div>
      <div style={{ fontSize: '1.1rem', fontWeight: 500, color: theme.text }}>在这里说出你的心情</div>
      <div style={{ fontSize: '0.875rem', textAlign: 'center', maxWidth: '22rem' }}>我会用心倾听，陪你梳理情绪、探索想法</div>
    </div>
  )
}

// ===================== Skill Manager Panel =====================
function SkillManager({ onClose }: { onClose: () => void }) {
  const { theme } = useTheme()
  const [activeTab, setActiveTab] = useState<'tools' | 'add'>('tools')
  const [tools, setTools] = useState<Tool[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [addCode, setAddCode] = useState('')
  const [addName, setAddName] = useState('')
  const [addDesc, setAddDesc] = useState('')
  const [addResult, setAddResult] = useState<{ ok: boolean; msg: string } | null>(null)
  const [testing, setTesting] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<string>('')
  const [search, setSearch] = useState('')

  useEffect(() => { loadTools() }, [])

  async function loadTools() {
    setLoading(true)
    try {
      const res = await fetch(`${import.meta.env.VITE_GATEWAY_URL}/evolution/status`)
      const data: EvolutionStatus = await res.json()
      setTools(data.tools as Tool[])
    } catch (e) {
      setError('加载失败: ' + String(e))
    } finally {
      setLoading(false)
    }
  }

  async function toggleTool(id: string, enabled: boolean) {
    try {
      await fetch(`${import.meta.env.VITE_GATEWAY_URL}/tools/${id}`, {
        method: enabled ? 'POST' : 'DELETE',
        headers: { 'Content-Type': 'application/json' },
      })
      setTools(prev => prev.map(t => t.id === id ? { ...t, enabled } : t))
    } catch (e) { setError('操作失败: ' + String(e)) }
  }

  async function testTool(tool: Tool) {
    setTesting(tool.id)
    setTestResult('')
    try {
      const params: Record<string, string> = {}
      if (tool.id === 'web-search') params.query = '北京天气'
      const res = await fetch(`${import.meta.env.VITE_GATEWAY_URL}/tools/${tool.id}/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ params }),
      })
      const data = await res.json()
      setTestResult(data.result ? String(data.result).slice(0, 300) : data.error || '无响应')
    } catch (e) { setTestResult('测试失败: ' + String(e)) }
    finally { setTesting(null) }
  }

  async function handleAdd() {
    if (!addName.trim() || !addCode.trim()) { setAddResult({ ok: false, msg: '名称和代码不能为空' }); return }
    try {
      const res = await fetch(`${import.meta.env.VITE_GATEWAY_URL}/tools`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: addName.toLowerCase().replace(/\s+/g, '-'), name: addName, display_name: addName, description: addDesc || addName, code: addCode, category: 'custom', icon: '🛠️' }),
      })
      const data = await res.json()
      if (res.ok || data.tool_id) { setAddResult({ ok: true, msg: `工具 ${addName} 添加成功！` }); setAddCode(''); setAddName(''); setAddDesc(''); loadTools() }
      else setAddResult({ ok: false, msg: data.detail || '添加失败' })
    } catch (e) { setAddResult({ ok: false, msg: String(e) }) }
  }

  const filtered = tools.filter(t => !search || t.display_name.includes(search) || t.id.includes(search) || t.category.includes(search))
  const categories = [...new Set(tools.map(t => t.category))]

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} style={{ position: 'fixed', inset: 0, background: theme.overlay, zIndex: 200, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '1rem' }}>
      <motion.div initial={{ scale: 0.92, y: 20 }} animate={{ scale: 1, y: 0 }} style={{ background: theme.bg, borderRadius: '1.25rem', width: 'min(720px, 100%)', maxHeight: '85vh', display: 'flex', flexDirection: 'column', overflow: 'hidden', boxShadow: '0 20px 60px rgba(0,0,0,0.3)' }}>
        {/* Header */}
        <div style={{ padding: '1.25rem 1.5rem', borderBottom: `1px solid ${theme.border}`, display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <Wrench size={20} color={theme.accent} />
          <h2 style={{ flex: 1, fontSize: '1rem', fontWeight: 600, color: theme.text }}>能力中心</h2>
          <button onClick={loadTools} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '0.25rem' }}><RefreshCw size={18} color={theme.textMuted} /></button>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '0.25rem' }}><X size={20} color={theme.textMuted} /></button>
        </div>

        {/* Tabs */}
        <div style={{ display: 'flex', borderBottom: `1px solid ${theme.border}`, padding: '0 1.5rem' }}>
          {[['tools', '工具列表', tools.length], ['add', '添加工具', null]].map(([tab, label, badge]) => (
            <button key={tab} onClick={() => setActiveTab(tab as any)} style={{ padding: '0.75rem 1rem', background: 'none', border: 'none', borderBottom: activeTab === tab ? `2px solid ${theme.accent}` : '2px solid transparent', color: activeTab === tab ? theme.accent : theme.textMuted, fontSize: '0.875rem', fontWeight: 500, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              {label} {badge !== null ? `(${badge})` : ''}
            </button>
          ))}
        </div>

        {/* Body */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '1.25rem 1.5rem' }}>
          {error && <div style={{ padding: '0.5rem 0.75rem', background: theme.errorBg, color: theme.errorColor, borderRadius: '0.5rem', fontSize: '0.8rem', marginBottom: '1rem' }}>⚠️ {error}</div>}

          {activeTab === 'tools' && (
            <>
              {/* Search */}
              <div style={{ position: 'relative', marginBottom: '1rem' }}>
                <Search size={16} style={{ position: 'absolute', left: '0.75rem', top: '50%', transform: 'translateY(-50%)', color: theme.textMuted }} />
                <input value={search} onChange={e => setSearch(e.target.value)} placeholder="搜索工具..." style={{ width: '100%', padding: '0.6rem 0.75rem 0.6rem 2.25rem', borderRadius: '0.75rem', border: `1px solid ${theme.border}`, background: theme.inputBg, color: theme.text, fontSize: '0.875rem', outline: 'none', boxSizing: 'border-box' }} />
              </div>

              {loading ? (
                <div style={{ textAlign: 'center', padding: '2rem', color: theme.textMuted }}>加载中...</div>
              ) : (
                <>
                  {categories.map(cat => {
                    const catTools = filtered.filter(t => t.category === cat)
                    if (catTools.length === 0) return null
                    return (
                      <div key={cat} style={{ marginBottom: '1.25rem' }}>
                        <div style={{ fontSize: '0.75rem', fontWeight: 600, color: theme.textMuted, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '0.5rem' }}>{cat}</div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                          {catTools.map(tool => (
                            <div key={tool.id} style={{ padding: '0.875rem 1rem', background: theme.surface, border: `1px solid ${theme.border}`, borderRadius: '0.875rem', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                              <div style={{ fontSize: '1.25rem', width: 36, height: 36, borderRadius: '0.5rem', background: theme.accent + '15', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                                {tool.icon || '🛠️'}
                              </div>
                              <div style={{ flex: 1, minWidth: 0 }}>
                                <div style={{ fontSize: '0.875rem', fontWeight: 500, color: theme.text }}>{tool.display_name || tool.name} <span style={{ fontSize: '0.7rem', color: theme.textMuted }}>({tool.id})</span></div>
                                <div style={{ fontSize: '0.75rem', color: theme.textMuted, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{tool.description}</div>
                              </div>
                              <div style={{ display: 'flex', gap: '0.5rem', flexShrink: 0 }}>
                                <button onClick={() => testTool(tool)} disabled={testing !== null} style={{ padding: '0.3rem 0.6rem', background: theme.accent + '15', color: theme.accent, border: 'none', borderRadius: '0.4rem', fontSize: '0.72rem', cursor: 'pointer' }}>
                                  {testing === tool.id ? '测试中...' : '测试'}
                                </button>
                                {tool.is_builtin ? (
                                  <span style={{ fontSize: '0.7rem', color: theme.textMuted, padding: '0.3rem 0.5rem' }}>内置</span>
                                ) : (
                                  <button onClick={() => toggleTool(tool.id, !tool.enabled)} style={{ padding: '0.3rem 0.6rem', background: tool.enabled ? theme.errorBg : '#DCFCE7', color: tool.enabled ? theme.errorColor : '#16A34A', border: 'none', borderRadius: '0.4rem', fontSize: '0.72rem', cursor: 'pointer' }}>
                                    {tool.enabled ? '禁用' : '启用'}
                                  </button>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )
                  })}
                  {filtered.length === 0 && <div style={{ textAlign: 'center', padding: '2rem', color: theme.textMuted }}>没有找到匹配的工具</div>}
                </>
              )}

              {/* Test result */}
              {testResult && (
                <div style={{ marginTop: '1rem', padding: '0.75rem', background: theme.surface, border: `1px solid ${theme.border}`, borderRadius: '0.75rem', fontSize: '0.8rem', color: theme.text }}>
                  <div style={{ fontWeight: 500, marginBottom: '0.35rem', color: theme.accent }}>测试结果：</div>
                  <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', margin: 0, fontFamily: 'monospace', fontSize: '0.75rem', color: theme.textMuted }}>{testResult}</pre>
                </div>
              )}
            </>
          )}

          {activeTab === 'add' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <div>
                <label style={{ fontSize: '0.8rem', fontWeight: 500, color: theme.text, display: 'block', marginBottom: '0.35rem' }}>工具 ID（英文，唯一标识）</label>
                <input value={addName} onChange={e => setAddName(e.target.value)} placeholder="如: my-weather" style={{ width: '100%', padding: '0.6rem 0.75rem', borderRadius: '0.75rem', border: `1px solid ${theme.border}`, background: theme.inputBg, color: theme.text, fontSize: '0.875rem', outline: 'none', boxSizing: 'border-box' }} />
              </div>
              <div>
                <label style={{ fontSize: '0.8rem', fontWeight: 500, color: theme.text, display: 'block', marginBottom: '0.35rem' }}>描述</label>
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <input value={addDesc} onChange={e => setAddDesc(e.target.value)} placeholder="这个工具做什么" style={{ flex: 1, padding: '0.6rem 0.75rem', borderRadius: '0.75rem', border: `1px solid ${theme.border}`, background: theme.inputBg, color: theme.text, fontSize: '0.875rem', outline: 'none', boxSizing: 'border-box' }} />
                  <button onClick={async () => {
                    if (!addDesc.trim()) { setAddResult({ ok: false, msg: '请先输入描述' }); return }
                    setAddResult({ ok: true, msg: 'AI 正在生成代码...' })
                    try {
                      const result = await generateToolCode(addDesc, addName)
                      setAddCode(result.code)
                      if (!addName.trim()) setAddName(result.name)
                      setAddResult({ ok: true, msg: '代码生成成功！请检查并修改' })
                    } catch (e) { setAddResult({ ok: false, msg: '生成失败: ' + String(e) }) }
                  }} style={{ padding: '0.6rem 1rem', background: theme.accent, color: 'white', border: 'none', borderRadius: '0.75rem', fontSize: '0.8rem', fontWeight: 500, cursor: 'pointer', whiteSpace: 'nowrap' }}>
                    <Zap size={14} style={{ display: 'inline', marginRight: '0.3rem' }} />AI 生成
                  </button>
                </div>
              </div>
              <div>
                <label style={{ fontSize: '0.8rem', fontWeight: 500, color: theme.text, display: 'block', marginBottom: '0.35rem' }}>工具代码（Python 函数）</label>
                <textarea value={addCode} onChange={e => setAddCode(e.target.value)} placeholder="Enter Python code: def my_tool(param): ..." rows={8} style={{ width: "100%", padding: "0.6rem 0.75rem", borderRadius: "0.75rem", border: `1px solid ${theme.border}`, background: theme.inputBg, color: theme.text, fontSize: "0.8rem", outline: "none", fontFamily: "monospace", resize: "vertical", boxSizing: "border-box" }} />
              </div>
              <button onClick={handleAdd} style={{ padding: '0.7rem', background: theme.accent, color: 'white', border: 'none', borderRadius: '0.75rem', fontSize: '0.875rem', fontWeight: 500, cursor: 'pointer' }}>
                <Zap size={16} style={{ display: 'inline', marginRight: '0.4rem' }} />添加工具
              </button>
              {addResult && (
                <div style={{ padding: '0.5rem 0.75rem', background: addResult.ok ? '#DCFCE7' : theme.errorBg, color: addResult.ok ? '#16A34A' : theme.errorColor, borderRadius: '0.5rem', fontSize: '0.8rem' }}>
                  {addResult.ok ? <Check size={14} style={{ display: 'inline', marginRight: '0.3rem' }} /> : <AlertCircle size={14} style={{ display: 'inline', marginRight: '0.3rem' }} />}{addResult.msg}
                </div>
              )}
              <div style={{ padding: '0.75rem', background: theme.surface, borderRadius: '0.75rem', fontSize: '0.75rem', color: theme.textMuted, lineHeight: 1.6 }}>
                💡 <strong>示例：天气查询</strong><br/>
                <pre style={{ fontFamily: 'monospace', fontSize: '0.72rem', marginTop: '0.5rem', whiteSpace: 'pre-wrap', color: theme.text }}>{`def weather(query: str) -> str:
    import urllib.request, json
    url = "https://api.tavily.com/search"
    payload = json.dumps({"query": query, "max_results": 3}).encode()
    req = urllib.request.Request(url, data=payload,
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + __import__("os").getenv("TAVILY_API_KEY", "")},
        method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:
        results = json.loads(resp.read()).get("results", [])
    return "\\n".join([f"{r['title']} - {r['url']}" for r in results[:3]])`}</pre>
              </div>
            </div>
          )}
        </div>
      </motion.div>
    </motion.div>
  )
}

// ===================== Main App =====================
export default function App() {
  const { theme, mode, toggleTheme } = useTheme()
  const [sessions, setSessions] = useState<Record<string, Session>>(() => loadSessions())
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null)
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [skillOpen, setSkillOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [CACHED_NICK, setCACHED_NICK] = useState('')
  const [suggestions, setSuggestions] = useState<string[]>([])
  const messagesEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    getNickname().then(nick => { if (nick) setCACHED_NICK(nick) })
    getSuggestions('neutral').then(s => { if (s?.length) setSuggestions(s) })
  }, [])

  useEffect(() => { getSuggestions('neutral').then(s => { if (s?.length) setSuggestions(s) }) }, [])

  const currentSession = currentSessionId ? sessions[currentSessionId] : null
  const messages = currentSession?.messages ?? []
  const trendData = useEmotionTrend(messages)

  useEffect(() => { if (Object.keys(sessions).length > 0) saveSessions(sessions) }, [sessions])
  useEffect(() => { messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  const handleStop = useCallback(() => { abortRef.current?.abort() }, [])

  const handleSend = useCallback(async () => {
    if (streaming || !input.trim()) return
    const controller = new AbortController()
    abortRef.current = controller
    const text = input.trim()
    setInput('')
    setError(null)

    let sessionId = currentSessionId
    if (!sessionId) {
      sessionId = Date.now().toString(36) + Math.random().toString(36).slice(2)
      setCurrentSessionId(sessionId)
      setSessions(prev => ({ ...prev, [sessionId!]: { id: sessionId!, title: text.slice(0, 20), messages: [], createdAt: Date.now() } }))
    }

    const { emotion, prob } = detectEmotion(text)
    const userMsg: Message = { id: Date.now().toString(36) + Math.random().toString(36).slice(2), role: 'user', content: text, emotion, emotionProb: prob, timestamp: Date.now() }
    setSessions(prev => ({ ...prev, [sessionId!]: { ...prev[sessionId!], messages: [...prev[sessionId!].messages, userMsg] } }))

    const assistantId = Date.now().toString(36) + Math.random().toString(36).slice(2)
    const assistantMsg: Message = { id: assistantId, role: 'assistant', content: '', emotion, emotionProb: prob, timestamp: Date.now() }
    setSessions(prev => ({ ...prev, [sessionId!]: { ...prev[sessionId!], messages: [...prev[sessionId!].messages, assistantMsg] } }))

    setStreaming(true)
    const appendToken = (token: string) => setSessions(prev => ({ ...prev, [sessionId!]: { ...prev[sessionId!], messages: prev[sessionId!].messages.map(m => m.id === assistantId ? { ...m, content: m.content + token } : m) } }))
    const finishStream = (result: { emotion?: string; advice?: string }) => setSessions(prev => ({ ...prev, [sessionId!]: { ...prev[sessionId!], messages: prev[sessionId!].messages.map(m => m.id === assistantId ? { ...m, emotion: result.emotion || emotion, advice: result.advice } : m) } }))
    const streamError = (errMsg: string | Error) => {
      setError(String(errMsg))
      const fallback = EMOTION_CONFIG[emotion]?.advice || '我在这里，愿意听你说。'
      setSessions(prev => ({ ...prev, [sessionId!]: { ...prev[sessionId!], messages: prev[sessionId!].messages.map(m => m.id === assistantId ? { ...m, content: fallback } : m) } }))
      setStreaming(false)
    }
    const savedMessages = sessions[sessionId!]?.messages ?? []
    await apiChatStream(sessionId!, text, emotion, prob, savedMessages, appendToken, finishStream, streamError, abortRef.current?.signal)
    setStreaming(false)
  }, [input, streaming, currentSessionId, sessions])

  const currentEmotion = messages.length > 0 ? (messages[messages.length - 1].emotion || 'neutral') : 'neutral'

  return (
    <div className="app" style={{ background: theme.bg }}>
      <AnimatePresence>
        {sidebarOpen && <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setSidebarOpen(false)} style={{ position: 'fixed', inset: 0, background: theme.overlay, zIndex: 99 }} />}
      </AnimatePresence>

      {/* Sidebar */}
      <motion.aside initial={{ x: -280 }} animate={{ x: sidebarOpen ? 0 : -280 }} transition={{ type: 'spring', stiffness: 300, damping: 30 }}
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
        <header style={{ padding: '1rem 1.5rem', borderBottom: `1px solid ${theme.border}`, display: 'flex', alignItems: 'center', gap: '0.75rem', background: theme.headerBg }}>
          <button onClick={() => setSidebarOpen(true)} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '0.25rem' }}><Menu size={24} color={theme.text} /></button>
          <div style={{ flex: 1 }}>
            <h1 style={{ fontSize: '1rem', fontWeight: 600, color: theme.text }}>情感对话</h1>
            <EmotionBadge emotion={currentEmotion} prob={0.8} size="sm" />
          </div>
          {/* 能力中心按钮 */}
          <button onClick={() => setSkillOpen(true)} title="能力中心" style={{ background: theme.accent + '15', border: 'none', borderRadius: '0.6rem', padding: '0.4rem 0.75rem', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '0.4rem', color: theme.accent, fontSize: '0.8rem', fontWeight: 500 }}>
            <Zap size={16} />能力
          </button>
          <button onClick={toggleTheme} title={`主题: ${mode === 'auto' ? '跟随系统' : mode === 'dark' ? '深色' : '浅色'}`} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '0.25rem', display: 'flex', alignItems: 'center', color: theme.textMuted }}>
            <ThemeIcon mode={mode} />
          </button>
          {currentSessionId && (
            <button onClick={() => { const updated = { ...sessions }; delete updated[currentSessionId]; setSessions(updated); setCurrentSessionId(null) }} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '0.25rem' }} title="清空对话">
              <Trash2 size={20} color={theme.textMuted} />
            </button>
          )}
          <button onClick={() => { const nick = window.prompt('设置昵称（留空清除）', CACHED_NICK || ''); if (nick !== null) { setNickname(nick).then(() => { setCACHED_NICK(nick || '') }) } }} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '0.25rem', fontSize: '0.8rem', color: theme.textMuted, borderRadius: '0.5rem' }}>
            {CACHED_NICK || '设置昵称'}
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
          {!streaming && messages.length > 0 && <SuggestionChips onSelect={text => { setInput(text) }} suggestions={suggestions} />}
          {error && <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} style={{ textAlign: 'center', padding: '0.5rem', color: theme.errorColor, fontSize: '0.875rem' }}>⚠️ {error}</motion.div>}
          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <div style={{ padding: '1rem 1.5rem', borderTop: `1px solid ${theme.border}`, background: theme.headerBg }}>
          {error && <div style={{ fontSize: '0.75rem', color: theme.errorColor, marginBottom: '0.5rem' }}>⚠️ {error}</div>}
          <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'flex-end' }}>
            <textarea value={input} onChange={e => setInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() } }}
              placeholder="说出你的心情..." rows={1}
              style={{ flex: 1, padding: '0.75rem 1rem', borderRadius: '1.25rem', border: `1.5px solid ${theme.border}`, fontSize: '0.9375rem', resize: 'none', outline: 'none', fontFamily: 'inherit', lineHeight: 1.5, maxHeight: '8rem', overflowY: 'auto', background: theme.inputBg, color: theme.text, boxSizing: 'border-box' }} />
            {streaming ? (
              <motion.button onClick={handleStop} whileTap={{ scale: 0.95 }} style={{ width: 48, height: 48, borderRadius: '50%', background: theme.errorBg || '#FEE2E2', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Square size={18} color={theme.errorColor || '#DC2626'} />
              </motion.button>
            ) : (
              <motion.button onClick={handleSend} disabled={!input.trim()} whileTap={{ scale: 0.95 }} style={{ width: 48, height: 48, borderRadius: '50%', background: input.trim() ? theme.accent : theme.border, border: 'none', cursor: input.trim() ? 'pointer' : 'not-allowed', display: 'flex', alignItems: 'center', justifyContent: 'center', transition: 'background 0.2s' }}>
                <Send size={20} color="white" />
              </motion.button>
            )}
          </div>
          <p style={{ fontSize: '0.75rem', color: theme.textMuted, textAlign: 'center', marginTop: '0.5rem' }}>按 Enter 发送 · Shift+Enter 换行</p>
        </div>
      </div>

      {/* Skill Manager Modal */}
      <AnimatePresence>
        {skillOpen && <SkillManager onClose={() => setSkillOpen(false)} />}
      </AnimatePresence>

      <style>{`
        @keyframes bounce { 0%, 80%, 100% { transform: translateY(0); } 40% { transform: translateY(-6px); } }
        .app { display: flex; height: 100vh; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
        .main { flex: 1; display: flex; flex-direction: column; min-width: 0; }
        textarea:focus { border-color: #8B5CF6 !important; }
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: rgba(128,128,128,0.3); border-radius: 3px; }
      `}</style>
    </div>
  )
}
