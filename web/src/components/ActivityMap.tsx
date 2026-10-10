import { useEffect, useMemo, useRef, useState } from 'react'
import type { Map as LMap, LayerGroup } from 'leaflet'
import { activitiesApi, type ActivitiesResponse, type ActivityItem } from '../api'

// 지도 라이브러리는 이 패널을 처음 열 때만 불러온다 (첫 화면을 가볍게)
const loadLeaflet = () => Promise.all([import('leaflet'), import('leaflet/dist/leaflet.css')]).then(([L]) => L.default ?? L)

const PAGE = 12
// 할 거리는 '가 볼 곳'만: 먹거리는 동네·먹거리 탭, 축제·체험은 지역 상세 위쪽 줄에 따로 있어 뺀다 (2026-10-11)
const PLACE_GROUPS = ['water', 'mountain', 'leisure', 'camping']

// 시군구 "할 거리": 번호 마커 지도 + 같은 번호의 카드 목록(사진 있는 곳만, 가까운 순). 묶음 칩으로 거른다.
// onPick: 카드를 누르면 지역 상세가 사진 팝업(사진·소개·주소·시간·전화)을 띄운다. 이 탭 안에서 띄우면 탭 영역에 갇혀 사진이 작아진다
export function ActivityMap({ sigunguKey, sigunguName, attractionId, initialGroup = 'all', onPick }: {
  sigunguKey: string; sigunguName: string; attractionId: string; initialGroup?: string; onPick?: (it: ActivityItem) => void
}) {
  const [data, setData] = useState<ActivitiesResponse | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [group, setGroup] = useState<string>(initialGroup)
  const [shown, setShown] = useState(PAGE)
  const [active, setActive] = useState<string | null>(null)
  const [broken, setBroken] = useState<Set<string>>(new Set())  // 원본이 지워진 사진
  const box = useRef<HTMLDivElement>(null)
  const map = useRef<LMap | null>(null)
  const layer = useRef<LayerGroup | null>(null)
  const fitted = useRef('')

  useEffect(() => {
    setData(null); setErr(null)
    activitiesApi(sigunguKey, attractionId).then(setData).catch(e => setErr(e.message))
  }, [sigunguKey, attractionId])

  // 사진 없는 곳은 보여 주지 않는다 (2026-10-11 사용자 결정). 원본이 지워진 사진(broken)도 뺀다
  const places = useMemo(() => (data?.items ?? []).filter(i => PLACE_GROUPS.includes(i.group) && i.image_url && !broken.has(i.id)), [data, broken])
  const inGroup = useMemo(() => (group === 'all' ? places : places.filter(i => i.group === group)), [places, group])
  const list: ActivityItem[] = useMemo(() => inGroup.slice(0, shown), [inGroup, shown])

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
  const groups = data.groups.filter(g => PLACE_GROUPS.includes(g.key))
  const count = (k: string) => places.filter(i => i.group === k).length

  return (
    <div className="acts">
      <div className="acts-chips" role="group" aria-label="활동 묶음">
        <button type="button" aria-pressed={group === 'all'} onClick={() => { setGroup('all'); setShown(PAGE) }}>전체 {places.length}</button>
        {groups.map(g => (
          <button key={g.key} type="button" className={`g-${g.key}`} aria-pressed={group === g.key} disabled={!count(g.key)}
                  onClick={() => { setGroup(g.key); setShown(PAGE) }}>
            <i aria-hidden="true" />{g.label} {count(g.key)}
          </button>
        ))}
      </div>
      {places.length === 0 ? <p className="fine">{sigunguName}에는 아직 등록된 관광지·레포츠 정보가 없습니다.</p> : <>
        <div className="acts-map" ref={box} role="region" aria-label={`${sigunguName} 활동 지도`} />
        {/* AI 여행 결과와 같은 카드 (feed.css .ask-cards). 번호 색은 지도 점과 같은 묶음 색 */}
        <ol className="ask-cards acts-cards">
          {list.map((it, i) => (
            <li key={it.id} className={active === it.id ? 'top' : undefined}>
              <button type="button" className="ask-card" onClick={() => { setActive(it.id); onPick?.(it) }}>
                <img src={it.image_url!} alt={it.name} loading="lazy" onError={() => setBroken(new Set(broken).add(it.id))} />
                <span className="ask-copy">
                  <b><span className={`ask-rank g-${it.group}`}>{i + 1}</span>{it.name}</b>
                  <small>{it.address ?? sigunguName}</small>
                  <span className="ask-chips">
                    <i>{it.kind}</i>
                    {it.distance_km != null && <i>{it.distance_km}km</i>}
                    <i className="more">상세보기 ›</i>
                  </span>
                </span>
              </button>
            </li>
          ))}
        </ol>
        {list.length < inGroup.length && <button type="button" className="ghost wide" onClick={() => setShown(shown + PAGE)}>더 보기 ({list.length} / {inGroup.length})</button>}
        <p className="acts-note">사진 속 장소에서 가까운 순 · 한국관광공사 TourAPI 관광지·레포츠</p>
      </>}
    </div>
  )
}
