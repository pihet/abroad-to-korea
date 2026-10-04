import type { Candidate, Priority } from '../api'
import { MonthlyChart } from './MonthlyChart'

export function CandidateCard({ c, originUrl, month, priority, saved, comparing, onSave, onCompare, onFeedback, onSearchSimilar, voted }: {
  c: Candidate; originUrl: string; month: number; priority: Priority
  saved: boolean; comparing: boolean; voted: 1 | -1 | undefined
  onSave: () => void; onCompare: () => void; onFeedback: (v: 1 | -1) => void; onSearchSimilar: () => void
}) {
  const cg = c.congestion, cl = c.climate
  const moved = c.rank !== c.visual_rank
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

        <div className="facts">
          <div className={priority === 'crowd' ? 'fact on' : 'fact'}>
            <span className="lab">{month}월 혼잡도</span>
            {cg ? <>
              <b>{cg.index}<small> / 평소 100</small></b>
              <small className="basis">{cg.basis === 'forecast' ? `예측 ${cg.basis_month}` : `실측 ${cg.basis_month}`} · 외지인 약 {Math.round(cg.visitors / 10000).toLocaleString()}만 명</small>
            </> : <b className="na">자료 없음</b>}
          </div>
          <div className={priority === 'season' ? 'fact on' : 'fact'}>
            <span className="lab">{month}월 날씨</span>
            {cl ? <><b>{cl.temp_c}°C<small> · 비 {cl.rain_days}일</small></b><small className="basis">2021~2025년 평균</small></> : <b className="na">자료 없음</b>}
          </div>
          {c.distance_km != null && (
            <div className={priority === 'near' ? 'fact on' : 'fact'}>
              <span className="lab">거리</span><b>{c.distance_km}<small> km</small></b><small className="basis">직선거리</small>
            </div>
          )}
        </div>
        {cg && (
          <div className="chart">
            <span className="lab">최근 12개월 혼잡도 (외지인 방문 실측, {cg.monthly[0].month} ~ {cg.monthly[11].month})</span>
            <MonthlyChart points={cg.monthly} month={month} />
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
        </div>
      </div>
    </article>
  )
}
