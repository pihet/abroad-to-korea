import { useEffect, useRef, useState } from 'react'
import type { GeoJSON as LGeoJSON, LayerGroup, Map as LMap } from 'leaflet'
import { dongActivitiesApi, type DongActivities, type Neighborhood } from '../api'

const loadLeaflet = () => Promise.all([import('leaflet'), import('leaflet/dist/leaflet.css')]).then(([L]) => L.default ?? L)

// 순위 1~5 동네의 색 (고정 순서). 번호와 함께 읽힌다.
export const RANK_COLORS = ['#d64545', '#2f80d1', '#3d9a5b', '#e0a21a', '#8e4ec6']
// 활동 묶음 색: styles.css 의 --g-* 와 같은 값 (지도 점은 CSS 변수를 못 읽어 값으로 둔다)
const GROUP_COLOR: Record<string, string> = { water: '#1f78b4', mountain: '#2e8b47', leisure: '#d9661f', camping: '#8a6d1f', experience: '#8e44ad', food: '#d6336c' }
const GROUP_LABEL: Record<string, string> = { water: '물·바다', mountain: '산·숲', leisure: '레저', camping: '캠핑', experience: '체험', food: '먹거리' }

export const mainGroup = (g: Record<string, number>) => {
  const top = Object.entries(g).sort((a, b) => b[1] - a[1])[0]
  return top ? `${GROUP_LABEL[top[0]] ?? top[0]} ${top[1]}` : ''
}

const esc = (s: string) => s.replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[ch]!)

// 점을 눌렀을 때 말풍선: 사진(공공누리 1·3유형만, 자르지 않음) · 이름 · 분류 · 대표메뉴 · 주소
function popupHtml(it: DongActivities['items'][number], color: string) {
  const photo = it.image_url
    ? `<div class="ap-ph"><img src="${it.image_url}" alt="${esc(it.name)}" onerror="this.parentNode.remove()"></div>` : ''
  return `${photo}<div class="ap-body">
    <span class="ap-group" style="color:${color}">● ${esc(GROUP_LABEL[it.group] ?? '')} · ${esc(it.kind)}</span>
    <b class="ap-name">${esc(it.name)}</b>
    ${it.menu ? `<span class="ap-menu">대표메뉴 · ${esc(it.menu)}</span>` : ''}
    ${it.address ? `<span class="ap-addr">${esc(it.address)}</span>` : ''}
  </div>`
}

