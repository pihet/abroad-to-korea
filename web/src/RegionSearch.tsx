import { useEffect, useMemo, useRef, useState } from 'react'
import type { RegionRow } from './api'

// 시군구 검색 (인스타그램 검색 화면형). 이름·시도로 찾고("강원 양양"처럼 여러 낱말도), 초성만 쳐도 찾는다("ㅇㅇ" → 양양군).
// 검색어가 없으면 최근 본 지역과 시도 목록을 보여 준다. 결과를 누르면 지역 상세를 연다.

const CHO = 'ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ'
const choseong = (s: string) => [...s].map(ch => {
  const c = ch.charCodeAt(0) - 0xac00
  return c >= 0 && c < 11172 ? CHO[Math.floor(c / 588)] : ch
}).join('')
const isCho = (s: string) => [...s].every(ch => CHO.includes(ch))
const norm = (s: string) => s.replace(/\s+/g, '').toLowerCase()

// 낱말 하나가 이 지역에 맞는지 (점수가 클수록 앞)
// 시도는 정식 이름과 줄임말 둘 다 본다 ('충북'은 '충청북도' 안에 그대로 들어 있지 않다)
function score(r: RegionRow, word: string, short: string): number {
  const name = norm(r.name), sido = norm(r.sido) + ' ' + norm(short)
  if (isCho(word)) return choseong(name).startsWith(word) ? 3 : choseong(name).includes(word) ? 2 : choseong(sido).startsWith(word) ? 1 : 0
  if (name.startsWith(word)) return 4
  if (name.includes(word)) return 3
  if (sido.startsWith(word) || sido.includes(word)) return 1
  return 0
}

const RECENT_KEY = 'feed-recent-regions'
const loadRecent = (): string[] => { try { return JSON.parse(localStorage.getItem(RECENT_KEY) || '[]') } catch { return [] } }

export function RegionSearch({ rows, shortSido, onPick, onClose }: {
  rows: RegionRow[]; shortSido: (s: string) => string; onPick: (key: string) => void; onClose: () => void
}) {
  const [q, setQ] = useState('')
  const [recent, setRecent] = useState<string[]>(loadRecent)
  const input = useRef<HTMLInputElement>(null)
  useEffect(() => { input.current?.focus() }, [])
  useEffect(() => {
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', esc)
    return () => window.removeEventListener('keydown', esc)
  }, [onClose])

  const hits = useMemo(() => {
    const words = q.trim().toLowerCase().split(/\s+/).filter(Boolean)
    if (!words.length) return []
    return rows.map(r => {
      const s = words.map(w => score(r, w, shortSido(r.sido)))
      return { r, s: s.every(x => x > 0) ? s.reduce((a, b) => a + b, 0) : 0 }
    }).filter(x => x.s > 0).sort((a, b) => b.s - a.s || a.r.name.localeCompare(b.r.name, 'ko')).slice(0, 40).map(x => x.r)
  }, [q, rows, shortSido])
  const sidos = useMemo(() => [...new Set(rows.map(r => r.sido))].sort((a, b) => a.localeCompare(b, 'ko')), [rows])
  const byKey = useMemo(() => new Map(rows.map(r => [r.key, r])), [rows])

  const pick = (key: string) => {
    const next = [key, ...recent.filter(k => k !== key)].slice(0, 10)
    setRecent(next)
    try { localStorage.setItem(RECENT_KEY, JSON.stringify(next)) } catch { /* 저장소 없음 */ }
    onPick(key)
  }
  const clearRecent = () => { setRecent([]); try { localStorage.removeItem(RECENT_KEY) } catch { /* 저장소 없음 */ } }

  const Row = ({ r }: { r: RegionRow }) => (
    <li><button type="button" onClick={() => pick(r.key)}>
      <span className="av">{r.photo && r.photo.license.includes('제1유형') ? <img src={r.photo.image_url} alt="" /> : <i>{r.name.slice(0, 1)}</i>}</span>
      <span className="tx"><b>{r.name}</b><small>{r.sido}{r.flags.sea ? ' · 바다' : ''}{r.mountain_n > 0 ? ' · 산·숲' : ''} · {r.flags.city ? '도시' : '시골·소도시'}</small></span>
    </button></li>
  )

  return (
    <div className="igs" role="dialog" aria-modal="true" aria-label="지역 검색">
      <div className="igs-col">
        <header className="igs-top">
          <button type="button" onClick={onClose} aria-label="닫기"><svg viewBox="0 0 24 24" className="ic" aria-hidden="true"><path d="M15 5l-7 7 7 7" /></svg></button>
          <div className="igs-box">
            <svg viewBox="0 0 24 24" className="ic" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="m20 20-4-4" /></svg>
            <input ref={input} value={q} onChange={e => setQ(e.target.value)} placeholder="시군구 검색 (양양, 강원 고성, ㅈㅈ…)" aria-label="시군구 검색"
                   onKeyDown={e => { if (e.key === 'Enter' && hits[0]) pick(hits[0].key) }} />
            {q && <button type="button" className="clr" onClick={() => { setQ(''); input.current?.focus() }} aria-label="지우기">×</button>}
          </div>
        </header>

        {q.trim() ? (
          hits.length ? <ul className="igs-list">{hits.map(r => <Row key={r.key} r={r} />)}</ul>
            : <p className="ig-wait">"{q.trim()}"에 맞는 시군구가 없어요. 시군구 이름(예: 양양군)이나 시도(예: 강원)로 찾아 보세요.</p>
        ) : <>
          {recent.length > 0 && (
            <section className="igs-sec">
              <div className="igs-head"><b>최근 본 지역</b><button type="button" className="ig-link" onClick={clearRecent}>모두 지우기</button></div>
              <ul className="igs-list">{recent.map(k => byKey.get(k)).filter((r): r is RegionRow => !!r).map(r => <Row key={r.key} r={r} />)}</ul>
            </section>
          )}
          <section className="igs-sec">
            <div className="igs-head"><b>시도로 찾기</b></div>
            <div className="igs-chips">
              {sidos.map(s => <button key={s} type="button" onClick={() => setQ(shortSido(s))}>{shortSido(s)} <small>{rows.filter(r => r.sido === s).length}</small></button>)}
            </div>
          </section>
        </>}
      </div>
    </div>
  )
}
