import type { MonthPoint } from '../api'

// 최근 12개월 외지인 방문자 실측. 막대 = 그달 방문자 / 12개월 평균 × 100, 가로선 = 100(평소), 고른 달 강조.
export function MonthlyChart({ points, month }: { points: MonthPoint[]; month: number }) {
  const W = 260, H = 70, top = 6, base = 52, gap = 3
  const max = Math.max(130, ...points.map(p => p.index))
  const bw = (W - gap * (points.length - 1)) / points.length
  const y = (v: number) => base - (v / max) * (base - top)
  return (
    <svg className="mchart" viewBox={`0 0 ${W} ${H}`} role="img"
         aria-label={`최근 12개월 혼잡도: ${points.map(p => `${Number(p.month.slice(5))}월 ${p.index}`).join(', ')}`}>
      <line x1={0} x2={W} y1={y(100)} y2={y(100)} className="ref" />
      {points.map((p, i) => {
        const on = Number(p.month.slice(5)) === month
        const x = i * (bw + gap)
        return (
          <g key={p.month}>
            <rect x={x} y={y(p.index)} width={bw} height={base - y(p.index)} rx={2} className={on ? 'bar on' : 'bar'}>
              <title>{`${p.month} · 혼잡도 ${p.index} · 외지인 ${p.visitors.toLocaleString()}명`}</title>
            </rect>
            <text x={x + bw / 2} y={H - 4} textAnchor="middle" className={on ? 'lab on' : 'lab'}>{Number(p.month.slice(5))}</text>
          </g>
        )
      })}
    </svg>
  )
}
