import { useEffect, useMemo, useState } from 'react'
import { api, type DemoPhoto } from '../api'

export type Source = { kind: 'file'; file: Blob; url: string; sourceAttractionId?: string } | { kind: 'demo'; photo: DemoPhoto; url: string }

export function PhotoStep({ onPick, onBrowse, filterBar }: { onPick: (s: Source) => void; onBrowse: () => void; filterBar: React.ReactNode }) {
  const [demos, setDemos] = useState<DemoPhoto[]>([])
  const [q, setQ] = useState('')
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => { api.demoPhotos().then(setDemos).catch(e => setErr(e.message)) }, [])
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
      <div className="hero-copy">
        <h1>가고 싶은 해외 풍경, 국내에서 찾아보세요</h1>
        <p>해외 여행지 사진을 올리면 분위기가 비슷한 국내 관광지를 찾고, 고른 달에 얼마나 붐비는지까지 함께 보여 드립니다.</p>
      </div>
      <div className="start-filters">{filterBar}</div>
      <div className="upload-row">
        <label className="upload">
          <input type="file" accept="image/*,.heic,.heif" onChange={onFile} />
          <strong>사진 올리기</strong><span>JPG·PNG·WEBP·HEIC, 15MB 이하</span>
        </label>
        <label className="upload camera">
          <input type="file" accept="image/*" capture="environment" onChange={onFile} />
          <strong>사진 찍기</strong><span>휴대폰에서 바로 촬영</span>
        </label>
        <button type="button" className="upload browse-entry" onClick={onBrowse}>
          <strong>사진 없이 둘러보기</strong><span>조건에 맞는 곳을 사진으로 훑어보기</span>
        </button>
      </div>
      {err && <p className="error" role="alert">{err}</p>}
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
