import { useCallback, useEffect, useState } from 'react'
import { api, PRIORITY_LABEL, regionsApi, type AnalyzeResponse, type Candidate, type Crop, type FilterKey, type Filters, type RecommendResponse, type RegionRow, type RegionsResponse } from './api'
import { BrowseStep } from './components/BrowseStep'
import { Rankings } from './components/Rankings'
import { RegionPage } from './components/RegionPage'
import { ResultMap } from './components/ResultMap'
import { FilterBar } from './components/FilterBar'
import { CandidateCard } from './components/CandidateCard'
import { Conditions, type Cond } from './components/Conditions'
import { CropStep } from './components/CropStep'
import { PhotoStep, type Source } from './components/PhotoStep'
import { TagChips } from './components/TagChips'

type Step = 'photo' | 'browse' | 'crop' | 'scene' | 'result'
type Saved = { key: string; name: string; sigungu: string; image_url: string; license: string }
const PAGE = 5
const STEPS: [Step, string][] = [['photo', '사진'], ['crop', '영역'], ['scene', '장면·조건'], ['result', '추천']]

function loadSaved(): Saved[] {
  try { return JSON.parse(localStorage.getItem('saved-places') || '[]') } catch { return [] }
}

// 자른 영역을 결과 화면의 "원본"으로 보여 주기 위한 미리보기 (사용자 사진이므로 잘라도 된다)
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

