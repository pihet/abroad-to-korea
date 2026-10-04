import { useEffect, useMemo, useState } from 'react'
import { api, type DemoPhoto } from '../api'

export type Source = { kind: 'file'; file: Blob; url: string } | { kind: 'demo'; photo: DemoPhoto; url: string }

export function PhotoStep({ onPick }: { onPick: (s: Source) => void }) {
  const [demos, setDemos] = useState<DemoPhoto[]>([])
  const [q, setQ] = useState('')
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => { api.demoPhotos().then(setDemos).catch(e => setErr(e.message)) }, [])
  const shown = useMemo(() => {
    const f = q.trim().toLowerCase()
    return demos.filter(d => !f || `${d.place_name} ${d.scene_label}`.toLowerCase().includes(f)).slice(0, 48)
  }, [demos, q])

  const onFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (!f) return
    if (!f.type.startsWith('image/')) { setErr('사진 파일만 올릴 수 있습니다.'); return }
    if (f.size > 15 * 1024 * 1024) { setErr('15MB보다 작은 사진을 골라 주세요.'); return }
    onPick({ kind: 'file', file: f, url: URL.createObjectURL(f) })
  }

  return (
    <section className="step photo-step">
      <div className="hero-copy">
        <h1>가고 싶은 해외 풍경, 국내에서 찾아보세요</h1>
        <p>해외 여행지 사진을 올리면 분위기가 비슷한 국내 관광지를 찾고, 고른 달에 얼마나 붐비는지까지 함께 보여 드립니다.</p>
      </div>
      <div className="upload-row">
        <label className="upload">
          <input type="file" accept="image/*" onChange={onFile} />
          <strong>사진 올리기</strong><span>JPG·PNG·WEBP, 15MB 이하</span>
        </label>
        <label className="upload camera">
          <input type="file" accept="image/*" capture="environment" onChange={onFile} />
          <strong>사진 찍기</strong><span>휴대폰에서 바로 촬영</span>
        </label>
      </div>
      {err && <p className="error" role="alert">{err}</p>}
      <div className="demo-head">
        <h2>또는 예시 사진으로 시작하기</h2>
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
