import { useState } from 'react'
import type { Candidate, Priority } from '../api'
import { ActivityMap } from './ActivityMap'

export function CandidateCard({ c, originUrl, priority, saved, comparing, onSave, onCompare, onFeedback, onSearchSimilar, onOpenRegion, voted }: {
  c: Candidate; originUrl: string; priority: Priority
  saved: boolean; comparing: boolean; voted: 1 | -1 | undefined
  onSave: () => void; onCompare: () => void; onFeedback: (v: 1 | -1) => void; onSearchSimilar: () => void; onOpenRegion: () => void
}) {
  const moved = c.rank !== c.visual_rank
  const [acts, setActs] = useState(false)
  return (
    <article className="card">
      <div className="pair">
        <figure><img src={originUrl} alt="원본 사진" /><figcaption>원본</figcaption></figure>
        <figure><img src={c.attraction.image_url} alt={c.attraction.name} loading="lazy" /><figcaption className="kr">{c.sigungu.name}</figcaption></figure>
      </div>
      <div className="card-body">
        <header>
          <span className="rank">{c.rank}</span>
          <div>
            <h3>{c.attraction.name}</h3>
            <p className="where">{c.sigungu.sido} {c.sigungu.name}{c.attraction.address ? ` · ${c.attraction.address}` : ''}</p>
          </div>
        </header>
        <p className="visual">
          사진 유사도 순위 <b>{c.visual_rank}위</b> / 30 · CLIP 유사도 {c.visual.similarity.toFixed(2)}
          {moved && priority !== 'visual' && <span className="moved"> · 조건 반영으로 {c.visual_rank}위 → {c.rank}위</span>}
        </p>

        <div className="reasons">
          <div><span className="lab">비슷한 점</span>{c.similar_tags.length ? c.similar_tags.map(t => <span key={t} className="pill same">{t}</span>) : <span className="none">겹치는 태그 없음</span>}</div>
          <div><span className="lab">다른 점</span>{c.different_tags.length ? c.different_tags.map(t => <span key={t} className="pill diff">{t}</span>) : <span className="none">없음</span>}</div>
          <p className="fine">장면 태그 자동 비교 (참고용, 평가 전 기능)</p>
        </div>

        {c.distance_km != null && (
          <div className="facts">
            <div className={priority === 'near' ? 'fact on' : 'fact'}>
              <span className="lab">거리</span><b>{c.distance_km}<small> km</small></b><small className="basis">직선거리</small>
            </div>
          </div>
        )}

        <div className="links">
          {c.map_links.kakao && <a href={c.map_links.kakao} target="_blank" rel="noopener">카카오맵</a>}
          {c.map_links.naver && <a href={c.map_links.naver} target="_blank" rel="noopener">네이버지도</a>}
        </div>
        <p className="credit">사진 {c.attraction.source} · {c.attraction.license}</p>

        <div className="card-actions">
          <button type="button" aria-pressed={saved} onClick={onSave}>{saved ? '저장됨' : '저장'}</button>
          <button type="button" aria-pressed={comparing} onClick={onCompare}>{comparing ? '비교 중' : '비교 담기'}</button>
          <button type="button" aria-pressed={voted === 1} onClick={() => onFeedback(1)}>좋아요</button>
          <button type="button" aria-pressed={voted === -1} onClick={() => onFeedback(-1)}>별로예요</button>
          <button type="button" onClick={onSearchSimilar}>이 사진으로 다시 찾기</button>
          <button type="button" className="strong" onClick={onOpenRegion}>{c.sigungu.name} 자세히 보기</button>
        </div>
      </div>
      <div className="acts-panel">
        <button type="button" className="acts-toggle" aria-expanded={acts} onClick={() => setActs(!acts)}>
          {c.sigungu.name}에서 할 만한 것 <span aria-hidden="true">{acts ? '▲' : '▼'}</span>
        </button>
        {acts && <ActivityMap sigunguKey={c.sigungu.key} sigunguName={c.sigungu.name} attractionId={c.attraction.id} />}
      </div>
    </article>
  )
}
