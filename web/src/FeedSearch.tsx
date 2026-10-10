import { useEffect, useState } from 'react'
import { api, type AnalyzeResponse, type Candidate, type Crop, type DemoPhoto, type RecommendResponse } from './api'
import { CropStep } from './components/CropStep'
import './search.css'

// 인스타그램형 "사진으로 찾기": 사진 고르기 → (선택) 영역 자르기 → 결과 피드.
// 결과 게시물은 후보 사진 한 장(누르면 지역 상세). 정렬은 사진 유사도 순 하나, 게시물에는 내 사진과 닮은 장면 태그만 보여 준다.
// 뒤로 가기: 탐색에서 고른 사진이면 탐색으로, 직접 올린 사진이면 사진 고르기로 (휴대폰 뒤로 가기도 같다)

export type Source = { kind: 'file'; file: Blob; url: string; sourceAttractionId?: string; persist?: boolean } | { kind: 'demo'; photo: DemoPhoto; url: string }
type Stage = 'pick' | 'crop' | 'result'
const PAGE = 5
const MAX = 30
// 고르기 화면의 "이렇게 찾아 드려요" 예시: 해외 사진 → 실제 추천 1위. 국내 쪽이 공공누리 1유형(자르기 가능)인 짝만 골랐다 (2026-10-08 결과 확인)
const EXAMPLE_IDS = ['tokyo__shibuya__1.jpg', 'beijing__forbidden__1.jpg', 'cancun__beach__1.jpg', 'kyoto__arashiyama__1.jpg']
type Example = { photo: DemoPhoto; top: Candidate }
// 개인 맞춤 (로그인 사용자, 좋아요·저장 3개부터). api.ts 타입에 아직 없어 여기서 읽는다
type Personal = { on: boolean; signals: number }
const personalOf = (r: RecommendResponse | null) => (r?.model as { personal?: Personal } | undefined)?.personal
const reasonOf = (c: Candidate) => (c.rerank as { personal_reason?: string | null }).personal_reason
let examplesCache: Promise<Example[]> | null = null  // 화면을 다시 열 때마다 다시 계산하지 않게 한 번만
function loadExamples(demos: DemoPhoto[]): Promise<Example[]> {
  examplesCache ??= Promise.all(EXAMPLE_IDS.map(id => demos.find(d => d.photo_id === id)).filter((d): d is DemoPhoto => !!d).map(async photo => {
    const a = await api.analyze({ demoPhotoId: photo.photo_id })
    const r = await api.recommend({ query_id: a.query_id, priority: 'visual', limit: 1, offset: 0 })
    return { photo, top: r.candidates[0] }
  })).catch(e => { examplesCache = null; throw e })
  return examplesCache
}

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

