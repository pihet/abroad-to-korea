import { useEffect, useState } from 'react'
import { activitiesApi, profileApi, type ActivityItem, type RegionProfile } from './api'
import { ActivityMap } from './components/ActivityMap'
import { CourseView } from './components/CourseView'
import { DongFood } from './components/DongFood'
import { NeighborhoodMap, RANK_COLORS } from './components/NeighborhoodMap'
import { RainCheck } from './components/RainCheck'

// 지역 상세 (인스타그램 프로필형): 프로필 머리 → 동네 하이라이트 → 탭(동네·먹거리 / 언제 갈까 / 할 거리).
// 지도·음식점·비 예보 부품은 예전 상세 화면과 같은 것을 쓴다.

// 평소(100) 대비 혼잡도를 말로: ±5 안은 '평소와 비슷'
const crowdWord = (i: number) => i >= 105 ? `평소보다 ${i - 100}% 붐빌 것으로 보여요` : i <= 95 ? `평소보다 ${100 - i}% 한산할 것으로 보여요` : '평소와 비슷할 것으로 보여요'

type Tab = 'hoods' | 'course' | 'when' | 'acts'
const TABS: [Tab, string][] = [['hoods', '동네·먹거리'], ['course', '코스'], ['when', '언제 갈까'], ['acts', '할 거리']]

