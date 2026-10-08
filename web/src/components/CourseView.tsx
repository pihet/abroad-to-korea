import { useEffect, useRef, useState } from 'react'
import type { LayerGroup, Map as LMap } from 'leaflet'
import { coursesApi, type Course, type CoursesResponse } from '../api'

const loadLeaflet = () => Promise.all([import('leaflet'), import('leaflet/dist/leaflet.css')]).then(([L]) => L.default ?? L)

// 한국관광공사 공식 여행코스: 코스를 고르면 지도에 들르는 순서대로 번호 핀과 직선을 긋고, 아래에 순서대로 보여 준다.
// 순서·설명·소요시간은 원문 그대로. 선은 실제 길이 아니라 순서를 이은 직선이다.
// 정류장 사이 이동 시간 (서버가 카카오 길찾기로 조회). api.ts 는 다른 작업과 겹쳐 타입을 여기 둔다
type Move = { min: number; km: number; parking?: boolean } | null  // parking: 관광지 앞에 도로가 없어 근처 주차장 기준
type Leg = { straight_km: number; car: Move; walk: Move; from?: number }  // from: 출발 정류장 번호 (중간에 위치 없는 정류장을 건너뛸 때)
const hm = (m: number) => (m >= 60 ? `${Math.floor(m / 60)}시간${m % 60 ? ` ${m % 60}분` : ''}` : `${Math.max(m, 1)}분`)

