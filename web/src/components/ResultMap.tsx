import { useEffect, useRef } from 'react'
import type { LayerGroup, Map as LMap } from 'leaflet'
import type { Candidate } from '../api'

const loadLeaflet = () => Promise.all([import('leaflet'), import('leaflet/dist/leaflet.css')]).then(([L]) => L.default ?? L)

// 추천 결과 전국 지도: 카드와 같은 번호를 각 후보의 "가장 닮은 관광지" 위치에 찍는다.
// 번호를 누르면 그 카드로 이동하고, 카드에 마우스를 올리면 번호가 커진다.
export function ResultMap({ items, active, onPick }: { items: Candidate[]; active: string | null; onPick: (key: string) => void }) {
  const box = useRef<HTMLDivElement>(null)
  const map = useRef<LMap | null>(null)
  const layer = useRef<LayerGroup | null>(null)
  const fittedFor = useRef('')

  useEffect(() => {
    let off = false
    loadLeaflet().then(L => {
      if (off || !box.current) return
      if (!map.current) {
        map.current = L.map(box.current, { scrollWheelZoom: false, zoomControl: true })
        L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
          maxZoom: 16, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        }).addTo(map.current)
        layer.current = L.layerGroup().addTo(map.current)
      }
      layer.current!.clearLayers()
      const pts: [number, number][] = []
      items.forEach(c => {
        const { latitude: lat, longitude: lon } = c.attraction
        if (lat == null || lon == null) return
        const on = c.sigungu.key === active
        const m = L.marker([lat, lon], {
          icon: L.divIcon({ className: on ? 'rpin on' : 'rpin', html: `<span>${c.rank}</span><b>${c.sigungu.name}</b>`, iconSize: [0, 0] }),
          zIndexOffset: on ? 1000 : -c.rank, title: `${c.rank}. ${c.sigungu.sido} ${c.sigungu.name}`,
        })
        m.on('click', () => onPick(c.sigungu.key))
        layer.current!.addLayer(m); pts.push([lat, lon])
      })
      const sig = items.map(c => c.sigungu.key).join(',')
      if (pts.length && fittedFor.current !== sig) {
        map.current!.fitBounds(L.latLngBounds(pts), { padding: [48, 48], maxZoom: 9 })
        fittedFor.current = sig
      }
    })
    return () => { off = true }
  }, [items, active]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => () => { map.current?.remove(); map.current = null }, [])
  return <div className="result-map" ref={box} role="region" aria-label="추천 위치 지도" />
}