export function FeedRegion({ regionKey, initialDong, saved, onToggleSave, onClose, onSearchPhoto }: {
  regionKey: string; initialDong?: string | null; saved: boolean; onToggleSave: () => void; onClose: () => void
  onSearchPhoto: (p: { attraction_id: string; image_url: string }) => void
}) {
  const [d, setD] = useState<RegionProfile | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [items, setItems] = useState<ActivityItem[] | null>(null)  // 축제·체험 줄에 쓴다
  const [peek, setPeek] = useState<ActivityItem | null>(null)
  const [dong, setDong] = useState<string | null>(null)
  const [tab, setTab] = useState<Tab>('hoods')

  useEffect(() => {
    setD(null); setErr(null); setTab('hoods')
    setItems(null); setPeek(null)
    profileApi(regionKey).then(p => { setD(p); setDong(initialDong ?? p.neighborhoods.find(n => n.rank === 1)?.code ?? null) }).catch(e => setErr(e.message))
    activitiesApi(regionKey).then(a => setItems(a.items)).catch(() => setItems(null))
  }, [regionKey, initialDong])
  useEffect(() => {
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', esc); document.body.style.overflow = 'hidden'
    return () => { window.removeEventListener('keydown', esc); document.body.style.overflow = '' }
  }, [onClose])

  const r = d?.region
  const ms = d?.months ?? []
  const fc = ms.find(m => m.basis === 'forecast' && m.congestion_index != null)  // 우리 예측 모델 값 (이번 달)
  const quiet = ms.filter(m => m.congestion_index != null).reduce<(typeof ms)[number] | null>((a, b) => (!a || b.congestion_index! < a.congestion_index! ? b : a), null)
  const top = (d?.neighborhoods ?? []).filter(h => h.rank).sort((a, b) => a.rank! - b.rank!)
  const nActs = (d?.neighborhoods ?? []).reduce((s, h) => s + h.total, 0)  // 관광지·레포츠 (축제·음식점 제외)
  const tags = r ? [
    r.flags.sea && `#바다 ${r.coast_km}km`, r.mountain_n > 0 && `#산숲 ${r.mountain_n}곳`,
    r.flags.city ? '#도시' : '#시골소도시',
  ].filter(Boolean) as string[] : []
  // 원형 프로필은 사진을 자르므로 변경이 허용되는 공공누리 1유형일 때만 사진을 쓴다
  const avatar = d?.photo && d.photo.license.includes('제1유형') ? d.photo.image_url : null
  // 앞으로 열릴(또는 열리고 있는) 축제는 시작일 순, 체험은 그대로 (TourAPI 체험마을·체험장 등)
  const fests = (items ?? []).filter(i => i.group === 'festival' && i.schedule === '예정').sort((a, b) => (a.period ?? '').localeCompare(b.period ?? ''))
  const exps = (items ?? []).filter(i => i.group === 'experience')
  const pickDong = (code: string) => { setDong(code); setTab('hoods') }

  return (
    <div className="igr" role="dialog" aria-modal="true" aria-label={r ? `${r.sido} ${r.name}` : '지역 정보'}>
      <div className="igr-col">
        <header className="igr-top">
          <button type="button" onClick={onClose} aria-label="뒤로"><svg viewBox="0 0 24 24" className="ic" aria-hidden="true"><path d="M15 5l-7 7 7 7" /></svg></button>
          <b>{r?.name ?? ''}</b>
          <span />
        </header>
        {err && <p className="ig-err">{err}</p>}
        {!d && !err && <p className="ig-wait">불러오는 중…</p>}
        {d && r && <>
          <section className="igr-head">
            <span className="igr-av">{avatar ? <img src={avatar} alt="" /> : <i>{r.name.slice(0, 1)}</i>}</span>
            <ul className="igr-stats">
              <li><b>{nActs}</b><small>활동지</small></li>
              <li><b>{d.food.n_places}</b><small>음식점</small></li>
              <li><b>{items ? fests.length : '–'}</b><small>열릴 축제</small></li>
            </ul>
          </section>
          <div className="igr-bio">
            <b>{r.sido} {r.name}</b>
            <p className="igr-tags">{tags.join(' ')}</p>
            {fc && <p><span className="tag">예측</span> {fc.month}월에는 <b>{crowdWord(fc.congestion_index!)}</b></p>}
            {quiet && <p className="sub"><span className="tag ghost">실측</span> 가장 한산했던 달 {quiet.month}월 (평소의 {quiet.congestion_index}%)</p>}
          </div>
          <div className="igr-btns">
            {d.photo && <button type="button" className="primary" onClick={() => onSearchPhoto(d.photo!)}>이 사진과 닮은 곳 찾기</button>}
            <button type="button" aria-pressed={saved} onClick={onToggleSave}>{saved ? '저장됨 ♥' : '저장'}</button>
          </div>

          {top.length > 0 && (
            <nav className="igr-hl" aria-label="활동지가 많은 동네">
              {top.map(h => (
                <button key={h.code} type="button" aria-pressed={dong === h.code} onClick={() => pickDong(h.code)}>
                  <span className="ring" style={{ borderColor: RANK_COLORS[h.rank! - 1] }}><b style={{ color: RANK_COLORS[h.rank! - 1] }}>{h.rank}</b></span>
                  <small>{h.name}</small>
                </button>
              ))}
            </nav>
          )}

          {(fests.length > 0 || exps.length > 0) && (
            <section className="igr-now">
              {fests.length > 0 && <>
                <div className="igr-now-head"><b>열리는 축제</b><small>{fests.length}개 · 한국관광공사 축제 일정</small></div>
                <ol>{fests.map(x => <NowCard key={x.id} x={x} on={peek?.id === x.id} sub={x.period ?? ''} onClick={() => setPeek(peek?.id === x.id ? null : x)} />)}</ol>
              </>}
              {exps.length > 0 && <>
                <div className="igr-now-head"><b>체험 활동</b><small>{exps.length}곳 · 체험마을·체험장 등</small></div>
                <ol>{exps.map(x => <NowCard key={x.id} x={x} on={peek?.id === x.id} sub={x.kind} onClick={() => setPeek(peek?.id === x.id ? null : x)} />)}</ol>
              </>}
              {peek && (
                <div className="igr-peek">
                  <b>{peek.name}</b>
                  <small>{peek.kind}{peek.period ? ` · ${peek.period}` : ''}</small>
                  {peek.address && <small>{peek.address}</small>}
                  <a href={`https://map.kakao.com/link/map/${encodeURIComponent(peek.name)},${peek.lat},${peek.lon}`} target="_blank" rel="noopener">카카오맵에서 보기</a>
                  {peek.license && <small className="lic">사진 한국관광공사 TourAPI · {peek.license}</small>}
                </div>
              )}
            </section>
          )}

          <nav className="igr-tabs" role="tablist">
            {TABS.map(([k, l]) => <button key={k} type="button" role="tab" aria-selected={tab === k} onClick={() => setTab(k)}>{l}</button>)}
          </nav>

          {tab === 'hoods' && (
            <section className="igr-sec">
              {d.photo && (
                <figure className="igr-photo">
                  <img src={d.photo.image_url} alt={d.photo.name} />
                  <figcaption>{d.photo.name} · 한국관광공사 TourAPI · {d.photo.license}</figcaption>
                </figure>
              )}
              <p className="igr-hint">번호는 관광지·레포츠가 많은 동네 Top 5예요. 동네를 누르면 지도가 확대되고 할 거리가 점으로, 아래에 음식점이 나와요.</p>
              <NeighborhoodMap regionKey={regionKey} hoods={d.neighborhoods} focus={d.focus} name={r.name} credit={d.notes.at(-1) ?? ''}
                selected={dong} onSelect={setDong} />
              {dong && <DongFood regionKey={regionKey} code={dong} name={d.neighborhoods.find(n => n.code === dong)?.name ?? ''} />}
            </section>
          )}
          {tab === 'course' && (
            <section className="igr-sec">
              <CourseView regionKey={regionKey} regionName={r.name} />
            </section>
          )}
          {tab === 'when' && (
            <section className="igr-sec">
              <h4>여행 날짜에 비가 올까</h4>
              <RainCheck regionKey={regionKey} />
              <p className="igr-hint">혼잡도는 시군구 전체의 외지인 방문자 수 기준이에요. 예측은 우리가 학습한 월 단위 모델(2025년 검증 오차 WAPE 5.6%) 값이에요.</p>
            </section>
          )}
          {tab === 'acts' && (
            <section className="igr-sec">
              <ActivityMap sigunguKey={regionKey} sigunguName={r.name} attractionId={d.photo?.attraction_id ?? ''} />
            </section>
          )}
          <ul className="igr-notes">{d.notes.slice(0, -1).map(n => <li key={n}>{n}</li>)}</ul>
        </>}
      </div>
    </div>
  )
}

// 축제·체험 카드: 사진(자르지 않음) + 이름 + 기간/종류. 누르면 아래에 주소·지도 링크
function NowCard({ x, on, sub, onClick }: { x: ActivityItem; on: boolean; sub: string; onClick: () => void }) {
  const [broken, setBroken] = useState(false)  // 원본 사진이 없는 곳(404)은 이름으로 대신
  return (
    <li><button type="button" aria-pressed={on} onClick={onClick}>
      <span className="ph">{x.image_url && !broken ? <img src={x.image_url} alt={x.name} loading="lazy" onError={() => setBroken(true)} /> : <i>{x.name}</i>}</span>
      <b>{x.name}</b><small>{sub}</small>
    </button></li>
  )
}
