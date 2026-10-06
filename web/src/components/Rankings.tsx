import { useEffect, useRef, useState } from 'react'
import { rankingsApi, type RankingList } from '../api'

// 둘러볼 만한 곳 목록: 목록마다 조건 하나 + 정렬 기준 하나 (기준 문구를 그대로 보여 준다).
export function Rankings({ onOpen }: { onOpen: (key: string) => void }) {
  const [lists, setLists] = useState<RankingList[] | null>(null)
  useEffect(() => { rankingsApi().then(setLists).catch(() => setLists([])) }, [])
  if (!lists) return <p className="fine">목록을 불러오는 중…</p>
  return (
    <section className="rankings">
      <h2>둘러볼 만한 곳</h2>
      {lists.map(l => (
        <div key={l.id} className="rank-list">
          <div className="rank-head"><h3>{l.title}</h3><small>{l.basis}</small></div>
          {l.items.length === 0 ? <p className="rank-empty">{l.empty ?? '조건에 맞는 곳이 없습니다.'}</p> : (
            <Row>
            
              {l.items.map((it, i) => (
                <li key={it.key}>
                  <button type="button" onClick={() => onOpen(it.key)}>
                    <span className="ph">{it.photo && <img src={it.photo.image_url} alt={it.photo.name} loading="lazy" />}<em>{i + 1}</em></span>
                    <b>{it.name}</b>
                    <small>{it.sido}</small>
                    <span className="val">{it.value.toLocaleString()}{it.unit && <i> {it.unit}</i>}</span>
                  </button>
                </li>
              ))}
            </Row>
          )}
        </div>
      ))}
    </section>
  )
}

// 가로로 넘기는 줄: 좌우 버튼으로 한 화면씩 이동 (터치·트랙패드로도 넘어간다)
function Row({ children }: { children: React.ReactNode }) {
  const ref = useRef<HTMLOListElement>(null)
  const go = (d: number) => ref.current?.scrollBy({ left: d * ref.current.clientWidth * 0.9, behavior: 'smooth' })
  return (
    <div className="rank-wrap">
      <button type="button" className="rank-nav prev" aria-label="이전" onClick={() => go(-1)}>‹</button>
      <ol className="rank-row" ref={ref}>{children}</ol>
      <button type="button" className="rank-nav next" aria-label="다음" onClick={() => go(1)}>›</button>
    </div>
  )
}
