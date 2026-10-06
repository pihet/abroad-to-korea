import { useEffect, useState } from 'react'
import { rainApi, type RainResult } from '../api'

const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
const addDays = (d: Date, n: number) => { const x = new Date(d); x.setDate(x.getDate() + n); return x }
const WEEK = ['일', '월', '화', '수', '목', '금', '토']
const label = (s: string) => { const d = new Date(`${s}T00:00`); return `${d.getMonth() + 1}/${d.getDate()}(${WEEK[d.getDay()]})` }

// 여행 날짜를 고르면 그 기간에 비가 올지: 16일 안은 일기예보, 그보다 멀면 과거 5년 같은 날짜 기록.
// 두 값은 성격이 달라서 문장과 표시를 다르게 쓴다 (과거 기록은 예측이 아니다).
export function RainCheck({ regionKey }: { regionKey: string }) {
  const today = new Date()
  const [start, setStart] = useState(iso(addDays(today, 3)))
  const [end, setEnd] = useState(iso(addDays(today, 5)))
  const [r, setR] = useState<RainResult | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    setR(null); setErr(null)
    if (!start || !end) return
    rainApi(regionKey, start, end).then(setR).catch(e => setErr(e.message))
  }, [regionKey, start, end])

  return (
    <div className="rain">
      <div className="rain-pick">
        <label>가는 날<input type="date" value={start} onChange={e => { setStart(e.target.value); if (e.target.value > end) setEnd(e.target.value) }} /></label>
        <span aria-hidden="true">~</span>
        <label>오는 날<input type="date" value={end} min={start} onChange={e => setEnd(e.target.value)} /></label>
      </div>
      {err && <p className="error">{err}</p>}
      {!r && !err && <p className="fine">확인하는 중…</p>}
      {r?.basis === 'forecast' && <>
        <p className="rain-say">{r.rainy_days ? <>이 기간 중 <b>{r.rainy_days}일</b>은 비 예보가 있어요.</> : <>이 기간에는 <b>비 예보가 없어요.</b></>}</p>
        <ul className="rain-days">
          {r.days.map(d => {
            const wet = (d.prob ?? 0) >= 50 || (d.rain_mm ?? 0) >= 1
            return <li key={d.date} className={wet ? 'wet' : ''}><b>{label(d.date)}</b><span>{wet ? '비' : '맑음·흐림'}</span>
              <small>강수확률 {d.prob ?? '–'}% · {d.rain_mm ?? '–'}mm</small></li>
          })}
        </ul>
        <p className="fine">Open-Meteo 일기예보 (오늘부터 16일까지만 제공) · {r.rule}</p>
      </>}
      {r?.basis === 'history' && <>
        <p className="rain-say">
          아직 일기예보가 나오지 않은 날짜예요. 지난 {r.n_years}년({r.years}) 중 <b>{r.years_with_rain}년</b>은 이 기간에 비 온 날이 있었고,
          한 해 평균 <b>{r.avg_rainy_days}일</b> 비가 왔어요.
        </p>
        <ul className="rain-days">
          {r.days.map(d => (
            <li key={d.date} className={d.rainy_years * 2 > d.years ? 'wet' : ''}><b>{label(d.date)}</b>
              <span>{d.years}년 중 {d.rainy_years}년 비</span></li>
          ))}
        </ul>
        <p className="fine">과거 기록이지 올해 예보가 아닙니다. Open-Meteo 2021~2025년 일별 기록 · {r.rule}. 날짜가 16일 안으로 들어오면 일기예보로 바뀝니다.</p>
      </>}
    </div>
  )
}
