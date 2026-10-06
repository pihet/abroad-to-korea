import { ORIGINS, PRIORITY_LABEL, type Origin, type Priority } from '../api'

export interface Cond { priority: Priority; origin: Origin | null }

const PRIORITY_HINT: Record<Priority, string> = {
  visual: '사진 유사도 순서 그대로',
  crowd: '월평균 외지인 방문이 적은 곳을 위로',
  near: '출발지에서 직선거리가 가까운 곳을 위로',
}

// 우선순위·출발지. 사진이 닮은 후보(최대 30곳) 안에서만 순서를 바꾼다. 여행 월은 FilterBar 에 있다.
export function Conditions({ value, onChange }: { value: Cond; onChange: (c: Cond) => void }) {
  return (
    <div className="conditions">
      <fieldset>
        <legend>무엇을 우선할까요</legend>
        <div className="priorities">
          {(Object.keys(PRIORITY_LABEL) as Priority[]).map(p => (
            <label key={p} className={value.priority === p ? 'on' : ''}>
              <input type="radio" name="priority" checked={value.priority === p} onChange={() => onChange({ ...value, priority: p })} />
              <b>{PRIORITY_LABEL[p]}</b><small>{PRIORITY_HINT[p]}</small>
            </label>
          ))}
        </div>
      </fieldset>
      <fieldset>
        <legend>출발지 <small>(선택)</small></legend>
        <select value={value.origin ?? ''} onChange={e => onChange({ ...value, origin: (e.target.value || null) as Origin | null })}
                aria-label="출발지">
          <option value="">{value.priority === 'near' ? '서울 (기본)' : '고르지 않음'}</option>
          {ORIGINS.map(o => <option key={o} value={o}>{o}</option>)}
        </select>
      </fieldset>
    </div>
  )
}
