import { useEffect, useState } from 'react'
import { profileApi, type RegionProfile } from '../api'
import { ActivityMap } from './ActivityMap'
import { RainCheck } from './RainCheck'
import { DongFood } from './DongFood'
import { NeighborhoodMap } from './NeighborhoodMap'

// 평소(100) 대비 혼잡도를 말로: ±5 안은 '평소와 비슷'
const crowdWord = (i: number) => i >= 105 ? `평소보다 ${i - 100}% 붐빌 것으로 보여요` : i <= 95 ? `평소보다 ${100 - i}% 한산할 것으로 보여요` : '평소와 비슷할 것으로 보여요'

// 지역 상세: 이 지역은 어떤 곳인지 → 언제 가면 좋은지 → 어느 동네에 할 거리가 몰렸는지 → 할 만한 것 목록.
export function RegionPage({ regionKey, initialGroup, onClose, onSearchPhoto }: {
  regionKey: string; initialGroup?: string; onClose: () => void
  onSearchPhoto: (p: { attraction_id: string; image_url: string }) => void
}) {
  const [d, setD] = useState<RegionProfile | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [dong, setDong] = useState<string | null>(null)

  useEffect(() => {
    setErr(null)
    profileApi(regionKey).then(p => { setD(p); setDong(p.neighborhoods.find(n => n.rank === 1)?.code ?? null) }).catch(e => setErr(e.message))
  }, [regionKey])  // 처음에는 1위 동네의 음식점을 보여 준다
  useEffect(() => {
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', esc); document.body.style.overflow = 'hidden'
    return () => { window.removeEventListener('keydown', esc); document.body.style.overflow = '' }
  }, [onClose])

  const r = d?.region
  const label = (k: string) => d?.filters.find(f => f.key === k)?.label
  const ms = d?.months ?? []
  const quiet = ms.filter(m => m.congestion_index != null).reduce<(typeof ms)[number] | null>((a, b) => (!a || b.congestion_index! < a.congestion_index! ? b : a), null)
  const fc = ms.find(m => m.basis === 'forecast' && m.congestion_index != null)  // 우리 예측 모델 값 (이번 달)
  const badges = r ? ([
    r.flags.sea && `바다 ${r.coast_km}km`, r.flags.mountain && `산·숲 ${r.mountain_n}곳`,
    r.flags.city ? `도시 · 동 거주 ${Math.round((r.urban_share ?? 0) * 100)}%` : `시골·소도시 · 동 거주 ${Math.round((r.urban_share ?? 0) * 100)}%`,
    r.flags.calm && label('calm'),
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
              {d.photo && <button type="button" className="primary" onClick={() => onSearchPhoto(d.photo!)}>이 사진과 닮은 다른 곳 찾기</button>}
              {d.photo && <p className="credit">사진 {d.photo.name} · 한국관광공사 TourAPI · {d.photo.license}</p>}
            </div>
          </header>

          <section className="region-sec">
            <h3>언제 가면 좋을까</h3>
            {(fc || quiet) && (
              <div className="crowd-line">
                {fc && <p><span className="tag">예측</span>{fc.month}월 {r!.name}은 <b>{crowdWord(fc.congestion_index!)}</b>
                  <small>외지인 약 {Math.round(fc.visitors! / 10000).toLocaleString()}만 명 · 평소(최근 12개월 평균) 대비 {fc.congestion_index}</small></p>}
                {quiet && <p><span className="tag ghost">실측</span>가장 한산했던 달은 <b>{quiet.month}월</b>
                  <small>평소의 {quiet.congestion_index}% · {quiet.basis_month}</small></p>}
                <p className="fine">혼잡도는 시군구 전체의 외지인 방문자 수 기준입니다. 예측은 우리가 학습한 월 단위 모델(2025년 검증 오차 WAPE 5.6%) 값입니다.</p>
              </div>
            )}
            <h4 className="rain-title">여행 날짜에 비가 올까</h4>
            <RainCheck regionKey={regionKey} />
          </section>

          <section className="region-sec">
            <h3>동네와 먹거리</h3>
            <p className="sub">번호는 관광지·레포츠가 많은 동네 Top 5입니다. 동네를 누르면 지도가 확대되며 그 동네의 활동지가 점으로 나타나고, 아래에 음식점과 대표메뉴가 나옵니다.</p>
            <NeighborhoodMap regionKey={regionKey} hoods={d.neighborhoods} focus={d.focus} name={r!.name} credit={d.notes.at(-1) ?? ''}
              selected={dong} onSelect={setDong} />
            {dong && <DongFood regionKey={regionKey} code={dong} name={d.neighborhoods.find(n => n.code === dong)?.name ?? ''} />}
          </section>

          <section className="region-sec">
            <h3>{r!.name}에서 할 만한 것</h3>
            <ActivityMap sigunguKey={regionKey} sigunguName={r!.name} attractionId={d.photo?.attraction_id ?? ''} initialGroup={initialGroup} />
          </section>

          <ul className="acts-notes">{d.notes.slice(0, -1).map(n => <li key={n}>{n}</li>)}</ul>
        </>}
      </div>
    </div>
  )
}
