import { useState, type FormEvent } from 'react'
import { api, type Candidate, type NaturalRecommendResponse } from './api'

const EXAMPLES = ['조용한 바다 마을', '서울에서 가까운 산과 숲', '10월에 날씨 좋은 시골']

// 그 달 혼잡도(평소 100 대비)를 칩 한 단어로. 지역 상세(FeedRegion crowdWord)와 같은 ±5 기준. 달을 안 정하면 없음
const crowdChip = (c: Candidate) => {
  const i = c.congestion?.index
  return i == null ? null : i >= 105 ? '붐빔' : i <= 95 ? '한산' : '보통'
}

export function FeedAsk({ onOpen, saved, onToggleSave }: {
  onOpen: (key: string) => void; saved: string[]; onToggleSave: (key: string) => void
}) {
  const [query, setQuery] = useState('')
  const [result, setResult] = useState<NaturalRecommendResponse | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (event?: FormEvent, example?: string) => {
    event?.preventDefault()
    const text = (example ?? query).trim()
    if (text.length < 2 || busy) return
    setQuery(text); setBusy(true); setError(null)
    try { setResult(await api.naturalRecommend(text)) }
    catch (e) { setError(e instanceof Error ? e.message : '추천을 불러오지 못했습니다.') }
    finally { setBusy(false) }
  }

  return <section className="ask">
    <div className="ask-head">
      <b>어떤 여행을 찾으세요?</b>
      <p>사진 없이 원하는 분위기와 출발지, 달을 문장으로 적어보세요.</p>
      <div>{EXAMPLES.map(example => <button type="button" key={example} onClick={() => submit(undefined, example)}>{example}</button>)}</div>
    </div>

    <form className="ask-form" onSubmit={submit}>
      <label htmlFor="travel-query">여행 요청</label>
      <textarea id="travel-query" value={query} maxLength={300} rows={3} onChange={event => setQuery(event.target.value)}
        placeholder="예: 부산에서 가까운 조용한 바다 마을" />
      <button type="submit" disabled={busy || query.trim().length < 2}>{busy ? '찾는 중…' : '추천받기'}</button>
    </form>

    {error && <p className="ask-error">{error}</p>}
    {result && <>
      <div className="ask-summary">
        <b>{result.message}</b>
        <div>{result.interpretation.scene_tags.slice(0, 4).map(tag => <span key={tag}>#{tag}</span>)}</div>
      </div>
      <ol className="ask-cards">
        {result.candidates.map(c => {
          const crowd = crowdChip(c), on = saved.includes(c.sigungu.key)
          return <li key={c.sigungu.key} className={c.rank === 1 ? 'top' : undefined}>
            <button type="button" className="ask-card" onClick={() => onOpen(c.sigungu.key)}>
              <img src={c.attraction.image_url} alt={c.attraction.name} loading="lazy" />
              <span className="ask-copy">
                <b><span className="ask-rank">{c.rank}</span>{c.attraction.name}</b>
                <small>{c.sigungu.sido} {c.sigungu.name}{c.distance_km != null ? ` · ${c.distance_km}km` : ''}</small>
                <span className="ask-chips">
                  {crowd && <i className={`crowd ${crowd === '붐빔' ? 'busy' : crowd === '한산' ? 'calm' : ''}`}>
                    <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="9" cy="8" r="3.2" /><path d="M3 20c0-3.3 2.7-5.5 6-5.5s6 2.2 6 5.5" /><path d="M16 5.2a3 3 0 0 1 0 5.6M18 14.8c1.8.7 3 2.3 3 4.7" /></svg>{crowd}</i>}
                  {c.similar_tags.slice(0, 1).map(tag => <i key={tag}>{tag}</i>)}
                  <i className="more">상세보기 ›</i>
                </span>
              </span>
            </button>
            <button type="button" className="ask-save" aria-pressed={on} aria-label={on ? '저장 취소' : '저장'} onClick={() => onToggleSave(c.sigungu.key)}>
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 20s-7-4.4-9.2-8.6C1.2 8.2 3 4.5 6.6 4.5c2.2 0 3.6 1.3 5.4 3.3 1.8-2 3.2-3.3 5.4-3.3 3.6 0 5.4 3.7 3.8 6.9C19 15.6 12 20 12 20z" /></svg>
            </button>
          </li>
        })}
      </ol>
    </>}
  </section>
}
