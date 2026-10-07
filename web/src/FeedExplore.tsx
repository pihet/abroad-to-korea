import { useEffect, useMemo, useState } from 'react'
import { api, type DemoPhoto } from './api'

// 탐색: 해외 사진(위키미디어 커먼즈 213장)을 대륙별로 펼쳐 보고, 누르면 그 사진과 닮은 국내 여행지를 찾는다.
// 커먼즈 사진은 CC BY·BY-SA·CC0·퍼블릭 도메인뿐이라(변경 금지 없음) 격자에 맞춰 자르고 이름표를 얹는다.
const CONTINENTS = ['전체', '아시아', '유럽', '아메리카', '오세아니아', '아프리카']

export function FeedExplore({ onPick }: { onPick: (p: DemoPhoto) => void }) {
  const [photos, setPhotos] = useState<DemoPhoto[] | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [cont, setCont] = useState('전체')
  useEffect(() => { api.demoPhotos().then(setPhotos).catch(e => setErr(e.message)) }, [])
  const counts = useMemo(() => {
    const c: Record<string, number> = { 전체: photos?.length ?? 0 }
    for (const p of photos ?? []) c[p.continent] = (c[p.continent] ?? 0) + 1
    return c
  }, [photos])
  const shown = (photos ?? []).filter(p => cont === '전체' || p.continent === cont)

  if (err) return <p className="ig-err">{err}</p>
  if (!photos) return <p className="ig-wait">불러오는 중…</p>
  return (
    <div className="igx">
      <div className="igx-head"><b>해외 풍경 둘러보기</b><small>사진을 누르면 분위기가 닮은 국내 여행지를 찾아 드려요</small></div>
      <nav className="igx-chips" aria-label="대륙" data-drag>
        {CONTINENTS.filter(c => counts[c]).map(c => (
          <button key={c} type="button" aria-pressed={cont === c} onClick={() => { setCont(c); window.scrollTo(0, 0) }}>{c} <small>{counts[c]}</small></button>
        ))}
      </nav>
      <div className="igx-grid">
        {shown.map((p, i) => (
          <button key={p.photo_id} type="button" className={i % 10 === 3 ? 'big' : ''} onClick={() => onPick(p)}
                  aria-label={`${p.country} ${p.place_name} ${p.scene_label}, 이 사진과 닮은 국내 여행지 찾기`}>
            <img src={p.image_url} alt="" loading="lazy" />
            <span><b>{p.country} · {p.place_name}</b><small>{p.scene_label}</small></span>
          </button>
        ))}
      </div>
      <p className="ig-foot">사진 Wikimedia Commons (사진별 저작자·라이선스는 사진을 고른 뒤 결과 화면 맨 아래) · 격자에서는 사진 가운데를 잘라 보여 줍니다</p>
    </div>
  )
}
