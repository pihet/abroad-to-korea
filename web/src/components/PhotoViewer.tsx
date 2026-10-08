import { useEffect, useState, type ReactNode } from 'react'
import { placePhotosApi } from '../api'

type Shot = { url: string; caption: string; license: string | null }

// 가게 사진을 누르면 여는 사진 보기: 대표사진 + 추가 사진(누를 때 받아 오고 서버에 저장). 사진은 자르지 않는다.
// children: 사진 아래에 붙는 장소 정보 (축제·체험 카드를 눌렀을 때 소개·주소·전화 등)
export function PhotoViewer({ cid, name, main, mainLicense, onClose, children }: {
  cid: string; name: string; main: string | null; mainLicense: string | null; onClose: () => void; children?: ReactNode
}) {
  const [shots, setShots] = useState<Shot[]>(main ? [{ url: main, caption: '대표사진', license: mainLicense }] : [])
  const [i, setI] = useState(0)
  const [note, setNote] = useState<string | null>('추가 사진을 불러오는 중…')

  useEffect(() => {
    placePhotosApi(cid)
      .then(r => {
        setShots(s => [...s, ...r.photos.map(p => ({ url: p.url, caption: p.name ?? '추가 사진', license: p.license }))])
        setNote(r.photos.length ? null : '등록된 추가 사진이 없습니다.')
      })
      .catch(e => setNote((e as Error).message))
  }, [cid])
  useEffect(() => {
    // 먼저 받아서(캡처) 멈춘다: 뒤에 열린 지역 상세 창이 같은 Esc 로 함께 닫히지 않게
    const key = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.stopImmediatePropagation(); onClose() }
      if (e.key === 'ArrowRight') setI(x => Math.min(x + 1, shots.length - 1))
      if (e.key === 'ArrowLeft') setI(x => Math.max(x - 1, 0))
    }
    window.addEventListener('keydown', key, true)
    return () => window.removeEventListener('keydown', key, true)
  }, [onClose, shots.length])

  const cur = shots[i]
  return (
    <div className="pv-overlay" role="dialog" aria-modal="true" aria-label={`${name} 사진`} onClick={onClose}>
      <div className="pv" onClick={e => e.stopPropagation()}>
        <div className="pv-head"><b>{name}</b><span>{shots.length ? `${i + 1} / ${shots.length}` : ''}</span>
          <button type="button" className="pv-close" onClick={onClose} aria-label="닫기">×</button></div>
        <div className="pv-main">
          {cur ? <img src={cur.url} alt={`${name} ${cur.caption}`} referrerPolicy="no-referrer" /> : <span>사진이 없습니다</span>}
          {i > 0 && <button type="button" className="pv-nav prev" onClick={() => setI(i - 1)} aria-label="이전 사진">‹</button>}
          {i < shots.length - 1 && <button type="button" className="pv-nav next" onClick={() => setI(i + 1)} aria-label="다음 사진">›</button>}
        </div>
        {cur && <p className="pv-cap">{cur.caption}{cur.license ? ` · 한국관광공사 · ${cur.license}` : ''}</p>}
        {shots.length > 1 && (
          <div className="pv-thumbs">
            {shots.map((s, k) => <button key={s.url} type="button" aria-pressed={k === i} onClick={() => setI(k)}><img src={s.url} alt="" loading="lazy" referrerPolicy="no-referrer" /></button>)}
          </div>
        )}
        {note && <p className="pv-note">{note}</p>}
        {children && <div className="pv-info">{children}</div>}
      </div>
    </div>
  )
}
