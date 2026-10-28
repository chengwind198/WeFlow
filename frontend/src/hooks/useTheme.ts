import { useTheme as useNextTheme } from 'next-themes'

/**
 * 封装 next-themes 的 useTheme，提供类型安全的主题操作。
 */
export function useTheme() {
  const { theme, setTheme, systemTheme, resolvedTheme } = useNextTheme()

  const isDark = resolvedTheme === 'dark'
  const isLight = resolvedTheme === 'light'

  const toggle = () => {
    setTheme(isDark ? 'light' : 'dark')
  }

  return {
    theme,        // 当前设置的主题（可能为 'system'）
    setTheme,
    systemTheme,  // 系统主题
    resolvedTheme,// 实际生效的主题
    isDark,
    isLight,
    toggle,
  } as const
}
