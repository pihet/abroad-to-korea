import { useEffect, useMemo, useRef, useState } from 'react'
import { api, ORIGINS, PRIORITY_LABEL, type AnalyzeResponse, type Candidate, type Crop, type DemoPhoto, type Origin, type Priority, type RecommendResponse } from './api'
import { CropStep } from './components/CropStep'

// 인스타그램형 "사진으로 찾기": 사진 고르기 → (선택) 영역 자르기 → 결과 피드.
// 결과 게시물은 좌우로 넘기면 후보 사진 ↔ 내 사진. 태그·우선순위·출발지는 결과 위 칩으로 바로 바꾼다.

export type Source = { kind: 'file'; file: Blob; url: string; sourceAttractionId?: string } | { kind: 'demo'; photo: DemoPhoto; url: string }
type Stage = 'pick' | 'crop' | 'result'
const PAGE = 5
const MAX = 30

// 자른 영역을 결과의 "내 사진"으로 보여 준다 (사용자 사진이므로 잘라도 된다)
async function croppedPreview(url: string, crop: Crop | null): Promise<string> {
  if (!crop) return url
  const img = new Image()
  img.src = url
  await img.decode()
  const c = document.createElement('canvas')
  c.width = Math.round(crop.w); c.height = Math.round(crop.h)
  c.getContext('2d')!.drawImage(img, crop.x, crop.y, crop.w, crop.h, 0, 0, c.width, c.height)
  return c.toDataURL('image/jpeg', 0.9)
}

