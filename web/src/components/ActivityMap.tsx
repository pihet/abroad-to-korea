import { useEffect, useMemo, useRef, useState } from 'react'
import type { Map as LMap, LayerGroup } from 'leaflet'
import { activitiesApi, type ActivitiesResponse, type ActivityItem } from '../api'

// 지도 라이브러리는 이 패널을 처음 열 때만 불러온다 (첫 화면을 가볍게)
const loadLeaflet = () => Promise.all([import('leaflet'), import('leaflet/dist/leaflet.css')]).then(([L]) => L.default ?? L)

const PAGE = 12

// 시군구 "할 만한 것": 번호 마커 지도 + 같은 번호의 목록. 묶음 칩으로 거른다.
export function ActivityMap({ sigunguKey, sigunguName, month, attractionId }: {
  sigunguKey: string; sigunguName: string; month: number; attractionId: string
}) {
  const [data, setData] = useState<ActivitiesResponse | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [group, setGroup] = useState<string>('all')
  const [shown, setShown] = useState(PAGE)
  const [active, setActive] = useState<string | null>(null)
  const [broken, setBroken] = useState<Set<string>>(new Set())  // 원본이 지워진 사진
  const box = useRef<HTMLDivElement>(null)
  const map = useRef<LMap | null>(null)
  const layer = useRef<LayerGroup | null>(null)
  const fitted = useRef('')

  useEffect(() => {
    setData(null); setErr(null)
    activitiesApi(sigunguKey, month, attractionId).then(setData).catch(e => setErr(e.message))
  }, [sigunguKey, month, attractionId])

  const list: ActivityItem[] = useMemo(() => {
    if (!data) return []
    return (group === 'all' ? data.items : data.items.filter(i => i.group === group)).slice(0, shown)
  }, [data, group, shown])

  // 지도 그리기: 목록에 보이는 곳만 같은 번호로 표시
  useEffect(() => {
    if (!data || !box.current) return
    let off = false
    loadLeaflet().then(L => {
      if (off || !box.current) return
      if (!map.current) {
        map.current = L.map(box.current, { scrollWheelZoom: false, attributionControl: true })
        L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
          maxZoom: 18, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        }).addTo(map.current)
        layer.current = L.layerGroup().addTo(map.current)
      }
      layer.current!.clearLayers()
      const pts: [number, number][] = []
      if (data.anchor) {
        const a = L.marker([data.anchor.lat, data.anchor.lon], {
          icon: L.divIcon({ className: 'pin anchor', html: '<span>★</span>', iconSize: [30, 30], iconAnchor: [15, 15] }),
          title: `사진이 닮은 곳: ${data.anchor.name}`, zIndexOffset: 1000,
        })
        a.bindTooltip(`사진이 닮은 곳 · ${data.anchor.name}`)
        layer.current!.addLayer(a); pts.push([data.anchor.lat, data.anchor.lon])
      }
      list.forEach((it, i) => {
        const m = L.marker([it.lat, it.lon], {
          icon: L.divIcon({ className: `pin g-${it.group}${active === it.id ? ' on' : ''}`, html: `<span>${i + 1}</span>`, iconSize: [26, 26], iconAnchor: [13, 13] }),
          title: it.name, zIndexOffset: active === it.id ? 900 : 0,
        })
        m.bindTooltip(`${i + 1}. ${it.name}`)
        m.on('click', () => setActive(it.id))
        layer.current!.addLayer(m); pts.push([it.lat, it.lon])
      })
      // 목록이 바뀔 때만 범위를 맞추고, 항목을 고를 때는 그 위치로만 옮긴다
      const sig = list.map(i => i.id).join(',')
      if (pts.length && fitted.current !== sig) {
        map.current!.fitBounds(L.latLngBounds(pts), { padding: [24, 24], maxZoom: 14 })
        fitted.current = sig
      } else if (active) {
        const it = list.find(i => i.id === active)
        if (it) map.current!.panTo([it.lat, it.lon])
      }
    })
    return () => { off = true }
  }, [data, list, active])

  useEffect(() => () => { map.current?.remove(); map.current = null }, [])

  if (err) return <p className="error">{err}</p>
  if (!data) return <p className="fine">불러오는 중…</p>
  const total = group === 'all' ? data.items.length : data.groups.find(g => g.key === group)?.count ?? 0

  return (
    <div className="acts">
      <div className="acts-chips" role="group" aria-label="활동 묶음">
        <button type="button" aria-pressed={group === 'all'} onClick={() => { setGroup('all'); setShown(PAGE) }}>전체 {data.items.length}</button>
        {data.groups.map(g => (
          <button key={g.key} type="button" className={`g-${g.key}`} aria-pressed={group === g.key} disabled={!g.count}
                  onClick={() => { setGroup(g.key); setShown(PAGE) }}>
            <i aria-hidden="true" />{g.label} {g.count}
          </button>
        ))}
      </div>
      {data.items.length === 0 ? <p className="fine">{sigunguName}에는 아직 등록된 활동 정보가 없습니다.</p> : <>
        <div className="acts-map" ref={box} role="region" aria-label={`${sigunguName} 활동 지도`} />
        <ol className="acts-list">
          {list.map((it, i) => (
            <li key={it.id} className={active === it.id ? 'on' : ''}>
              <button type="button" onClick={() => setActive(it.id)}>
                <span className={`num g-${it.group}`}>{i + 1}</span>
                {it.image_url && !broken.has(it.id)
                  ? <img src={it.image_url} alt="" loading="lazy" onError={() => setBroken(new Set(broken).add(it.id))} />
                  : <span className="noimg" aria-hidden="true" />}
                <span className="txt">
                  <b>{it.name}</b>
                  <small>{it.kind}{it.distance_km != null ? ` · ${it.distance_km}km` : ''}</small>
                  {it.period && <small className={it.schedule === '예정' ? 'fest' : 'fest past'}>{it.period} · {it.schedule === '예정' ? '2026년 일정' : '지난 개최 기록, 다음 일정 미정'}</small>}
                </span>
              </button>
            </li>
          ))}
        </ol>
        {list.length < total && <button type="button" className="ghost wide" onClick={() => setShown(shown + PAGE)}>더 보기 ({list.length} / {total})</button>}
        <ul className="acts-notes">{data.notes.map(n => <li key={n}>{n}</li>)}<li>목록 사진: 한국관광공사 TourAPI · 공공누리 제1·3유형</li></ul>
      </>}
    </div>
  )
}