export function CourseView({ regionKey, regionName }: { regionKey: string; regionName: string }) {
  const [d, setD] = useState<CoursesResponse | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [pick, setPick] = useState(0)
  const box = useRef<HTMLDivElement>(null)
  const map = useRef<LMap | null>(null)
  const layer = useRef<LayerGroup | null>(null)

  useEffect(() => { setD(null); setPick(0); coursesApi(regionKey).then(setD).catch(e => setErr(e.message)) }, [regionKey])
  const c: Course | undefined = d?.items[pick]
  const [legs, setLegs] = useState<Record<string, Leg> | null>(null)  // 키: 도착 정류장 order-id
  const [legErr, setLegErr] = useState<string | null>(null)
  useEffect(() => {
    setLegs(null); setLegErr(null)
    const pts = c ? c.stops.filter(s => s.lat != null && s.lon != null) : []
    if (pts.length < 2) { setLegs({}); return }
    let off = false
    fetch(`/api/legs?pts=${pts.map(s => `${s.lat!.toFixed(5)},${s.lon!.toFixed(5)}`).join(';')}`)
      .then(async r => { if (!r.ok) throw new Error((await r.json().catch(() => null))?.detail ?? '이동 시간을 불러오지 못했어요'); return r.json() })
      .then((r: { legs: Leg[] }) => { if (!off) setLegs(Object.fromEntries(r.legs.map((l, i) => [`${pts[i + 1].order}-${pts[i + 1].id}`,
        { ...l, from: pts[i + 1].order - pts[i].order > 1 ? pts[i].order : undefined }]))) })
      .catch(e => { if (!off) { setLegs({}); setLegErr(e.message) } })
    return () => { off = true }
  }, [c])

  useEffect(() => {
    if (!c) return
    let off = false
    loadLeaflet().then(L => {
      if (off || !box.current) return
      if (!map.current) {
        map.current = L.map(box.current, { scrollWheelZoom: false })
        L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 18, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' }).addTo(map.current)
        layer.current = L.layerGroup().addTo(map.current)
      }
      layer.current!.clearLayers()
      const pts = c.stops.filter(s => s.lat != null && s.lon != null).map(s => ({ s, ll: [s.lat!, s.lon!] as [number, number] }))
      if (!pts.length) return
      L.polyline(pts.map(p => p.ll), { color: '#ee2a7b', weight: 3, opacity: 0.8, dashArray: '6 6' }).addTo(layer.current!)
      for (const { s, ll } of pts) {
        L.marker(ll, { icon: L.divIcon({ className: 'course-pin', html: `<span>${s.order}</span>`, iconSize: [28, 28], iconAnchor: [14, 14] }) })
          .bindTooltip(s.name, { direction: 'top', offset: [0, -12] }).addTo(layer.current!)
      }
      map.current!.fitBounds(L.latLngBounds(pts.map(p => p.ll)), { padding: [28, 28], maxZoom: 14 })
    })
    return () => { off = true }
  }, [c])
  useEffect(() => () => { map.current?.remove(); map.current = null }, [])

  if (err) return <p className="ig-err">{err}</p>
  if (!d) return <p className="ig-wait">코스를 불러오는 중…</p>
  if (!d.items.length) return (
    <p className="igr-hint">{regionName}을 지나는 공식 여행코스가 아직 없습니다.
      {d.coverage.loaded < d.coverage.listed && ` (전국 ${d.coverage.listed}개 중 ${d.coverage.loaded}개 받음, 매일 이어서 받는 중)`}</p>
  )
  const located = c ? c.stops.filter(s => s.lat != null).length : 0
  return (
    <div className="course">
      <div className="course-pick" role="tablist" data-drag>
        {d.items.map((x, i) => (
          <button key={x.id} type="button" role="tab" aria-selected={i === pick} onClick={() => setPick(i)}>
            <b>{x.title}</b><small>{x.stops.length}곳{x.taketime ? ` · ${x.taketime}` : ''}</small>
          </button>
        ))}
      </div>
      {c && <>
        <div className="course-head">
          <b>{c.title}</b>
          <small>{[c.taketime && `소요 ${c.taketime}`, c.distance && `총 ${c.distance}`, c.theme].filter(Boolean).join(' · ') || '소요시간 정보 없음'}</small>
        </div>
        <div className="course-map" ref={box} role="region" aria-label={`${c.title} 지도`} />
        {located < c.stops.length && <p className="igr-hint">{c.stops.length - located}곳은 위치 정보가 없어 지도에 표시하지 않았어요.</p>}
        {legs === null && <p className="igr-hint">이동 시간을 계산하는 중…</p>}
        {legErr && <p className="igr-hint">{legErr}</p>}
        <ol className="course-stops">
          {c.stops.map(s => (
            <li key={`${s.order}-${s.id}`}>
              {legs?.[`${s.order}-${s.id}`] && <LegLine l={legs[`${s.order}-${s.id}`]} />}
              <span className="n">{s.order}</span>
              <div>
                <b>{s.name}</b>
                {s.kind && <small className="kind">{s.kind}</small>}
                {s.region && s.region !== regionKey && <small className="kind">· 다른 시군구</small>}
                {s.image_url && <figure><img src={s.image_url} alt={s.name} loading="lazy" /></figure>}
                {s.overview && <p>{s.overview}</p>}
                {s.lat != null && <a href={`https://map.kakao.com/link/map/${encodeURIComponent(s.name)},${s.lat},${s.lon}`} target="_blank" rel="noopener">카카오맵</a>}
              </div>
            </li>
          ))}
        </ol>
      </>}
      <p className="igr-hint">지도의 선은 들르는 순서를 직선으로 이은 것이며 실제 길이 아니에요.</p>
    </div>
  )
}

// 앞 정류장에서 이 정류장까지: 차로 ○분 · ○km (가까우면 걸어서 ○분)
function LegLine({ l }: { l: Leg }) {
  const parts = [l.car && `차로 ${hm(l.car.min)} · ${l.car.km}km${l.car.parking ? ' (주차장 기준)' : ''}`, l.walk && `걸어서 ${hm(l.walk.min)}`].filter(Boolean)
  const head = l.from ? `${l.from}번에서 ` : ''
  return <p className="course-leg">{head}{parts.length ? parts.join(' · ') : `직선 ${l.straight_km}km (길찾기 결과 없음)`}</p>
}