export function FeedSearch({ start, saved, onToggleSave, onOpen }: {
  start: Source | null  // 지역 상세의 "이 사진과 닮은 다른 곳 찾기"로 들어온 사진
  saved: string[]; onToggleSave: (key: string) => void; onOpen: (key: string) => void
}) {
  const [stage, setStage] = useState<Stage>('pick')
  const [source, setSource] = useState<Source | null>(null)
  const [preview, setPreview] = useState('')
  const [analysis, setAnalysis] = useState<AnalyzeResponse | null>(null)
  const [kept, setKept] = useState<string[]>([])
  const [priority, setPriority] = useState<Priority>('visual')
  const [origin, setOrigin] = useState<Origin | null>(null)
  const [res, setRes] = useState<RecommendResponse | null>(null)
  const [list, setList] = useState<Candidate[]>([])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [demos, setDemos] = useState<DemoPhoto[]>([])
  const [q, setQ] = useState('')
  const [votes, setVotes] = useState<Record<string, 1 | -1>>({})

  useEffect(() => { api.demoPhotos().then(setDemos).catch(e => setErr(e.message)) }, [])
  const shownDemos = useMemo(() => {
    const f = q.trim().toLowerCase()
    return demos.filter(d => !f || `${d.place_name} ${d.scene_label}`.toLowerCase().includes(f)).slice(0, 48)
  }, [demos, q])

  const analyze = async (s: Source, crop: Crop | null) => {
    setBusy(true); setErr(null)
    try {
      const a = await api.analyze(s.kind === 'file' ? { file: s.file, crop, sourceAttractionId: s.sourceAttractionId }
                                                     : { demoPhotoId: s.photo.photo_id, crop })
      setAnalysis(a); setKept(a.scene_tags.map(t => t.tag))
      setPreview(await croppedPreview(s.url, crop))
      setStage('result'); window.scrollTo(0, 0)
    } catch (e) { setErr((e as Error).message) } finally { setBusy(false) }
  }

  // 지역 상세에서 넘어온 국내 사진은 자르기 없이 바로 찾는다
  useEffect(() => { if (start) { setSource(start); analyze(start, null) } }, [start]) // eslint-disable-line react-hooks/exhaustive-deps

  // 태그·우선순위·출발지가 바뀌면 다시 분석하지 않고 정렬만 다시 받는다
  useEffect(() => {
    if (stage !== 'result' || !analysis) return
    setBusy(true); setErr(null)
    api.recommend({ query_id: analysis.query_id, priority, origin, kept_tags: kept, limit: PAGE, offset: 0 })
      .then(r => { setRes(r); setList(r.candidates) })
      .catch(e => setErr(e.message))
      .finally(() => setBusy(false))
  }, [stage, analysis, priority, origin, kept])

  const more = async () => {
    if (!analysis) return
    setBusy(true)
    try {
      const r = await api.recommend({ query_id: analysis.query_id, priority, origin, kept_tags: kept, limit: PAGE, offset: list.length })
      setList([...list, ...r.candidates])
    } catch (e) { setErr((e as Error).message) } finally { setBusy(false) }
  }

  const onFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    e.target.value = ''
    if (!f) return
    // HEIC 는 브라우저가 type 을 비워 두기도 해서 확장자로도 본다
    const heic = /^image\/hei[cf]/.test(f.type) || /\.hei[cf]$/i.test(f.name)
    if (!f.type.startsWith('image/') && !heic) { setErr('사진 파일만 올릴 수 있습니다.'); return }
    if (f.size > 15 * 1024 * 1024) { setErr('15MB보다 작은 사진을 골라 주세요.'); return }
    setErr(null)
    try {
      const file = heic ? await api.convert(f) : f  // 크롬은 HEIC 를 못 띄워 서버에서 JPEG 로 바꾼다
      setSource({ kind: 'file', file, url: URL.createObjectURL(file) }); setStage('crop')
    } catch (x) { setErr((x as Error).message) }
  }

  // 국내 관광지 사진으로 다시 찾기: 출발 관광지를 넘겨 그 시군구가 다시 1위로 나오지 않게 한다
  const searchFrom = async (c: Candidate) => {
    try {
      const blob = await fetch(c.attraction.image_url).then(r => r.blob())
      const s: Source = { kind: 'file', file: blob, url: URL.createObjectURL(blob), sourceAttractionId: c.attraction.id }
      setSource(s); await analyze(s, null)
    } catch { setErr('이 사진을 불러오지 못했습니다.') }
  }
  const vote = (c: Candidate, v: 1 | -1) => {
    if (!analysis) return
    setVotes({ ...votes, [c.sigungu.key]: v })
    api.feedback({ query_id: analysis.query_id, sigungu_key: c.sigungu.key, attraction_id: c.attraction.id, value: v }).catch(() => {})
  }

  if (stage === 'crop' && source) return (
    <div className="ig-crop">
      <CropStep url={source.url} busy={busy} onBack={() => setStage('pick')} onDone={c => analyze(source, c)} />
      {err && <p className="ig-err" role="alert">{err}</p>}
    </div>
  )

  if (stage === 'result' && analysis) return (
    <div className="ig-res">
      <section className="ig-mine">
        <img src={preview} alt="내 사진" />
        <div>
          <b>내 사진과 닮은 국내 여행지</b>
          <small>사진이 닮은 {res?.total_candidates ?? '…'}곳 중에서{analysis.excluded_sigungu ? ` · 출발 지역(${analysis.excluded_sigungu.name}) 제외` : ''}</small>
          <button type="button" className="ig-link" onClick={() => setStage('pick')}>다른 사진으로 찾기</button>
        </div>
      </section>
      <div className="ig-pills" role="group" aria-label="정렬">
        {(Object.keys(PRIORITY_LABEL) as Priority[]).map(p => (
          <button key={p} type="button" aria-pressed={priority === p} onClick={() => { setPriority(p); if (p === 'near' && !origin) setOrigin('서울') }}>{PRIORITY_LABEL[p]}</button>
        ))}
        {priority === 'near' && (
          <select aria-label="출발지" value={origin ?? '서울'} onChange={e => setOrigin(e.target.value as Origin)}>
            {ORIGINS.map(o => <option key={o} value={o}>{o}에서</option>)}
          </select>
        )}
      </div>
      <div className="ig-pills tags" role="group" aria-label="장면 태그 (비슷한 점·다른 점 설명에 씀)">
        {analysis.scene_tags.map(t => {
          const on = kept.includes(t.tag)
          return <button key={t.tag} type="button" aria-pressed={on} onClick={() => setKept(on ? kept.filter(k => k !== t.tag) : [...kept, t.tag])}>#{t.tag}</button>
        })}
      </div>
      {err && <p className="ig-err" role="alert">{err}</p>}
      {!res && <p className="ig-wait">닮은 곳을 찾는 중…</p>}
      <ul className="ig-feed">
        {list.map(c => <ResultPost key={c.sigungu.key} c={c} mine={preview} priority={priority}
          saved={saved.includes(c.sigungu.key)} voted={votes[c.sigungu.key]}
          onSave={() => onToggleSave(c.sigungu.key)} onOpen={() => onOpen(c.sigungu.key)}
          onVote={v => vote(c, v)} onAgain={() => searchFrom(c)} />)}
      </ul>
      {res && list.length < Math.min(MAX, res.total_candidates) && (
        <button type="button" className="ig-more" disabled={busy} onClick={more}>{busy ? '불러오는 중…' : '닮은 곳 더 보기'}</button>
      )}
      {list.length > 0 && <p className="ig-foot">사진·정보 한국관광공사 TourAPI (공공누리 제1·3유형) · 자세한 출처는 각 지역 상세 맨 아래</p>}
      {source?.kind === 'demo' && (
        <p className="ig-foot">내 사진: {source.photo.place_name} · {source.photo.artist} · <a href={source.photo.license_url} target="_blank" rel="noopener">{source.photo.license}</a> · Wikimedia Commons</p>
      )}
    </div>
  )

  return (
    <div className="ig-pick">
      <section className="ig-upload">
        <b>가고 싶은 해외 사진을 올려 보세요</b>
        <small>분위기가 닮은 국내 여행지를 찾아 드려요 · 올린 사진은 저장하지 않습니다</small>
        <div>
          <label className="ig-btn primary"><input type="file" accept="image/*,.heic,.heif" onChange={onFile} />앨범에서 고르기</label>
          <label className="ig-btn"><input type="file" accept="image/*" capture="environment" onChange={onFile} />사진 찍기</label>
        </div>
        <small>JPG·PNG·WEBP·HEIC, 15MB 이하</small>
      </section>
      {err && <p className="ig-err" role="alert">{err}</p>}
      <div className="ig-search">
        <input placeholder="예시 사진 검색 (교토, 해변…)" value={q} onChange={e => setQ(e.target.value)} aria-label="예시 사진 검색" />
      </div>
      <div className="ig-grid">
        {shownDemos.map(d => (
          <button key={d.photo_id} type="button" onClick={() => { setSource({ kind: 'demo', photo: d, url: d.image_url }); setStage('crop'); window.scrollTo(0, 0) }}
                  aria-label={`${d.place_name} ${d.scene_label}`}>
            <img src={d.image_url} alt="" loading="lazy" />
          </button>
        ))}
      </div>
      <p className="ig-foot">예시 사진: Wikimedia Commons (사진별 저작자·라이선스는 결과 화면에 표시)</p>
    </div>
  )
}

