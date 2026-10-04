import { useRef, useState } from 'react'
import type { Crop } from '../api'

// 사진 위를 드래그해 관심 영역을 고른다. 좌표는 원본 픽셀 기준으로 바꿔 서버에 보낸다.
export function CropStep({ url, onBack, onDone, busy }: {
  url: string; onBack: () => void; onDone: (crop: Crop | null) => void; busy: boolean
}) {
  const img = useRef<HTMLImageElement>(null)
  const [box, setBox] = useState<{ x: number; y: number; w: number; h: number } | null>(null)
  const start = useRef<{ x: number; y: number } | null>(null)

  const pt = (e: React.PointerEvent) => {
    const r = img.current!.getBoundingClientRect()
    return { x: Math.min(Math.max(e.clientX - r.left, 0), r.width), y: Math.min(Math.max(e.clientY - r.top, 0), r.height) }
  }
  const down = (e: React.PointerEvent) => {
    (e.target as Element).setPointerCapture(e.pointerId)
    start.current = pt(e)
    setBox({ ...start.current, w: 0, h: 0 })
  }
  const move = (e: React.PointerEvent) => {
    if (!start.current) return
    const p = pt(e), s = start.current
    setBox({ x: Math.min(s.x, p.x), y: Math.min(s.y, p.y), w: Math.abs(p.x - s.x), h: Math.abs(p.y - s.y) })
  }
  const up = () => { start.current = null; if (box && (box.w < 12 || box.h < 12)) setBox(null) }

  const toNatural = (): Crop | null => {
    const el = img.current
    if (!el || !box) return null
    const sx = el.naturalWidth / el.clientWidth, sy = el.naturalHeight / el.clientHeight
    return { x: box.x * sx, y: box.y * sy, w: box.w * sx, h: box.h * sy }
  }

  return (
    <section className="step crop-step">
      <h2>찾고 싶은 부분을 골라 주세요</h2>
      <p className="sub">사진 위를 드래그하면 그 영역만으로 찾습니다. 전체 분위기로 찾으려면 그대로 진행하세요.</p>
      <div className="crop-stage">
        <div className="crop-wrap" onPointerDown={down} onPointerMove={move} onPointerUp={up}>
          <img ref={img} src={url} alt="선택한 사진" draggable={false} />
          {box && box.w > 0 && <div className="crop-box" style={{ left: box.x, top: box.y, width: box.w, height: box.h }} />}
        </div>
      </div>
      <div className="actions">
        <button type="button" className="ghost" onClick={onBack}>다른 사진</button>
        {box && <button type="button" className="ghost" onClick={() => setBox(null)}>영역 지우기</button>}
        <button type="button" className="primary" disabled={busy} onClick={() => onDone(box ? toNatural() : null)}>
          {busy ? '분석 중…' : box ? '이 영역으로 분석' : '사진 전체로 분석'}
        </button>
      </div>
    </section>
  )
}