export default function App() {
  const [step, setStep] = useState<Step>('photo')
  const [source, setSource] = useState<Source | null>(null)
  const [preview, setPreview] = useState<string>('')
  const [analysis, setAnalysis] = useState<AnalyzeResponse | null>(null)
  const [kept, setKept] = useState<string[]>([])
  const [cond, setCond] = useState<Cond>({ priority: 'visual', origin: null })
  const [fsel, setFsel] = useState<{ sido: string | null; keys: FilterKey[] }>({ sido: null, keys: [] })
  const [regions, setRegions] = useState<RegionsResponse | null>(null)
  const filters: Filters = fsel
  const setFilters = (f: Filters) => setFsel({ sido: f.sido, keys: f.keys })
  const [result, setResult] = useState<RecommendResponse | null>(null)
  const [extra, setExtra] = useState<Candidate[]>([])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [saved, setSaved] = useState<Saved[]>(loadSaved)
  const [compare, setCompare] = useState<Candidate[]>([])
  const [votes, setVotes] = useState<Record<string, 1 | -1>>({})
  // 지역 상세는 주소로도 연다: #region=50_제주시&acts=food (공유·바로가기용)
  const readHash = () => new URLSearchParams(window.location.hash.slice(1))
  const [hoverKey, setHoverKey] = useState<string | null>(null)
  const [regionKey, setRegionKeyState] = useState<string | null>(() => readHash().get('region'))
  const [actsGroup] = useState<string | undefined>(() => readHash().get('acts') ?? undefined)
  const setRegionKey = (k: string | null) => {
    setRegionKeyState(k)
    history.replaceState(null, '', k ? `#region=${encodeURIComponent(k)}` : window.location.pathname)
  }
  useEffect(() => {
    const onHash = () => setRegionKeyState(readHash().get('region'))
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  useEffect(() => { try { localStorage.setItem('saved-places', JSON.stringify(saved)) } catch { /* 저장소 없음 */ } }, [saved])
  useEffect(() => { regionsApi(cond.origin).then(setRegions).catch(e => setErr(e.message)) }, [cond.origin])

  const pick = (s: Source) => { setSource(s); setErr(null); setStep('crop'); window.scrollTo(0, 0) }

  const analyze = async (crop: Crop | null, override?: Source) => {
    const s = override ?? source
    if (!s) return
    setBusy(true); setErr(null)
    try {
      const a = await api.analyze(s.kind === 'file' ? { file: s.file, crop, sourceAttractionId: s.sourceAttractionId }
                                                     : { demoPhotoId: s.photo.photo_id, crop })
      setAnalysis(a); setKept(a.scene_tags.map(t => t.tag))
      setPreview(await croppedPreview(s.url, crop))
      setResult(null); setExtra([]); setCompare([])
      setStep('scene'); window.scrollTo(0, 0)
    } catch (e) { setErr((e as Error).message) } finally { setBusy(false) }
  }

  const recommend = useCallback(async (c: Cond, tags: string[]) => {
    if (!analysis) return
    setBusy(true); setErr(null)
    try {
      const r = await api.recommend({ query_id: analysis.query_id, priority: c.priority,
                                      origin: c.origin, kept_tags: tags, limit: PAGE, offset: 0, filters: fsel.keys, sido: fsel.sido })
      setResult(r); setExtra([]); setStep('result')
    } catch (e) { setErr((e as Error).message) } finally { setBusy(false) }
  }, [analysis, fsel])

  // 결과 화면에서 조건·태그를 바꾸면 사진을 다시 분석하지 않고 다시 정렬만 한다
  useEffect(() => { if (step === 'result') recommend(cond, kept) }, [cond, kept, fsel]) // eslint-disable-line react-hooks/exhaustive-deps

  const more = async () => {
    if (!analysis || !result) return
    setBusy(true)
    try {
      const r = await api.recommend({ query_id: analysis.query_id, priority: cond.priority,
                                      origin: cond.origin, kept_tags: kept, limit: PAGE, offset: PAGE + extra.length,
                                      filters: fsel.keys, sido: fsel.sido })
      setExtra([...extra, ...r.candidates])
    } catch (e) { setErr((e as Error).message) } finally { setBusy(false) }
  }

  // 국내 관광지 사진으로 다시 찾기: 출발 관광지를 넘겨 그 시군구가 다시 1위로 나오지 않게 한다 (#14)
  const searchFrom = async (c: { attraction: { id: string; image_url: string } }) => {
    try {
      const blob = await fetch(c.attraction.image_url).then(r => r.blob())
      const s: Source = { kind: 'file', file: blob, url: URL.createObjectURL(blob), sourceAttractionId: c.attraction.id }
      setSource(s)
      await analyze(null, s)
    } catch { setErr('이 사진을 불러오지 못했습니다.') }
  }

  const toggleSave = (c: Candidate) => {
    const key = `${c.sigungu.key}/${c.attraction.id}`
    setSaved(saved.some(s => s.key === key) ? saved.filter(s => s.key !== key)
      : [...saved, { key, name: c.attraction.name, sigungu: `${c.sigungu.sido} ${c.sigungu.name}`, image_url: c.attraction.image_url, license: c.attraction.license }])
  }
  const toggleCompare = (c: Candidate) => {
    const has = compare.some(x => x.sigungu.key === c.sigungu.key)
    setCompare(has ? compare.filter(x => x.sigungu.key !== c.sigungu.key) : [...compare, c].slice(-3))
  }
  const feedback = (c: Candidate, v: 1 | -1) => {
    if (!analysis) return
    setVotes({ ...votes, [c.sigungu.key]: v })
    api.feedback({ query_id: analysis.query_id, sigungu_key: c.sigungu.key, attraction_id: c.attraction.id, value: v }).catch(() => {})
  }

  const credit = source?.kind === 'demo' ? source.photo : null
  const list = result ? [...result.candidates, ...extra] : []

  return (
    <div className="app">
      <header className="topbar">
        <button type="button" className="logo" onClick={() => { setStep('photo'); setResult(null) }}>닮은꼴<i>.</i></button>
        <ol className="stepper" aria-label="진행 단계">
          {STEPS.map(([s, l], i) => <li key={s} className={s === step ? 'on' : STEPS.findIndex(x => x[0] === (step === 'browse' ? 'photo' : step)) > i ? 'done' : ''}>{l}</li>)}
        </ol>
        {saved.length > 0 && <a className="saved-link" href="#saved">저장 {saved.length}</a>}
      </header>

      <main className="main">
        {err && <p className="error" role="alert">{err}</p>}
        {step === 'photo' && (
          <PhotoStep onPick={pick} onBrowse={() => { setStep('browse'); window.scrollTo(0, 0) }}
                     filterBar={<FilterBar value={filters} onChange={setFilters} regions={regions} />}
                     afterEntries={<Rankings onOpen={setRegionKey} />} />
        )}
        {step === 'browse' && (
          <section className="step">
            <div className="browse-top">
              <button type="button" className="ghost" onClick={() => setStep('photo')}>← 처음으로</button>
              <FilterBar value={filters} onChange={setFilters} regions={regions} compact />
            </div>
            <BrowseStep filters={filters} regions={regions} origin={cond.origin} onOrigin={o => setCond({ ...cond, origin: o })}
                        onSearchPhoto={(r: RegionRow) => searchFrom({ attraction: { id: r.photo!.attraction_id, image_url: r.photo!.image_url } })}
                        onOpen={setRegionKey} />
          </section>
        )}
        {step === 'crop' && source && <CropStep url={source.url} busy={busy} onBack={() => setStep('photo')} onDone={c => analyze(c)} />}

        {step === 'scene' && analysis && (
          <section className="step scene-step">
            <div className="scene-photo"><img src={preview} alt="분석한 사진" />{credit && <Credit p={credit} />}</div>
            <div className="scene-side">
              <h2>사진에서 찾은 장면</h2>
              <p className="sub">설명에 쓰지 않을 태그는 눌러서 빼 주세요. (CLIP 자동 분석)</p>
              <TagChips tags={analysis.scene_tags} kept={kept} onChange={setKept} />
              <h2>조건</h2>
              <FilterBar value={filters} onChange={setFilters} regions={regions} compact />
              <Conditions value={cond} onChange={setCond} />
              <div className="actions">
                <button type="button" className="ghost" onClick={() => setStep('crop')}>영역 다시 고르기</button>
                <button type="button" className="primary" disabled={busy} onClick={() => recommend(cond, kept)}>{busy ? '찾는 중…' : '닮은 국내 여행지 찾기'}</button>
              </div>
            </div>
          </section>
        )}

        {step === 'result' && result && analysis && (
          <section className="result2">
            <div className="qbar">
              <img className="qthumb" src={preview} alt="찾은 사진" />
              <div className="qmain">
                <h1>이 사진과 분위기가 닮은 국내 여행지</h1>
                <p className="qmeta">
                  {result.is_example && <span className="badge warn">예시 데이터</span>}
                  {result.query.allowed_regions != null && <>조건에 맞는 {result.query.allowed_regions}곳 안에서 </>}
                  사진이 닮은 {result.total_candidates}곳 · <b>{PRIORITY_LABEL[cond.priority]}</b> 순
                  {result.query.excluded_sigungu && <> · 출발한 {result.query.excluded_sigungu.name}은 제외</>}
                </p>
                <TagChips tags={analysis.scene_tags} kept={kept} onChange={setKept} />
                {credit && <Credit p={credit} />}
              </div>
              <details className="qcond">
                <summary>조건 바꾸기</summary>
                <div className="qcond-panel">
                  <FilterBar value={filters} onChange={setFilters} regions={regions} compact />
                  <Conditions value={cond} onChange={setCond} />
                  <button type="button" className="ghost wide" onClick={() => setStep('photo')}>새 사진으로 찾기</button>
                </div>
              </details>
            </div>
            {result.total_candidates === 0 && <p className="error">조건에 맞는 시군구가 없습니다. 조건을 하나 빼 보세요.</p>}
            <div className="result-body">
              <div className="results">
                <div className={busy ? 'cards busy' : 'cards'}>
                  {list.map(c => (
                    <div key={c.sigungu.key} id={`cand-${c.sigungu.key}`} className={hoverKey === c.sigungu.key ? 'cand on' : 'cand'}
                         onMouseEnter={() => setHoverKey(c.sigungu.key)} onMouseLeave={() => setHoverKey(null)}>
                      <CandidateCard c={c} originUrl={preview} priority={cond.priority}
                        saved={saved.some(s => s.key === `${c.sigungu.key}/${c.attraction.id}`)}
                        comparing={compare.some(x => x.sigungu.key === c.sigungu.key)} voted={votes[c.sigungu.key]}
                        onSave={() => toggleSave(c)} onCompare={() => toggleCompare(c)} onFeedback={v => feedback(c, v)}
                        onSearchSimilar={() => searchFrom(c)} onOpenRegion={() => setRegionKey(c.sigungu.key)} />
                    </div>
                  ))}
                </div>
                {list.length < result.total_candidates && (
                  <button type="button" className="ghost wide" disabled={busy} onClick={more}>다른 후보 보기 ({list.length} / {result.total_candidates})</button>
                )}
                {compare.length >= 2 && <CompareTable items={compare} onClear={() => setCompare([])} />}
                <Sources r={result} />
              </div>
              <div className="map-col">
                <ResultMap items={list} active={hoverKey}
                  onPick={k => { setHoverKey(k); document.getElementById(`cand-${k}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' }) }} />
              </div>
            </div>
          </section>
        )}

        {saved.length > 0 && (
          <section id="saved" className="saved">
            <h2>저장한 곳</h2>
            <div className="saved-grid">
              {saved.map(s => (
                <div key={s.key} className="saved-item">
                  <img src={s.image_url} alt={s.name} loading="lazy" />
                  <div><b>{s.name}</b><small>{s.sigungu}</small><small className="fine">{s.license}</small></div>
                  <button type="button" className="ghost" onClick={() => setSaved(saved.filter(x => x.key !== s.key))}>빼기</button>
                </div>
              ))}
            </div>
          </section>
        )}
      </main>
      {regionKey && (
        <RegionPage regionKey={regionKey} initialGroup={actsGroup}
          onClose={() => setRegionKey(null)}
          onSearchPhoto={p => { setRegionKey(null); searchFrom({ attraction: { id: p.attraction_id, image_url: p.image_url } }) }} />
      )}
    </div>
  )
}

function Credit({ p }: { p: { artist: string; license: string; license_url: string; source_page: string } }) {
  return (
    <p className="credit">
      사진 {p.artist} · <a href={p.license_url} target="_blank" rel="noopener">{p.license}</a> · <a href={p.source_page} target="_blank" rel="noopener">Wikimedia Commons</a>
    </p>
  )
}

function CompareTable({ items, onClear }: { items: Candidate[]; onClear: () => void }) {
  const rows: [string, (c: Candidate) => string][] = [
    ['시군구', c => `${c.sigungu.sido} ${c.sigungu.name}`],
    ['가장 닮은 관광지', c => c.attraction.name],
    ['사진 유사도 순위', c => `${c.visual_rank}위 (CLIP ${c.visual.similarity.toFixed(2)})`],
    ['거리', c => c.distance_km != null ? `${c.distance_km} km` : '출발지 미선택'],
    ['비슷한 점', c => c.similar_tags.join(', ') || '–'],
    ['다른 점', c => c.different_tags.join(', ') || '–'],
  ]
  return (
    <section className="compare">
      <div className="compare-head"><h2>후보 비교</h2><button type="button" className="ghost" onClick={onClear}>비우기</button></div>
      <div className="table-wrap">
        <table>
          <thead><tr><th scope="col">항목</th>{items.map(c => <th key={c.sigungu.key} scope="col">{c.sigungu.name}</th>)}</tr></thead>
          <tbody>{rows.map(([l, f]) => <tr key={l}><th scope="row">{l}</th>{items.map(c => <td key={c.sigungu.key}>{f(c)}</td>)}</tr>)}</tbody>
        </table>
      </div>
    </section>
  )
}

function Sources({ r }: { r: RecommendResponse }) {
  return (
    <section className="sources">
      <h2>데이터 출처와 기준</h2>
      <ul>{r.data_sources.map(s => <li key={s.name}><b>{s.name}</b> · {s.as_of} · {s.period}</li>)}</ul>
      <p className="fine">추천: {r.model.visual} / 재정렬: {r.model.rerank}</p>
    </section>
  )
}
