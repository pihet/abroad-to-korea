// 다크·라이트 전환. 처음 값은 index.html 의 작은 스크립트가 <html data-theme> 에 넣어 둔다
import { useEffect, useState } from 'react'

export type Theme = 'light' | 'dark'
const root = document.documentElement
const system = matchMedia('(prefers-color-scheme: dark)')
const saved = () => { try { return localStorage.getItem('theme') } catch { return null } }

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(root.dataset.theme === 'dark' ? 'dark' : 'light')
  useEffect(() => { root.dataset.theme = theme }, [theme])
  // 직접 고른 적이 없으면 기기 설정이 바뀔 때 따라간다
  useEffect(() => {
    const follow = (e: MediaQueryListEvent) => { if (!saved()) setTheme(e.matches ? 'dark' : 'light') }
    system.addEventListener('change', follow)
    return () => system.removeEventListener('change', follow)
  }, [])
  const toggle = () => {
    const next: Theme = theme === 'dark' ? 'light' : 'dark'
    try { localStorage.setItem('theme', next) } catch { /* 저장이 막혀도 이번 화면에서는 바뀐다 */ }
    setTheme(next)
  }
  return { theme, toggle }
}