export function FeedSearch({ start, saved, onToggleSave, onOpen, loggedIn, avatars }: {
  start: Source | null  // 탐색에서 고른 해외 사진
  saved: string[]; onToggleSave: (key: string) => void; onOpen: (key: string) => void
  loggedIn: boolean; avatars: Record<string, string | undefined>
}) {
  const [stage, setStage] = useState<Stage>('pick')
  const [source, setSource] = useState<Source | null>(null)
  const [preview, setPreview] = useState('')
  const [analysis, setAnalysis] = useState<AnalyzeResponse | null>(null)
  const [res, setRes] = useState<RecommendResponse | null>(null)
  const [list, setList] = useState<Candidate[]>([])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [examples, setExamples] = useState<Example[] | null>(null)
  const [votes, setVotes] = useState<Record<string, 1 | -1>>({})
  const [retainPhoto, setRetainPhoto] = useState(false)

  useEffect(() => { api.demoPhotos().then(loadExamples).then(setExamples).catch(() => setExamples([])) }, [])

  const [fromStart, setFromStart] = useState(false)
  // 결과에서 뒤로 가기로 돌아오면 고르기 화면으로
  useEffect(() => {
    const onPop = () => { if (!history.state?.stage) setStage(st => (st === 'result' ? 'pick' : st)) }
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])

  const analyze = async (s: Source, crop: Crop | null, viaStart = false) => {
    setBusy(true); setErr(null)
    try {
      const a = await api.analyze(s.kind === 'file' ? { file: s.file, crop, sourceAttractionId: s.sourceAttractionId,
                                                       retainPhoto: retainPhoto && s.persist !== false, storePhoto: s.persist !== false }
                                                     : { demoPhotoId: s.photo.photo_id, crop })
      setAnalysis(a)
      setPreview(await croppedPreview(s.url, crop))
      setStage('result'); setFromStart(viaStart); window.scrollTo(0, 0)
      // 결과 화면임을 방문 기록에 표시한다. 탐색에서 온 사진은 기록을 더 쌓지 않는다 (뒤로 가기 한 번에 탐색으로)
      const st = { ...(history.state ?? {}), stage: 'result' }
      if (viaStart) history.replaceState(st, ''); else history.pushState(st, '')
    } catch (e) { setErr((e as Error).message) } finally { setBusy(false) }
  }

  // 탐색에서 고른 사진은 자르기 없이 바로 찾는다
  useEffect(() => { if (start) { setSource(start); analyze(start, null, true) } }, [start]) // eslint-disable-line react-hooks/exhaustive-deps

  // 태그·우선순위·출발지가 바뀌면 다시 분석하지 않고 정렬만 다시 받는다
  useEffect(() => {
    if (stage !== 'result' || !analysis) return
    setBusy(true); setErr(null)
    api.recommend({ query_id: analysis.query_id, priority: 'visual', limit: PAGE, offset: 0 })
      .then(r => { setRes(r); setList(r.candidates) })
      .catch(e => setErr(e.message))
      .finally(() => setBusy(false))
  }, [stage, analysis])

  const more = async () => {
    if (!analysis) return
    setBusy(true)
    try {
      const r = await api.recommend({ query_id: analysis.query_id, priority: 'visual', limit: PAGE, offset: list.length })
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
      setSource({ kind: 'file', file, url: URL.createObjectURL(file), persist: true }); setStage('crop')
    } catch (x) { setErr((x as Error).message) }
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
      <div className="igs-top">
        <button type="button" onClick={() => { setStage('pick'); history.back() }}>
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 5l-7 7 7 7" /></svg>{fromStart ? '탐색으로' : '다른 사진 고르기'}
        </button>
      </div>
      <section className="ig-mine">
        <img src={preview} alt="내 사진" />
        <div>
          <b>내 사진과 닮은 국내 여행지</b>
          <small>사진이 닮은 {res?.total_candidates ?? '…'}곳 중에서{analysis.excluded_sigungu ? ` · 출발 지역(${analysis.excluded_sigungu.name}) 제외` : ''}</small>
        </div>
      </section>
      <p className="ig-mytags">{analysis.scene_tags.map(t => <span key={t.tag}>#{t.tag}</span>)}</p>
      {personalOf(res)?.on && <p className="ig-personal">내 취향 반영 중 · 좋아요·저장 {personalOf(res)!.signals}개를 바탕으로 순서를 조금 바꿨어요</p>}
      {err && <p className="ig-err" role="alert">{err}</p>}
      {!res && <p className="ig-wait">닮은 곳을 찾는 중…</p>}
      <ul className="ig-feed">
        {list.map(c => <ResultPost key={c.sigungu.key} c={c} avatar={avatars[c.sigungu.key]}
          saved={saved.includes(c.sigungu.key)} voted={votes[c.sigungu.key]}
          onSave={() => onToggleSave(c.sigungu.key)} onOpen={() => onOpen(c.sigungu.key)}
          onVote={v => vote(c, v)} />)}
      </ul>
      {res && list.length < Math.min(MAX, res.total_candidates) && (
        <button type="button" className="ig-more" disabled={busy} onClick={more}>{busy ? '불러오는 중…' : '닮은 곳 더 보기'}</button>
      )}
    </div>
  )

  return (
    <div className="ig-pick">
      <section className="ig-upload">
        <b>가고 싶은 해외 사진을 올려 보세요</b>
        <small>분위기가 닮은 국내 여행지를 찾아 드려요 · 보관을 고르지 않으면 사진은 저장하지 않습니다</small>
        <label className="ig-retain"><input type="checkbox" checked={retainPhoto} disabled={!loggedIn}
          onChange={e => setRetainPhoto(e.target.checked)} /> 계정에 사진 계속 보관{!loggedIn && ' (로그인 필요)'}</label>
        <div>
          <label className="ig-btn primary"><input type="file" accept="image/*,.heic,.heif" onChange={onFile} />앨범에서 고르기</label>
          <label className="ig-btn"><input type="file" accept="image/*" capture="environment" onChange={onFile} />사진 찍기</label>
        </div>
        <small>JPG·PNG·WEBP·HEIC, 15MB 이하</small>
      </section>
      {err && <p className="ig-err" role="alert">{err}</p>}
      <section className="ig-ex">
        <b>이렇게 찾아 드려요</b>
        {examples === null && <p className="ig-wait">예시를 찾는 중…</p>}
        <ul>
          {examples?.map(({ photo, top }) => (
            <li key={photo.photo_id}>
              <button type="button" onClick={() => { const s: Source = { kind: 'demo', photo, url: photo.image_url }; setSource(s); analyze(s, null) }}
                      aria-label={`${photo.place_name} ${photo.scene_label} 사진으로 찾은 결과 보기`}>
                <span className="pair"><img src={photo.image_url} alt="" loading="lazy" /><img src={top.attraction.image_url} alt="" loading="lazy" /></span>
                <span className="cap"><small>{photo.country} {photo.scene_label} →</small><b>{top.attraction.name}</b><small>{top.sigungu.sido.slice(0, 2)} {top.sigungu.name}</small></span>
              </button>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}

const Heart = ({ on }: { on: boolean }) => <svg viewBox="0 0 24 24" className={on ? 'ic fill' : 'ic'} aria-hidden="true"><path d="M12 20s-7-4.4-9.2-8.6C1.2 8.2 3 4.5 6.6 4.5c2.2 0 3.6 1.3 5.4 3.3 1.8-2 3.2-3.3 5.4-3.3 3.6 0 5.4 3.7 3.8 6.9C19 15.6 12 20 12 20z" /></svg>

// 결과 게시물: 프로필(시군구 대표 사진) + 후보 사진 한 장(누르면 지역 상세) + 하트·닮았어요·별로예요 + 닮은 장면 태그
function ResultPost({ c, avatar, saved, voted, onSave, onOpen, onVote }: {
  c: Candidate; avatar?: string; saved: boolean; voted: 1 | -1 | undefined
  onSave: () => void; onOpen: () => void; onVote: (v: 1 | -1) => void
}) {
  return (
    <li className="post">
      <div className="post-head">
        <span className="av">{avatar ? <img src={avatar} alt="" /> : <i>{c.sigungu.name.slice(0, 1)}</i>}</span>
        <span><b>{c.attraction.name}</b><small>{c.sigungu.sido} {c.sigungu.name}{c.distance_km != null ? ` · ${c.distance_km}km` : ''}</small></span>
      </div>
      <button type="button" className="post-ph" onClick={onOpen} aria-label={`${c.sigungu.name} 자세히 보기`}>
        <img src={c.attraction.image_url} alt={c.attraction.name} loading="lazy" />
      </button>
      <div className="post-act">
        <button type="button" aria-pressed={saved} onClick={onSave} aria-label="저장"><Heart on={saved} /></button>
        <button type="button" className="txt" aria-pressed={voted === 1} onClick={() => onVote(1)}>닮았어요</button>
        <button type="button" className="txt" aria-pressed={voted === -1} onClick={() => onVote(-1)}>별로예요</button>
      </div>
      {reasonOf(c) && <p className="post-personal">내 취향 반영 ↑ · {reasonOf(c)}</p>}
      {c.similar_tags.length > 0 && <p className="post-cap tags">{c.similar_tags.map(t => <span key={t}>#{t}</span>)}</p>}
    </li>
  )
}
