import { useEffect, useRef, useState } from 'react'
import type { Map as LMap } from 'leaflet'
import type { PlaceDetail } from '../api'

const loadLeaflet = () => Promise.all([import('leaflet'), import('leaflet/dist/leaflet.css')]).then(([L]) => L.default ?? L)

const Ico = ({ d }: { d: string }) => <svg viewBox="0 0 24 24" aria-hidden="true"><path d={d} /></svg>
const PIN = 'M12 21s-6.5-6.2-6.5-11a6.5 6.5 0 0 1 13 0c0 4.8-6.5 11-6.5 11zM12 12.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5z'
const CLOCK = 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 7v5l3 2'
const PHONE = 'M5 4h3l2 5-2.5 1.5a11 11 0 0 0 6 6L15 14l5 2v3a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2z'
const HOME = 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM3 12h18M12 3c2.5 2.5 3.8 5.5 3.8 9s-1.3 6.5-3.8 9c-2.5-2.5-3.8-5.5-3.8-9S9.5 5.5 12 3z'

// 사진 보기 아래 장소 정보: 주소(복사) · 이용 시간·쉬는 날 · 전화(누르면 걸기) · 홈페이지 · 위치 지도.
// 값은 한국관광공사 TourAPI (detailCommon2·detailIntro2). 없는 칸은 줄째 숨긴다
// map=false: 지역 상세처럼 아래에 이미 지도가 있는 화면에서는 위치 지도를 빼고 카카오맵 링크만 둔다
export function PlaceInfo({ d, name, map: showMap = true }: { d: PlaceDetail; name: string; map?: boolean }) {
  const [copied, setCopied] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  const map = useRef<LMap | null>(null)

  useEffect(() => {
    if (!showMap || d.lat == null || d.lon == null || !box.current) return
    let off = false
    loadLeaflet().then(L => {
      if (off || !box.current || map.current) return
      map.current = L.map(box.current, { scrollWheelZoom: false, zoomControl: false }).setView([d.lat!, d.lon!], 15)
      L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 18, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      }).addTo(map.current)
      L.circleMarker([d.lat!, d.lon!], { radius: 9, color: '#fff', weight: 3, fillColor: '#ee2a7b', fillOpacity: 1 }).addTo(map.current)
    })
    return () => { off = true; map.current?.remove(); map.current = null }
  }, [showMap, d.lat, d.lon])

  const copy = () => {
    if (!d.address) return
    navigator.clipboard?.writeText(d.address).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500) }).catch(() => {})
  }
  const phones = (d.tel ?? '').split(/[,\n]/).map(x => x.trim()).filter(Boolean)
  return (
    <div className="pi">
      {d.address && <div className="pi-row"><Ico d={PIN} /><span>{d.address}</span>
        <button type="button" onClick={copy}>{copied ? '복사됨' : '복사'}</button></div>}
      {(d.hours || d.rest) && <div className="pi-row"><Ico d={CLOCK} /><span>
        {d.hours && <span className="pi-pre">{d.hours}</span>}
        {d.rest && <small>쉬는 날 · {d.rest}</small>}
      </span></div>}
      {phones.length > 0 && <div className="pi-row"><Ico d={PHONE} /><span>
        {phones.map(p => <a key={p} href={`tel:${p.replace(/[^\d+]/g, '')}`}>{p}</a>)}
      </span></div>}
      {d.homepage && <div className="pi-row"><Ico d={HOME} /><span><a href={d.homepage} target="_blank" rel="noopener" className="plain">홈페이지</a></span></div>}
      {d.lat != null && d.lon != null && <>
        {showMap && <div ref={box} className="pi-map" role="img" aria-label={`${name} 위치 지도`} />}
        <a className="pi-kakao" href={`https://map.kakao.com/link/map/${encodeURIComponent(name)},${d.lat},${d.lon}`} target="_blank" rel="noopener">{showMap ? '카카오맵에서 크게 보기 ›' : '카카오맵에서 위치 보기 ›'}</a>
      </>}
    </div>
  )
}
