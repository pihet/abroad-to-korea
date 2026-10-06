import { useEffect, useState } from 'react'
import { profileApi, type RegionProfile } from '../api'
import { ActivityMap } from './ActivityMap'
import { MonthsChart } from './MonthsChart'
import { NeighborhoodMap } from './NeighborhoodMap'

// 지역 상세: 이 지역은 어떤 곳인지 → 언제 가면 좋은지 → 어느 동네에 할 거리가 몰렸는지 → 할 만한 것 목록.
export function RegionPage({ regionKey, month, onMonth, onClose, onSearchPhoto }: {
  regionKey: string; month: number; onMonth: (m: number) => void; onClose: () => void
  onSearchPhoto: (p: { attraction_id: string; image_url: string }) => void
}) {
  const [d, setD] = useState<RegionProfile | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => { setErr(null); profileApi(regionKey, month).then(setD).catch(e => setErr(e.message)) }, [regionKey, month])
  useEffect(() => {
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', esc); document.body.style.overflow = 'hidden'
    return () => { window.removeEventListener('keydown', esc); document.body.style.overflow = '' }
  }, [onClose])

  const r = d?.region
  const label = (k: string) => d?.filters.find(f => f.key === k)?.label
  const cur = d?.months.find(m => m.month === month)
  const badges = r ? ([
    r.flags.sea && `바다 ${r.coast_km}km`, r.flags.mountain && `산·숲 ${r.mountain_n}곳`,
    r.flags.city ? `도시 · 동 거주 ${Math.round((r.urban_share ?? 0) * 100)}%` : `시골·소도시 · 동 거주 ${Math.round((r.urban_share ?? 0) * 100)}%`,
    r.flags.calm && label('calm'), r.flags.mild && `${month}월 ${label('mild')}`,
  ].filter(Boolean) as string[]) : []

  return (
    <div className="region-overlay" role="dialog" aria-modal="true" aria-label={r ? `${r.sido} ${r.name}` : '지역 정보'}>
      <div className="region-page">
        <button type="button" className="region-close" onClick={onClose} aria-label="닫기">×</button>
        {err && <p className="error">{err}</p>}
        {!d ? <p className="fine">불러오는 중…</p> : <>
          <header className="region-hero">
            {d.photo && <div className="region-photo"><img src={d.photo.image_url} alt={d.photo.name} /></div>}
            <div className="region-head">
              <p className="eyebrow">{r!.sido}</p>
              <h2>{r!.name}</h2>
              <div className="region-badges">{badges.map(b => <span key={b}>{b}</span>)}</div>
              <div className="region-facts">
                <div><small>{month}월 평균기온</small><b>{cur?.temp_c ?? '–'}<i>°C</i></b></div>
                <div><small>{month}월 비 온 날</small><b>{cur?.rain_days ?? '–'}<i>일</i></b></div>
                <div><small>{month}월 혼잡도</small><b>{cur?.congestion_index ?? '–'}<i>/ 평소 100</i></b></div>
                <div><small>외지인 방문</small><b>{cur?.visitors ? Math.round(cur.visitors / 10000).toLocaleString() : '–'}<i>만 명</i></b></div>
              </div>
              {d.photo && <button type="button" className="primary" onClick={() => onSearchPhoto(d.photo!)}>이 사진과 닮은 다른 곳 찾기</button>}
              {d.photo && <p className="credit">사진 {d.photo.name} · 한국관광공사 TourAPI · {d.photo.license}</p>}
            </div>
          </header>

          <section className="region-sec">
            <h3>언제 가면 좋을까</h3>
            <p className="sub">달을 누르면 그 달 기준으로 바뀝니다.</p>
            <MonthsChart months={d.months} month={month} onPick={onMonth} />
          </section>

          <section className="region-sec">
            <h3>할 거리가 몰린 동네 Top 5</h3>
            <p className="sub">읍·면·동마다 관광지·레포츠 수를 센 순서입니다 (축제 제외).</p>
            <NeighborhoodMap hoods={d.neighborhoods} focus={d.focus} name={r!.name} credit={d.notes.at(-1) ?? ''} />
          </section>

          <section className="region-sec">
            <h3>{r!.name}에서 할 만한 것 · {month}월</h3>
            <ActivityMap sigunguKey={regionKey} sigunguName={r!.name} month={month} attractionId={d.photo?.attraction_id ?? ''} />
          </section>

          <ul className="acts-notes">{d.notes.slice(0, -1).map(n => <li key={n}>{n}</li>)}</ul>
        </>}
      </div>
    </div>
  )
}
