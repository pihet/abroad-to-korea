import { useEffect, useState } from 'react'
import { dongFoodApi, type DongFood as DF } from '../api'

const PAGE = 12

// 동네를 누르면 그 동네 음식점: 대표사진(공공누리 1·3유형만) + 대표메뉴. 평점·맛 순위가 아니다.
export function DongFood({ regionKey, code, name }: { regionKey: string; code: string; name: string }) {
  const [d, setD] = useState<DF | null>(null)
  const [shown, setShown] = useState(PAGE)
  const [broken, setBroken] = useState<Set<string>>(new Set())
  useEffect(() => { setD(null); setShown(PAGE); dongFoodApi(regionKey, code).then(setD).catch(() => setD(null)) }, [regionKey, code])
  if (!d) return <p className="fine">음식점을 불러오는 중…</p>
  return (
    <div className="dong-food">
      <div className="df-head"><h4>{name} 음식점 {d.total}곳</h4><small>대표메뉴 확인 {d.with_menu}곳</small></div>
      {d.total === 0 ? <p className="rank-empty">이 동네에는 등록된 음식점이 없습니다.</p> : (
        <ul className="df-grid">
          {d.items.slice(0, shown).map(it => (
            <li key={it.id}>
              <div className="df-ph">
                {it.image_url && !broken.has(it.id)
                  ? <img src={it.image_url} alt={it.name} loading="lazy" onError={() => setBroken(new Set(broken).add(it.id))} />
                  : <span>사진 없음</span>}
              </div>
              <b>{it.name}</b>
              <p className={it.menu ? 'df-menu' : 'df-menu none'}>{it.menu ?? '대표메뉴 수집 전'}</p>
              <small>{it.kind}{it.address ? ` · ${it.address.split(' ').slice(2, 4).join(' ')}` : ''}</small>
            </li>
          ))}
        </ul>
      )}
      {shown < d.total && <button type="button" className="ghost wide" onClick={() => setShown(shown + PAGE)}>더 보기 ({shown} / {d.total})</button>}
      <p className="fine">{d.note} 사진: 한국관광공사 TourAPI · 공공누리 제1·3유형</p>
    </div>
  )
}
