import { useMemo } from 'react'
import { LIGHT_THEME, DARK_THEME, type Theme, type ThemeMode } from './types'

const THEME_KEY = 'empathic_theme'

export function useTheme() {
  const mode: ThemeMode = (localStorage.getItem(THEME_KEY) as ThemeMode) || 'auto'

  const theme: Theme = useMemo(() => {
    if (mode === 'dark') return DARK_THEME
    if (mode === 'light') return LIGHT_THEME
    // auto: respect system preference
    if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
      return DARK_THEME
    }
    return LIGHT_THEME
  }, [mode])

  const toggleTheme = () => {
    const next: ThemeMode = mode === 'light' ? 'dark' : mode === 'dark' ? 'auto' : 'light'
    localStorage.setItem(THEME_KEY, next)
    window.dispatchEvent(new CustomEvent('themechange'))
  }

  return { theme, mode, toggleTheme }
}
