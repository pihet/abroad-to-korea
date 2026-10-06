import { matches, type FilterKey, type Filters, type RegionsResponse } from '../api'

// 시도 · 조건 칩. 칩마다 "지금 고른 다른 조건과 함께 걸었을 때" 남는 시군구 수를 보여 준다.
export function FilterBar({ value, onChange, regions, compact }: {
  value: Filters; onChange: (f: Filters) => void; regions: RegionsResponse | null; compact?: boolean
}) {
  const rows = regions?.regions ?? []
  const count = (f: Filters) => rows.filter(r => matches(r, f)).length
  const toggle = (k: FilterKey) =>
    onChange({ ...value, keys: value.keys.includes(k) ? value.keys.filter(x => x !== k) : [...value.keys, k] })
  const left = count(value)

  return (
    <div className={compact ? 'filterbar compact' : 'filterbar'}>
      <fieldset>
        <legend>어떤 곳이면 좋을까요 <small>(여러 개 고를 수 있어요)</small></legend>
        <div className="fchips">
          {regions?.filters.filter(f => f.key !== 'mild' && f.key !== 'calm').map(f => {  // 날씨 칩은 여행 월이 있어야 성립해서, 방문객 칩은 혼잡도를 지역 상세에서만 보여 주기로 해서 뺐다
            const on = value.keys.includes(f.key)
            const n = count({ ...value, keys: on ? value.keys : [...value.keys, f.key] })
            return (
              <button key={f.key} type="button" aria-pressed={on} disabled={!on && n === 0} title={f.basis} onClick={() => toggle(f.key)}>
                {f.label} <span className="n">{n}</span>
              </button>
            )
          })}
          <select aria-label="지역(시도)" value={value.sido ?? ''} onChange={e => onChange({ ...value, sido: e.target.value || null })}>
            <option value="">전국</option>
            {regions?.sidos.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
      </fieldset>
      {regions && (
        <p className={left ? 'fleft' : 'fleft none'} role="status">
          {left ? <>조건에 맞는 시군구 <b>{left}</b>곳 / {rows.length}</> : '조건에 맞는 시군구가 없습니다. 조건을 하나 빼 보세요.'}
        </p>
      )}
      {!compact && regions && value.keys.length > 0 && (
        <ul className="fbasis">
          {regions.filters.filter(f => value.keys.includes(f.key)).map(f => <li key={f.key}><b>{f.label}</b>: {f.basis}</li>)}
        </ul>
      )}
    </div>
  )
}
