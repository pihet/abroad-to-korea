import { useEffect, useMemo, useState } from 'react'
import { api, showcaseApi, type DemoPhoto, type Showcase } from '../api'

export type Source = { kind: 'file'; file: Blob; url: string; sourceAttractionId?: string } | { kind: 'demo'; photo: DemoPhoto; url: string }

export function PhotoStep({ onPick, onBrowse, filterBar, afterEntries }: { onPick: (s: Source) => void; onBrowse: () => void; filterBar: React.ReactNode; afterEntries?: React.ReactNode }) {
  const [demos, setDemos] = useState<DemoPhoto[]>([])
  const [q, setQ] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const [show, setShow] = useState<Showcase | null>(null)
  useEffect(() => { api.demoPhotos().then(setDemos).catch(e => setErr(e.message)) }, [])
  useEffect(() => { showcaseApi().then(setShow).catch(() => setShow(null)) }, [])
  const shown = useMemo(() => {
    const f = q.trim().toLowerCase()
    return demos.filter(d => !f || `${d.place_name} ${d.scene_label}`.toLowerCase().includes(f)).slice(0, 48)
  }, [demos, q])

  const onFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (!f) return
    // HEIC 는 브라우저가 type 을 비워 두기도 해서 확장자로도 본다
    const heic = /^image\/hei[cf]/.test(f.type) || /\.hei[cf]$/i.test(f.name)
    if (!f.type.startsWith('image/') && !heic) { setErr('사진 파일만 올릴 수 있습니다.'); return }
    if (f.size > 15 * 1024 * 1024) { setErr('15MB보다 작은 사진을 골라 주세요.'); return }
    setErr(null)
    try {
      // 크롬 등은 HEIC 를 화면에 못 띄우므로 서버에서 JPEG 로 바꿔 미리보기·자르기·분석에 쓴다
      const file = heic ? await api.convert(f) : f
      onPick({ kind: 'file', file, url: URL.createObjectURL(file) })
    } catch (x) { setErr((x as Error).message) }
  }

  return (
    <section className="step photo-step">
      <div className="hero">
        <div className="hero-copy">
          <h1>그 해외 풍경,<br />국내에도 있어요</h1>
          <p>가고 싶은 해외 여행지 사진을 올리면 분위기가 닮은 국내 관광지를 찾아 드립니다. 덜 붐비는 곳, 가까운 곳으로 다시 고를 수도 있어요.</p>
          <div className="hero-ctas">
            <label className="cta">
              <input type="file" accept="image/*,.heic,.heif" onChange={onFile} />사진 올리기
            </label>
            <label className="cta ghost-cta only-mobile">
              <input type="file" accept="image/*" capture="environment" onChange={onFile} />사진 찍기
            </label>
            <button type="button" className="cta ghost-cta" onClick={onBrowse}>사진 없이 둘러보기</button>
          </div>
          <p className="fine">JPG·PNG·WEBP·HEIC, 15MB 이하 · 올린 사진은 저장하지 않습니다</p>
        </div>
        {show && (
          <figure className="hero-pair" aria-label="실제 추천 예시">
            <div className="hp-photo">
              <img src={show.overseas.image_url} alt={`${show.overseas.place_name} ${show.overseas.scene_label}`} />
              <figcaption><b>{show.overseas.place_name}</b><span>{show.overseas.scene_label}</span></figcaption>
            </div>
            <div className="hp-arrow" aria-hidden="true"><span>닮은 곳</span></div>
            <div className="hp-photo">
              <img src={show.domestic.attraction.image_url} alt={show.domestic.attraction.name} />
              <figcaption><b>{show.domestic.sigungu.sido.split(' ')[0]} {show.domestic.sigungu.name}</b><span>{show.domestic.attraction.name}</span></figcaption>
            </div>
            <p className="hp-note">예시 · {show.note} · 왼쪽 {show.overseas.artist} ({show.overseas.license}, Wikimedia Commons) · 오른쪽 한국관광공사 · {show.domestic.attraction.license}</p>
          </figure>
        )}
      </div>
      <details className="start-filters">
        <summary>조건을 걸고 찾기 <small>바다·산·방문객·도시/시골·지역 (선택)</small></summary>
        {filterBar}
      </details>
      {err && <p className="error" role="alert">{err}</p>}
      {afterEntries}
      <div className="demo-head">
        <h2>예시 사진으로 해 보기</h2>
        <input className="search" placeholder="여행지 검색 (교토, 해변…)" value={q} onChange={e => setQ(e.target.value)} aria-label="예시 사진 검색" />
      </div>
      <div className="demo-grid">
        {shown.map(d => (
          <button key={d.photo_id} type="button" className="demo" onClick={() => onPick({ kind: 'demo', photo: d, url: d.image_url })}>
            <span className="ph"><img src={d.image_url} alt={`${d.place_name} ${d.scene_label}`} loading="lazy" /></span>
            <b>{d.place_name}</b><small>{d.scene_label}</small>
          </button>
        ))}
      </div>
      <p className="fine">예시 사진: Wikimedia Commons (사진별 저작자·라이선스는 선택 후 표시)</p>
    </section>
  )
}
