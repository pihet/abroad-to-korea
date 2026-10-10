import { useEffect, useState } from 'react'
import { ORIGINS, type AuthUser, type Origin, type RegionRow } from './api'
import './my.css'

// MY 탭: 프로필 · 내 취향 상태와 설정(개인 맞춤 켜기·끄기, 기본 출발지) · 저장한 곳 · 저장한 곳의 축제 · 내가 누른 반응.
// 저장은 비로그인이면 이 기기에만, 로그인하면 서버에도 남는다 (FeedApp 의 saved). 나머지는 로그인 사용자만.

type Taste = { logged_in: boolean; on: boolean; enabled: boolean; origin: Origin | null
  likes: number; dislikes: number; saved: number; min_signals: number }
type Vote = { attraction_id: string; value: 1 | -1; name: string | null; image_url: string | null; region: { key: string; name: string } }
type Fest = { id: string; name: string; start: string; end: string; region: { key: string; name: string; sido: string } }

const md = (iso: string) => `${+iso.slice(5, 7)}/${+iso.slice(8, 10)}`
const getJson = <T,>(url: string): Promise<T | null> => fetch(url).then(r => r.ok ? r.json() : null).catch(() => null)

export function FeedMy({ user, rows, saved, onAccount, onOpen, onOrigin }: {
  user: AuthUser | null; rows: RegionRow[]; saved: string[]
  onAccount: () => void; onOpen: (key: string) => void; onOrigin: (o: Origin | null) => void
}) {
  const [taste, setTaste] = useState<Taste | null>(null)
  const [votes, setVotes] = useState<Vote[]>([])
  const [fests, setFests] = useState<Fest[]>([])
  const [err, setErr] = useState<string | null>(null)
  const loadTaste = () => getJson<Taste>('/api/my/taste').then(setTaste)
  // 하트를 누르거나 로그인 상태가 바뀌면 다시 센다
  useEffect(() => { loadTaste() }, [user, saved.length])
  useEffect(() => {
    if (!user) { setVotes([]); setFests([]); return }
    getJson<{ votes: Vote[] }>('/api/my/votes').then(d => setVotes(d?.votes ?? []))
    getJson<{ items: Fest[] }>('/api/my/festivals').then(d => setFests(d?.items ?? []))
  }, [user, saved.length])

  const save = async (personal: boolean, origin: Origin | null) => {
    setErr(null)
    const r = await fetch('/api/my/settings', { method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ personal, origin }) }).catch(() => null)
    if (!r?.ok) { setErr('설정을 저장하지 못했어요. 잠시 뒤 다시 해 주세요.'); return }
    onOrigin(origin)
    loadTaste()
  }
  const unvote = async (id: string) => {
    const r = await fetch(`/api/my/votes/${encodeURIComponent(id)}`, { method: 'DELETE' }).catch(() => null)
    if (!r?.ok && r?.status !== 404) { setErr('취소하지 못했어요. 잠시 뒤 다시 해 주세요.'); return }
    setVotes(votes.filter(v => v.attraction_id !== id))
    loadTaste()
  }

  const mine = rows.filter(r => saved.includes(r.key))
  const n = taste ? taste.likes + taste.dislikes + taste.saved : 0
  return (
    <div className="my">
      <section className="my-profile">
        <span className="my-av">{user ? user.nickname.slice(0, 1) : '?'}</span>
        <div>
          <b>{user ? user.nickname : '로그인하지 않았어요'}</b>
          <small>{user ? user.email : '저장한 곳은 이 기기에만 남아요'}</small>
        </div>
        <button type="button" onClick={onAccount}>{user ? '계정 설정' : '로그인'}</button>
      </section>

      <section className="my-taste" aria-live="polite">
        {!user && <p>로그인하면 저장한 곳이 다른 기기에서도 보이고, <b>내 취향이 추천 순서에 반영돼요.</b></p>}
        {user && taste && !taste.enabled && <p><b>내 취향 반영 꺼짐</b> · 사진으로 찾기 결과가 사진 닮은 순서 그대로 나와요</p>}
        {user && taste?.on && <p><b>내 취향 반영 중</b> · 닮았어요·별로예요·저장 {n}개로 사진으로 찾기 결과 순서를 조금 바꿔요</p>}
        {user && taste?.enabled && !taste.on && <p><b>{Math.max(taste.min_signals - n, 1)}개 더</b> 누르면 내 취향이 추천에 반영돼요 <small>(닮았어요·별로예요·하트)</small></p>}
      </section>

      {user && taste && <section className="my-set">
        <div>
          <span>내 취향 반영</span>
          <button type="button" role="switch" aria-checked={taste.enabled} className="my-switch"
            onClick={() => save(!taste.enabled, taste.origin)}><i /></button>
        </div>
        <div>
          <span>기본 출발지 <small>{taste.origin ? `저장됨 · 사진으로 찾기 결과에 '${taste.origin}에서 ○km'` : '고르면 사진으로 찾기 결과에 거리 표시'}</small></span>
          <span className="my-chips">
            {[null, ...ORIGINS].map(o => <button key={o ?? 'none'} type="button" aria-pressed={taste.origin === o}
              onClick={() => save(taste.enabled, o)}>{o ?? '없음'}</button>)}
          </span>
        </div>
        {err && <p className="my-err">{err}</p>}
      </section>}

      <h2 className="my-h">저장한 곳 <small>{mine.length}</small></h2>
      {mine.length === 0 ? <p className="ig-wait">하트를 누른 곳이 여기에 모여요.</p> : (
        <div className="ig-grid">
          {mine.map(r => (
            <button key={r.key} type="button" onClick={() => onOpen(r.key)} aria-label={`${r.sido} ${r.name}`}>
              <img src={r.photo!.image_url} alt={r.photo!.name} loading="lazy" />
            </button>
          ))}
        </div>
      )}

      {user && mine.length > 0 && <>
        <h2 className="my-h">저장한 곳의 축제 <small>{fests.length}</small></h2>
        {fests.length === 0 ? <p className="ig-wait">앞으로 한 달 안에 저장한 곳에서 열리는 축제가 없어요.</p> : (
          <ul className="my-list">
            {fests.map(f => <li key={f.id}>
              <button type="button" onClick={() => onOpen(f.region.key)}>
                <span className="my-date">{md(f.start)}{f.end !== f.start ? `~${md(f.end)}` : ''}</span>
                <span><b>{f.name}</b><small>{f.region.name}</small></span>
              </button>
            </li>)}
          </ul>
        )}
      </>}

      {user && <>
        <h2 className="my-h">내가 누른 반응 <small>{votes.length}</small></h2>
        {votes.length === 0 ? <p className="ig-wait">사진으로 찾기 결과에서 닮았어요·별로예요를 누르면 여기에 모여요.</p> : (
          <ul className="my-list">
            {votes.map(v => <li key={v.attraction_id}>
              <button type="button" onClick={() => onOpen(v.region.key)}>
                {v.image_url && <img src={v.image_url} alt={v.name ?? ''} loading="lazy" />}
                <span><b>{v.name ?? '지금은 없는 관광지'}</b>
                  <small><em className={v.value === 1 ? 'up' : 'down'}>{v.value === 1 ? '닮았어요' : '별로예요'}</em> · {v.region.name}</small></span>
              </button>
              <button type="button" className="my-undo" onClick={() => unvote(v.attraction_id)}>취소</button>
            </li>)}
          </ul>
        )}
      </>}
    </div>
  )
}