const Heart = ({ on }: { on: boolean }) => <svg viewBox="0 0 24 24" className={on ? 'ic fill' : 'ic'} aria-hidden="true"><path d="M12 20s-7-4.4-9.2-8.6C1.2 8.2 3 4.5 6.6 4.5c2.2 0 3.6 1.3 5.4 3.3 1.8-2 3.2-3.3 5.4-3.3 3.6 0 5.4 3.7 3.8 6.9C19 15.6 12 20 12 20z" /></svg>

// 결과 게시물: 좌우로 넘기는 사진 2장 (후보 · 내 사진) + 근거 설명
function ResultPost({ c, mine, priority, saved, voted, onSave, onOpen, onVote, onAgain }: {
  c: Candidate; mine: string; priority: Priority; saved: boolean; voted: 1 | -1 | undefined
  onSave: () => void; onOpen: () => void; onVote: (v: 1 | -1) => void; onAgain: () => void
}) {
  const track = useRef<HTMLDivElement>(null)
  const [slide, setSlide] = useState(0)
  const go = (i: number) => track.current?.scrollTo({ left: i * track.current.clientWidth, behavior: 'smooth' })
  const moved = priority !== 'visual' && c.rank !== c.visual_rank
  return (
    <li className="post">
      <div className="post-head">
        <span className="rank-badge">{c.rank}</span>
        <span><b>{c.attraction.name}</b><small>{c.sigungu.sido} {c.sigungu.name}{c.distance_km != null ? ` · ${c.distance_km}km` : ''}</small></span>
      </div>
      <div className="carousel">
        <div className="track" ref={track} onScroll={e => setSlide(Math.round(e.currentTarget.scrollLeft / e.currentTarget.clientWidth))}>
          <figure><img src={c.attraction.image_url} alt={c.attraction.name} loading="lazy" /></figure>
          <figure><img src={mine} alt="내 사진" /></figure>
        </div>
        {slide === 0 && <button type="button" className="nav next" onClick={() => go(1)} aria-label="내 사진과 비교">›</button>}
        {slide === 1 && <button type="button" className="nav prev" onClick={() => go(0)} aria-label="후보 사진으로">‹</button>}
        <div className="dots"><span>{slide === 0 ? c.sigungu.name : '내 사진'}</span><i className={slide === 0 ? 'on' : ''} /><i className={slide === 1 ? 'on' : ''} /></div>
      </div>
      <div className="post-act">
        <button type="button" aria-pressed={saved} onClick={onSave} aria-label="저장"><Heart on={saved} /></button>
        <button type="button" className="txt" aria-pressed={voted === 1} onClick={() => onVote(1)}>닮았어요</button>
        <button type="button" className="txt" aria-pressed={voted === -1} onClick={() => onVote(-1)}>별로예요</button>
        <button type="button" className="post-more" onClick={onOpen}>{c.sigungu.name} 자세히</button>
      </div>
      <p className="post-cap">
        <b>사진 유사도 {c.visual_rank}위</b> / 30 · CLIP {c.visual.similarity.toFixed(2)}{moved && ` · 정렬 반영 ${c.visual_rank}위 → ${c.rank}위`}
      </p>
      {c.similar_tags.length > 0 && <p className="post-cap tags">비슷한 점 {c.similar_tags.map(t => <span key={t}>#{t}</span>)}</p>}
      {c.different_tags.length > 0 && <p className="post-cap tags diff">다른 점 {c.different_tags.map(t => <span key={t}>#{t}</span>)}</p>}
      <p className="post-links">
        <button type="button" className="ig-link" onClick={onAgain}>이 사진으로 다시 찾기</button>
        {c.map_links.kakao && <a href={c.map_links.kakao} target="_blank" rel="noopener">카카오맵</a>}
        {c.map_links.naver && <a href={c.map_links.naver} target="_blank" rel="noopener">네이버지도</a>}
      </p>
      <small className="post-credit">비슷한 점·다른 점은 장면 태그 자동 비교 (참고용)</small>
    </li>
  )
}
