import { useState } from 'react'
import type { MonthRow } from '../api'

// "언제 가면 좋을까": 같은 월 축을 쓰는 작은 그래프 세 개(기온 · 비 온 날 · 혼잡도).
// 단위가 다른 값을 한 그래프의 두 축에 겹치지 않는다. 고른 달은 세로 띠로 강조, 마우스를 올린 달은 세 값을 한 번에 보여 준다.
const W = 640, PAD_L = 44, PAD_R = 12, ROW_H = 74, GAP = 22, TOP = 8
const COL = (W - PAD_L - PAD_R) / 12

type Row = { key: 'temp' | 'rain' | 'crowd'; title: string; unit: string; get: (m: MonthRow) => number | null; kind: 'line' | 'bar'; ref?: number }
const ROWS: Row[] = [
  { key: 'temp', title: '평균기온', unit: '°C', get: m => m.temp_c, kind: 'line' },
  { key: 'rain', title: '비 온 날', unit: '일', get: m => m.rain_days, kind: 'bar' },
  { key: 'crowd', title: '혼잡도 (평소 100)', unit: '', get: m => m.congestion_index, kind: 'bar', ref: 100 },
]

export function MonthsChart({ months, month, onPick }: { months: MonthRow[]; month: number; onPick?: (m: number) => void }) {
  const [hover, setHover] = useState<number | null>(null)
  const H = TOP + ROWS.length * (ROW_H + GAP) + 18
  const cx = (i: number) => PAD_L + COL * i + COL / 2
  const shown = hover ?? month
  const cur = months.find(m => m.month === shown)

  return (
    <div className="mchart3">
      <div className="mchart3-read" aria-live="polite">
        <b>{shown}월</b>
        <span>평균기온 {cur?.temp_c ?? '–'}°C</span>
        <span>비 온 날 {cur?.rain_days ?? '–'}일</span>
        <span>혼잡도 {cur?.congestion_index ?? '–'}{cur?.basis ? ` (${cur.basis === 'forecast' ? '예측' : '실측'} ${cur.basis_month})` : ''}</span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="월별 평균기온, 비 온 날, 혼잡도" onMouseLeave={() => setHover(null)}>
        <rect x={PAD_L + COL * (month - 1)} y={0} width={COL} height={H - 18} className="pick-band" />
        {hover && hover !== month && <rect x={PAD_L + COL * (hover - 1)} y={0} width={COL} height={H - 18} className="hover-band" />}
        {ROWS.map((r, ri) => {
          const y0 = TOP + ri * (ROW_H + GAP) + 14, y1 = y0 + ROW_H - 14
          const vals = months.map(r.get).filter((v): v is number => v != null)
          let lo = Math.min(0, ...vals), hi = Math.max(...vals, r.ref ?? -Infinity)
          if (r.kind === 'line') { lo = Math.floor(Math.min(...vals) / 5) * 5; hi = Math.ceil(Math.max(...vals) / 5) * 5 }
          if (hi === lo) hi = lo + 1
          const Y = (v: number) => y1 - (v - lo) / (hi - lo) * (y1 - y0)
          const pts = months.map((m, i) => [cx(i), r.get(m)] as const).filter(([, v]) => v != null) as [number, number][]
          return (
            <g key={r.key}>
              <text x={PAD_L} y={y0 - 6} className="row-title">{r.title}</text>
              <line x1={PAD_L} x2={W - PAD_R} y1={y1} y2={y1} className="axis" />
              <text x={PAD_L - 6} y={y1 + 4} className="tick" textAnchor="end">{lo}</text>
              <text x={PAD_L - 6} y={y0 + 4} className="tick" textAnchor="end">{hi}</text>
              {r.ref != null && <><line x1={PAD_L} x2={W - PAD_R} y1={Y(r.ref)} y2={Y(r.ref)} className="ref" />
                <text x={W - PAD_R} y={Y(r.ref) - 4} className="tick" textAnchor="end">평소</text></>}
              {r.kind === 'bar' && months.map((m, i) => {
                const v = r.get(m); if (v == null) return null
                const on = m.month === month, top = Math.min(Y(v), y1 - 1), bw = COL * 0.56
                return <path key={m.month} className={on ? 'bar on' : 'bar'}
                  d={`M${cx(i) - bw / 2},${y1} V${top + 4} q0,-4 4,-4 H${cx(i) + bw / 2 - 4} q4,0 4,4 V${y1} Z`} />
              })}
              {r.kind === 'line' && <>
                <polyline points={pts.map(([x, v]) => `${x},${Y(v)}`).join(' ')} className="line" />
                {pts.map(([x, v], i) => <circle key={i} cx={x} cy={Y(v)} r={months[i]?.month === month ? 5 : 3} className={months[i]?.month === month ? 'dot on' : 'dot'} />)}
              </>}
            </g>
          )
        })}
        {months.map((m, i) => (
          <g key={m.month}>
            <text x={cx(i)} y={H - 4} textAnchor="middle" className={m.month === shown ? 'mlab on' : 'mlab'}>{m.month}</text>
            <rect x={PAD_L + COL * i} y={0} width={COL} height={H} fill="transparent" style={{ cursor: onPick ? 'pointer' : 'default' }}
              onMouseEnter={() => setHover(m.month)} onClick={() => onPick?.(m.month)}>
              <title>{`${m.month}월 · ${m.temp_c ?? '–'}°C · 비 ${m.rain_days ?? '–'}일 · 혼잡도 ${m.congestion_index ?? '–'}`}</title>
            </rect>
          </g>
        ))}
      </svg>
    </div>
  )
}
