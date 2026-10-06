import { useEffect, useState } from 'react'
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
            <ol className="rank-row">
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
            </ol>
          )}
        </div>
      ))}
    </section>
  )
}
