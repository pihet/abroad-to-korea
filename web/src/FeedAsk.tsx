import { useState, type FormEvent } from 'react'
import { api, type NaturalRecommendResponse } from './api'

const EXAMPLES = ['조용한 바다 마을', '서울에서 가까운 산과 숲', '10월에 날씨 좋은 시골']

export function FeedAsk({ onOpen }: { onOpen: (key: string) => void }) {
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
      <ol className="ask-results">
        {result.candidates.map(candidate => <li key={candidate.sigungu.key}>
          <button type="button" onClick={() => onOpen(candidate.sigungu.key)}>
            <span className="ask-rank">{candidate.rank}</span>
            <img src={candidate.attraction.image_url} alt={candidate.attraction.name} />
            <span className="ask-copy">
              <b>{candidate.attraction.name}</b>
              <small>{candidate.sigungu.sido} {candidate.sigungu.name}{candidate.distance_km != null ? ` · ${candidate.distance_km}km` : ''}</small>
              <em>{candidate.similar_tags.length ? candidate.similar_tags.map(tag => `#${tag}`).join(' ') : '상세보기'}</em>
            </span>
          </button>
        </li>)}
      </ol>
    </>}
  </section>
}
