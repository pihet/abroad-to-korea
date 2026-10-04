import type { Tag } from '../api'

// 분석된 장면 태그. 지우거나 되살릴 수 있다. 태그는 결과의 "비슷한 점·다른 점" 설명에 쓰인다.
export function TagChips({ tags, kept, onChange }: { tags: Tag[]; kept: string[]; onChange: (k: string[]) => void }) {
  return (
    <div className="tags">
      {tags.map(t => {
        const on = kept.includes(t.tag)
        return (
          <button key={t.tag} type="button" className={on ? 'chip on' : 'chip off'} aria-pressed={on}
                  title={`CLIP 태그 점수 ${t.score}`}
                  onClick={() => onChange(on ? kept.filter(k => k !== t.tag) : [...kept, t.tag])}>
            {t.tag}<span aria-hidden="true">{on ? '×' : '+'}</span>
          </button>
        )
      })}
    </div>
  )
}
