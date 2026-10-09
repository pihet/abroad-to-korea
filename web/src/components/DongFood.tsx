import { useEffect, useState } from 'react'
import { dongFoodApi, type DongFood as DF } from '../api'
import { PhotoViewer } from './PhotoViewer'

const PAGE = 12

// 동네를 누르면 그 동네 음식점: 대표사진(공공누리 1·3유형만) + 대표메뉴. 평점·맛 순위가 아니다.
export function DongFood({ regionKey, code, name }: { regionKey: string; code: string; name: string }) {
  const [d, setD] = useState<DF | null>(null)
  const [shown, setShown] = useState(PAGE)
  const [broken, setBroken] = useState<Set<string>>(new Set())
  const [view, setView] = useState<DF['items'][number] | null>(null)
  useEffect(() => { setD(null); setShown(PAGE); dongFoodApi(regionKey, code).then(setD).catch(() => setD(null)) }, [regionKey, code])
  if (!d) return <p className="fine">음식점을 불러오는 중…</p>
  // 사진 칸에는 사진 있는 가게만. 사진 없는 가게는 아래 접힌 목록(이름·대표메뉴)으로, 지도 점에는 그대로 있다
  const withPhoto = d.items.filter(it => it.image_url && !broken.has(it.id))
  const noPhoto = d.items.filter(it => !it.image_url || broken.has(it.id))
  return (
    <div className="dong-food">
      <div className="df-head"><h4>{name} 음식점 {d.total}곳</h4><small>대표메뉴 확인 {d.with_menu}곳</small></div>
      {d.total === 0 ? <p className="rank-empty">이 동네에는 등록된 음식점이 없습니다.</p> : (
        <ul className="df-grid">
          {withPhoto.slice(0, shown).map(it => (
            <li key={it.id}>
              <button type="button" className="df-ph" onClick={() => setView(it)} aria-label={`${it.name} 사진 보기`}>
                <img src={it.image_url!} alt={it.name} loading="lazy" referrerPolicy="no-referrer" onError={() => setBroken(new Set(broken).add(it.id))} />
                <em>사진 더 보기</em>
              </button>
              <b>{it.name}</b>
              {it.menu && <p className="df-menu">{it.menu}</p>}
              <small>{it.kind}{it.address ? ` · ${it.address.split(' ').slice(2, 4).join(' ')}` : ''}</small>
            </li>
          ))}
        </ul>
      )}
      {shown < withPhoto.length && <button type="button" className="ghost wide" onClick={() => setShown(shown + PAGE)}>더 보기 ({shown} / {withPhoto.length})</button>}
      {noPhoto.length > 0 && (
        <details className="df-nophoto">
          <summary>사진 없는 음식점 {noPhoto.length}곳</summary>
          <ul>{noPhoto.map(it => <li key={it.id}><b>{it.name}</b>{it.menu ? <span> · {it.menu}</span> : null}</li>)}</ul>
        </details>
      )}
      <p className="fine">{d.note} 사진을 누르면 추가 사진을 볼 수 있습니다.</p>
      {view && <PhotoViewer cid={view.id} name={view.name} main={view.image_url && !broken.has(view.id) ? (view.image_url.startsWith('/images/tour/') ? `${view.image_url}?full=1` : view.image_url) : null}
                            mainLicense={view.license} onClose={() => setView(null)} />}
    </div>
  )
}
