import { useMemo, useState } from 'react'
import { matches, ORIGINS, type Filters, type Origin, type RegionRow, type RegionsResponse } from '../api'
import { ActivityMap } from './ActivityMap'

type Sort = 'calm' | 'near' | 'name'
const SORT_LABEL: Record<Sort, string> = { calm: '방문객 적은 순 (월평균)', near: '가까운 순', name: '이름순' }
const PAGE = 24

// 사진 없이 둘러보기: 조건에 맞는 시군구를 기준 하나로 정렬해 대표 사진으로 보여 준다.
// 사진을 고르면 그 사진으로 "닮은 곳 찾기"가 이어진다.
export function BrowseStep({ filters, regions, origin, onOrigin, onSearchPhoto, onOpen }: {
  filters: Filters; regions: RegionsResponse | null; origin: Origin | null; onOrigin: (o: Origin | null) => void
  onSearchPhoto: (r: RegionRow) => void; onOpen: (key: string) => void
}) {
  const [sort, setSort] = useState<Sort>('calm')
  const [shown, setShown] = useState(PAGE)
  const [open, setOpen] = useState<string | null>(null)

  const list = useMemo(() => {
    const rows = (regions?.regions ?? []).filter(r => matches(r, filters) && r.photo)
    const v = (r: RegionRow) => sort === 'calm' ? r.visitors ?? Infinity : sort === 'near' ? r.distance_km ?? Infinity : 0
    return rows.sort((a, b) => v(a) - v(b) || a.name.localeCompare(b.name, 'ko'))
  }, [regions, filters, sort])

  if (!regions) return <p className="fine">불러오는 중…</p>
  return (
    <section className="browse">
      <div className="browse-head">
        <h2>조건에 맞는 곳 {list.length}곳</h2>
        <div className="browse-sort">
          <select aria-label="정렬" value={sort} onChange={e => { setSort(e.target.value as Sort); if (e.target.value === 'near' && !origin) onOrigin('서울') }}>
            {(Object.keys(SORT_LABEL) as Sort[]).map(s => <option key={s} value={s}>{SORT_LABEL[s]}</option>)}
          </select>
          {sort === 'near' && (
            <select aria-label="출발지" value={origin ?? '서울'} onChange={e => onOrigin(e.target.value as Origin)}>
              {ORIGINS.map(o => <option key={o} value={o}>{o}에서</option>)}
            </select>
          )}
        </div>
      </div>
      <p className="sub">
        {sort === 'calm' ? '월평균 외지인 방문자가 적은 순서입니다.' : sort === 'near' ? '출발 도시에서 직선거리가 가까운 순서입니다.' : '가나다 순서입니다.'}
        {' '}사진은 각 시군구 관광지 사진 중 그 지역 사진들의 평균에 가장 가까운 한 장입니다.
      </p>
      <div className="browse-grid">
        {list.slice(0, shown).map(r => (
          <article key={r.key} className="bcard">
            <div className="ph"><img src={r.photo!.image_url} alt={r.photo!.name} loading="lazy" /></div>
            <div className="bbody">
              <h3>{r.name} <small>{r.sido}</small></h3>
              <p className="bphoto">{r.photo!.name}</p>
              <div className="bfacts">
                {r.visitors != null && <span>월평균 외지인 약 {Math.round(r.visitors / 10000).toLocaleString()}만 명</span>}
                {r.temp_c != null && <span>{r.temp_c}°C · 비 {r.rain_days}일</span>}
                {r.distance_km != null && sort === 'near' && <span>{r.distance_km}km</span>}
                {r.flags.sea && <span className="badge-sea">바다 {r.coast_km}km</span>}
                {r.flags.mountain && <span className="badge-mt">산·숲 {r.mountain_n}곳</span>}
              </div>
              <div className="bactions">
                <button type="button" className="primary" onClick={() => onSearchPhoto(r)}>이 사진과 닮은 곳 찾기</button>
                <button type="button" className="ghost" onClick={() => onOpen(r.key)}>지역 자세히</button>
                <button type="button" className="ghost" aria-expanded={open === r.key} onClick={() => setOpen(open === r.key ? null : r.key)}>할 만한 것</button>
              </div>
              <p className="credit">사진 한국관광공사 TourAPI · {r.photo!.license}</p>
            </div>
            {open === r.key && (
              <div className="bacts"><ActivityMap sigunguKey={r.key} sigunguName={r.name} attractionId={r.photo!.attraction_id} /></div>
            )}
          </article>
        ))}
      </div>
      {shown < list.length && <button type="button" className="ghost wide" onClick={() => setShown(shown + PAGE)}>더 보기 ({shown} / {list.length})</button>}
    </section>
  )
}
