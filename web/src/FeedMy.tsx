import { useEffect, useState } from 'react'
import type { AuthUser, RegionRow } from './api'
import './my.css'

// MY 탭: 프로필 · 내 취향 상태(개인 맞춤이 켜졌는지) · 저장한 곳.
// 저장은 비로그인이면 이 기기에만, 로그인하면 서버에도 남는다 (FeedApp 의 saved).

type Taste = { logged_in: boolean; on: boolean; likes: number; dislikes: number; saved: number; min_signals: number }

export function FeedMy({ user, rows, saved, onAccount, onOpen }: {
  user: AuthUser | null; rows: RegionRow[]; saved: string[]
  onAccount: () => void; onOpen: (key: string) => void
}) {
  const [taste, setTaste] = useState<Taste | null>(null)
  // 하트를 누르거나 로그인 상태가 바뀌면 다시 센다
  useEffect(() => {
    fetch('/api/my/taste').then(r => r.ok ? r.json() : null).then(setTaste).catch(() => setTaste(null))
  }, [user, saved.length])

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
        {user && taste?.on && <p><b>내 취향 반영 중</b> · 닮았어요·별로예요·저장 {n}개로 사진으로 찾기 결과 순서를 조금 바꿔요</p>}
        {user && taste && !taste.on && <p><b>{Math.max(taste.min_signals - n, 1)}개 더</b> 누르면 내 취향이 추천에 반영돼요 <small>(닮았어요·별로예요·하트)</small></p>}
      </section>

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
    </div>
  )
}