// 시군구 안 읍·면·동 경계. 동네(번호·영역)를 누르면 그 동네로 확대하고, 그 안의 활동지·음식점을 묶음별 색 점으로 찍는다.
export function NeighborhoodMap({ regionKey, hoods, focus, name, selected, onSelect }: {
  regionKey: string; hoods: Neighborhood[]; focus: [number, number, number, number] | null; name: string
  selected: string | null; onSelect: (code: string) => void
}) {
  const box = useRef<HTMLDivElement>(null)
  const map = useRef<LMap | null>(null)
  const L_ = useRef<typeof import('leaflet') | null>(null)
  const shapes = useRef<LGeoJSON | null>(null)
  const dots = useRef<LayerGroup | null>(null)
  const [zoomed, setZoomed] = useState<string | null>(null)  // 사용자가 눌러서 확대한 동네
  const [acts, setActs] = useState<DongActivities | null>(null)
  const [only, setOnly] = useState<string | null>(null)  // 누른 묶음만 보기 (다시 누르면 전체)
  const top = hoods.filter(h => h.rank).sort((a, b) => a.rank! - b.rank!)

  const pick = (code: string) => { setZoomed(code); onSelect(code) }
  const showAll = () => {
    setZoomed(null); setActs(null)
    const L = L_.current, m = map.current
    if (L && m) m.fitBounds(focus ? L.latLngBounds([focus[0], focus[1]], [focus[2], focus[3]]) : shapes.current!.getBounds(), { padding: [16, 16] })
  }

  // 지도와 경계는 지역이 바뀔 때만 새로 그린다
  useEffect(() => {
    let off = false
    loadLeaflet().then(L => {
      if (off || !box.current) return
      L_.current = L
      map.current?.remove()
      const m = L.map(box.current, { scrollWheelZoom: false })
      map.current = m
      L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 18, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> · 경계 SGIS·admdongkor',
      }).addTo(m)
      shapes.current = L.geoJSON({ type: 'FeatureCollection', features: hoods.map(h => ({ type: 'Feature', properties: h, geometry: h.geometry })) } as GeoJSON.FeatureCollection, {
        onEachFeature: (f, layer) => {
          const h = f.properties as Neighborhood
          layer.bindTooltip(`${h.rank ? `${h.rank}. ` : ''}${h.name} · 활동지 ${h.total}곳 · 음식점 ${h.n_food}곳 (눌러서 확대)`, { sticky: true })
          layer.on('click', () => pick(h.code))
        },
      }).addTo(m)
      dots.current = L.layerGroup().addTo(m)
      for (const h of top) {
        const mk = L.marker(h.label, { icon: L.divIcon({ className: 'hood-pin', html: `<span style="background:${RANK_COLORS[h.rank! - 1]}">${h.rank}</span>`, iconSize: [30, 30], iconAnchor: [15, 15] }), zIndexOffset: 500 })
        mk.on('click', () => pick(h.code))
        mk.addTo(m)
      }
      m.fitBounds(focus ? L.latLngBounds([focus[0], focus[1]], [focus[2], focus[3]]) : shapes.current.getBounds(), { padding: [16, 16] })
      restyle()
    })
    return () => { off = true }
  }, [hoods]) // eslint-disable-line react-hooks/exhaustive-deps

  // 선택 동네 강조 (경계 굵게, 나머지는 옅게)
  const restyle = () => shapes.current?.setStyle(f => {
    const h = f?.properties as Neighborhood, r = h.rank, sel = h.code === selected, dim = zoomed && !sel
    const base = r ? { color: RANK_COLORS[r - 1], weight: 2, fillColor: RANK_COLORS[r - 1], fillOpacity: 0.3 }
                   : { color: '#6b7a76', weight: 1, fillColor: '#6b7a76', fillOpacity: 0.04, dashArray: '3 3' }
    if (sel) return { ...base, weight: 4, color: '#15181a', fillOpacity: zoomed ? 0.06 : (r ? 0.45 : 0.15), dashArray: undefined }
    return dim ? { ...base, fillOpacity: 0.02, opacity: 0.4 } : base
  })
  // 확대한 동안에는 동네 안내 문구를 끈다 (점 위를 가리지 않게)
  const tooltips = () => shapes.current?.eachLayer(l => {
    const h = (l as unknown as { feature: { properties: Neighborhood } }).feature.properties
    l.unbindTooltip()
    if (!zoomed) l.bindTooltip(`${h.rank ? `${h.rank}. ` : ''}${h.name} · 활동지 ${h.total}곳 · 음식점 ${h.n_food}곳 (눌러서 확대)`, { sticky: true })
  })
  useEffect(() => { restyle(); tooltips() }, [selected, zoomed]) // eslint-disable-line react-hooks/exhaustive-deps

  // 눌러서 확대한 동네: 범위 맞추고 활동지 불러오기
  useEffect(() => {
    if (!zoomed) return
    const L = L_.current, m = map.current
    const h = hoods.find(x => x.code === zoomed)
    if (L && m && h) m.fitBounds(L.geoJSON(h.geometry as GeoJSON.GeoJsonObject).getBounds(), { padding: [24, 24], maxZoom: 15 })
    setActs(null); setOnly(null)
    dongActivitiesApi(regionKey, zoomed).then(setActs).catch(() => setActs(null))
  }, [zoomed]) // eslint-disable-line react-hooks/exhaustive-deps

  // 활동지 점 그리기 (끈 묶음은 빼고)
  useEffect(() => {
    const L = L_.current, layer = dots.current
    if (!L || !layer) return
    layer.clearLayers()
    if (!acts || !zoomed) return
    for (const it of acts.items) {
      if (only && it.group !== only) continue
      const c = GROUP_COLOR[it.group] ?? '#555'
      L.circleMarker([it.lat, it.lon], { radius: 8, color: '#fff', weight: 2, fillColor: c, fillOpacity: 0.95 })
        .bindTooltip(esc(it.name), { direction: 'top', offset: [0, -6] })
        .bindPopup(popupHtml(it, c), { maxWidth: 260, minWidth: 220, className: 'act-pop' })
        .addTo(layer)
    }
  }, [acts, only, zoomed])

  useEffect(() => () => { map.current?.remove(); map.current = null }, [])
  const zh = hoods.find(h => h.code === zoomed)

  return (
    <div className="hoods">
      <div className="hoods-mapwrap">
        <div className="hoods-map" ref={box} role="region" aria-label={`${name} 동네 지도`} />
        {zoomed && <button type="button" className="hoods-back" onClick={showAll}>← {name} 전체 보기</button>}
      </div>
      {zoomed && (
        <div className="hoods-acts" aria-live="polite">
          <b>{zh?.name}에서 할 수 있는 것</b>
          {!acts ? <small>불러오는 중…</small> : acts.groups.filter(g => g.count).map(g => (
            <button key={g.key} type="button" aria-pressed={!only || only === g.key}
              onClick={() => setOnly(only === g.key ? null : g.key)}>
              <i style={{ background: GROUP_COLOR[g.key] }} />{g.label} {g.count}
            </button>
          ))}
          {acts && acts.items.length === 0 && <small>이 동네에는 등록된 활동지가 없습니다.</small>}
        </div>
      )}
      {top.length ? (
        <ol className="hoods-legend">
          {top.map(h => (
            <li key={h.code}><button type="button" aria-pressed={h.code === selected} onClick={() => pick(h.code)}>
              <span className="n" style={{ background: RANK_COLORS[h.rank! - 1] }}>{h.rank}</span>
              <b>{h.name}</b><small>활동지 {h.total}곳 · {mainGroup(h.groups)} · 음식점 {h.n_food}곳</small></button></li>
          ))}
        </ol>
      ) : <p className="fine">이 지역에는 활동지로 분류된 곳이 아직 없습니다.</p>}
    </div>
  )
}
