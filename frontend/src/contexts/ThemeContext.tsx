import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

export type ThemeMode = 'light' | 'dark'
export type ThemePreference = ThemeMode | 'system'

interface ThemeContextValue {
  mode: ThemePreference
  theme: ThemeMode
  setMode: (mode: ThemePreference) => void
  setTheme: (theme: ThemePreference) => void
  toggleTheme: () => void
}

const THEME_STORAGE_KEY = 'talk-training-studio.theme'
const ThemeContext = createContext<ThemeContextValue | null>(null)

function isThemePreference(value: unknown): value is ThemePreference {
  return value === 'light' || value === 'dark' || value === 'system'
}

function getSystemTheme(): ThemeMode {
  if (typeof window === 'undefined') return 'light'
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function getPreferredTheme(): ThemePreference {
  if (typeof window === 'undefined') return 'light'

  try {
    const storedTheme = window.localStorage.getItem(THEME_STORAGE_KEY)
    if (isThemePreference(storedTheme)) return storedTheme
  } catch {
    return 'system'
  }

  return 'system'
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<ThemePreference>(getPreferredTheme)
  const [systemTheme, setSystemTheme] = useState<ThemeMode>(getSystemTheme)
  const theme = mode === 'system' ? systemTheme : mode

  const setMode = useCallback((nextMode: ThemePreference) => {
    setModeState(nextMode)
  }, [])

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    document.documentElement.dataset.themeMode = mode
    document.documentElement.style.colorScheme = theme
  }, [mode, theme])

  useEffect(() => {
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, mode)
    } catch {
      // Theme persistence is optional; the current session still updates.
    }
  }, [mode])

  useEffect(() => {
    if (typeof window === 'undefined') return undefined

    const mediaQuery = window.matchMedia?.('(prefers-color-scheme: dark)')
    if (!mediaQuery) return undefined

    const updateSystemTheme = (event: MediaQueryListEvent) => {
      setSystemTheme(event.matches ? 'dark' : 'light')
    }

    setSystemTheme(mediaQuery.matches ? 'dark' : 'light')
    mediaQuery.addEventListener('change', updateSystemTheme)
    return () => mediaQuery.removeEventListener('change', updateSystemTheme)
  }, [])

  const value = useMemo<ThemeContextValue>(
    () => ({
      mode,
      theme,
      setMode,
      setTheme: setMode,
      toggleTheme: () => setMode(theme === 'dark' ? 'light' : 'dark'),
    }),
    [mode, setMode, theme],
  )

  return (
    <ThemeContext.Provider value={value}>
      {children}
    </ThemeContext.Provider>
  )
}

export function useTheme() {
  const value = useContext(ThemeContext)
  if (!value) {
    throw new Error('useTheme must be used inside ThemeProvider')
  }
  return value
}
