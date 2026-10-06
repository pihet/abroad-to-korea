import { useEffect, useRef } from 'react'
import type { Map as LMap } from 'leaflet'
import type { Neighborhood } from '../api'

const loadLeaflet = () => Promise.all([import('leaflet'), import('leaflet/dist/leaflet.css')]).then(([L]) => L.default ?? L)

// 순위 1~5 동네의 색 (고정 순서). 순위가 같은 지역 안에서만 쓰이므로 번호와 함께 읽힌다.
export const RANK_COLORS = ['#d64545', '#2f80d1', '#3d9a5b', '#e0a21a', '#8e4ec6']
const GROUP_LABEL: Record<string, string> = { water: '물·바다', mountain: '산·숲', leisure: '레저', camping: '캠핑', experience: '체험' }

export const mainGroup = (g: Record<string, number>) => {
  const top = Object.entries(g).sort((a, b) => b[1] - a[1])[0]
  return top ? `${GROUP_LABEL[top[0]] ?? top[0]} ${top[1]}` : ''
}

// 시군구 안 읍·면·동 경계: 전부 옅게, 활동지가 많은 Top 5는 색과 번호로.
export function NeighborhoodMap({ hoods, focus, name, credit }: { hoods: Neighborhood[]; focus: [number, number, number, number] | null; name: string; credit: string }) {
  const box = useRef<HTMLDivElement>(null)
  const map = useRef<LMap | null>(null)
  const top = hoods.filter(h => h.rank).sort((a, b) => a.rank! - b.rank!)

  useEffect(() => {
    let off = false
    loadLeaflet().then(L => {
      if (off || !box.current) return
      map.current?.remove()
      const m = L.map(box.current, { scrollWheelZoom: false })
      map.current = m
      L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 18, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> · 경계 SGIS·admdongkor',
      }).addTo(m)
      const all = L.geoJSON({ type: 'FeatureCollection', features: hoods.map(h => ({ type: 'Feature', properties: h, geometry: h.geometry })) } as GeoJSON.FeatureCollection, {
        style: f => {
          const r = (f?.properties as Neighborhood).rank
          return r ? { color: RANK_COLORS[r - 1], weight: 2, fillColor: RANK_COLORS[r - 1], fillOpacity: 0.35 }
                   : { color: '#6b7a76', weight: 1, fillOpacity: 0.04, dashArray: '3 3' }
        },
        onEachFeature: (f, layer) => {
          const h = f.properties as Neighborhood
          layer.bindTooltip(`${h.rank ? `${h.rank}. ` : ''}${h.name} · 활동지 ${h.total}곳`, { sticky: true })
        },
      }).addTo(m)
      for (const h of top) {
        L.marker(h.label, { icon: L.divIcon({ className: 'hood-pin', html: `<span style="background:${RANK_COLORS[h.rank! - 1]}">${h.rank}</span>`, iconSize: [30, 30], iconAnchor: [15, 15] }), interactive: false }).addTo(m)
      }
      // 외딴 작은 섬(예: 울릉군의 독도)을 빼고 맞춘 범위. 없으면 경계 전체
      m.fitBounds(focus ? L.latLngBounds([focus[0], focus[1]], [focus[2], focus[3]]) : all.getBounds(), { padding: [16, 16] })
    })
    return () => { off = true }
  }, [hoods]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => () => { map.current?.remove(); map.current = null }, [])

  return (
    <div className="hoods">
      <div className="hoods-map" ref={box} role="region" aria-label={`${name} 동네 지도`} />
      {top.length ? (
        <ol className="hoods-legend">
          {top.map(h => (
            <li key={h.code}><span className="n" style={{ background: RANK_COLORS[h.rank! - 1] }}>{h.rank}</span>
              <b>{h.name}</b><small>활동지 {h.total}곳 · 가장 많은 것: {mainGroup(h.groups)}</small></li>
          ))}
        </ol>
      ) : <p className="fine">이 지역에는 활동지로 분류된 곳이 아직 없습니다.</p>}
      <p className="fine">{credit}</p>
    </div>
  )
}
