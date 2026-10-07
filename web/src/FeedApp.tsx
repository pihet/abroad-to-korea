import { useEffect, useMemo, useRef, useState } from 'react'
import { rankingsApi, regionsApi, type RankingList, type RegionRow } from './api'
import { RegionPage } from './components/RegionPage'
import { FeedSearch, type Source } from './FeedSearch'
import './feed.css'

// 메인 화면 (인스타그램형). 예전 화면은 #classic 으로 연다. 데이터는 기존 API 그대로, 화면 배치만 다르다.
// 사진은 공공누리 3유형이 섞여 있어 정사각형으로 자르지 않는다 (object-fit: contain).

type Tab = 'home' | 'explore' | 'search' | 'saved'
type Story = { id: string; label: string; match: (r: RegionRow) => boolean }
const STORIES: Story[] = [
  { id: 'all', label: '전체', match: () => true },
  { id: 'sea', label: '바다', match: r => r.flags.sea },
  { id: 'mountain', label: '산·숲', match: r => r.flags.mountain },
  { id: 'rural', label: '시골', match: r => r.flags.rural },
  { id: 'city', label: '도시', match: r => r.flags.city },
]
const PAGE = 8

// 하루 동안은 같은 순서 (새로 고칠 때마다 피드가 뒤섞이지 않게)
function dailyShuffle<T>(xs: T[]): T[] {
  let seed = Number(new Date().toISOString().slice(0, 10).replace(/-/g, ''))
  const rnd = () => (seed = (seed * 9301 + 49297) % 233280) / 233280
  const a = [...xs]
  for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(rnd() * (i + 1)); [a[i], a[j]] = [a[j], a[i]] }
  return a
}

// 원형으로 자르는 작은 사진은 변경이 허용되는 공공누리 1유형만 (3유형은 변경 금지라 자르지 않는다)
const canCrop = (r: RegionRow) => !!r.photo && r.photo.license.includes('제1유형')

const loadSaved = (): string[] => { try { return JSON.parse(localStorage.getItem('feed-saved') || '[]') } catch { return [] } }

function caption(r: RegionRow) {
  const bits = [
    r.flags.sea && r.coast_km != null && `#바다 ${r.coast_km}km`,
    r.mountain_n > 0 && `#산숲 ${r.mountain_n}곳`,
    r.flags.city ? '#도시' : '#시골소도시',
  ].filter(Boolean)
  return bits.join(' ')
}

const Icon = {
  home: <path d="M3 10.5 12 3l9 7.5V21h-6v-6H9v6H3z" />,
  search: <><circle cx="11" cy="11" r="7" /><path d="m20 20-4-4" /></>,
  plus: <><rect x="3" y="3" width="18" height="18" rx="5" /><path d="M12 8v8M8 12h8" /></>,
  bookmark: <path d="M6 3h12v18l-6-5-6 5z" />,
  heart: <path d="M12 20s-7-4.4-9.2-8.6C1.2 8.2 3 4.5 6.6 4.5c2.2 0 3.6 1.3 5.4 3.3 1.8-2 3.2-3.3 5.4-3.3 3.6 0 5.4 3.7 3.8 6.9C19 15.6 12 20 12 20z" />,
  photo: <><rect x="3" y="5" width="18" height="15" rx="3" /><circle cx="12" cy="12.5" r="3.5" /><path d="M8 5l1.5-2h5L16 5" /></>,
  map: <><path d="M9 4 3 6v14l6-2 6 2 6-2V4l-6 2z" /><path d="M9 4v14M15 6v14" /></>,
}
const Svg = ({ d, fill }: { d: React.ReactNode; fill?: boolean }) =>
  <svg viewBox="0 0 24 24" className={fill ? 'ic fill' : 'ic'} aria-hidden="true">{d}</svg>

export default function FeedApp() {
  const [rows, setRows] = useState<RegionRow[] | null>(null)
  const [lists, setLists] = useState<RankingList[]>([])
  const [err, setErr] = useState<string | null>(null)
  const [tab, setTab] = useState<Tab>('home')
  const [story, setStory] = useState('all')
  const [shown, setShown] = useState(PAGE)
  // 지역 상세는 주소로도 연다: #region=50_제주시 (공유·바로가기용)
  const [open, setOpenState] = useState<string | null>(() => new URLSearchParams(window.location.hash.slice(1)).get('region'))
  const setOpen = (k: string | null) => { setOpenState(k); history.replaceState(null, '', k ? `#region=${encodeURIComponent(k)}` : window.location.pathname) }
  const [start, setStart] = useState<Source | null>(null)
  const [saved, setSaved] = useState<string[]>(loadSaved)
  const more = useRef<HTMLDivElement>(null)

  useEffect(() => {
    regionsApi().then(r => setRows(dailyShuffle(r.regions.filter(x => x.photo)))).catch(e => setErr(e.message))
    rankingsApi().then(setLists).catch(() => setLists([]))
  }, [])
  useEffect(() => { try { localStorage.setItem('feed-saved', JSON.stringify(saved)) } catch { /* 저장소 없음 */ } }, [saved])
  useEffect(() => { setShown(PAGE); window.scrollTo(0, 0) }, [story, tab])
  useEffect(() => {
    const onHash = () => setOpenState(new URLSearchParams(window.location.hash.slice(1)).get('region'))
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const feed = useMemo(() => (rows ?? []).filter(STORIES.find(s => s.id === story)!.match), [rows, story])
  // 피드 끝에 닿으면 다음 묶음 (무한 스크롤)
  useEffect(() => {
    const el = more.current
    if (!el) return
    const io = new IntersectionObserver(es => es[0].isIntersecting && setShown(n => n + PAGE), { rootMargin: '600px' })
    io.observe(el)
    return () => io.disconnect()
  }, [tab, feed.length])

  const toggle = (k: string) => setSaved(saved.includes(k) ? saved.filter(x => x !== k) : [...saved, k])
  const strip = lists.find(l => l.items.length > 0)  // 순위 목록 하나를 가로 줄로
  // 분류마다 서로 다른 1유형 사진을 고른다
  const covers = useMemo(() => {
    const used = new Set<string>(), out: Record<string, string | undefined> = {}
    for (const s of STORIES) {
      const r = (rows ?? []).find(r => s.match(r) && canCrop(r) && !used.has(r.photo!.image_url))
      if (r) { used.add(r.photo!.image_url); out[s.id] = r.photo!.image_url }
    }
    return out
  }, [rows])
  const cover = (s: Story) => covers[s.id]
  const goSearch = () => setTab('search')
  // 지역 상세의 "이 사진과 닮은 다른 곳 찾기": 출발 관광지를 넘겨 같은 시군구가 다시 1위로 나오지 않게 한다
  const searchPhoto = async (p: { attraction_id: string; image_url: string }) => {
    const blob = await fetch(p.image_url).then(r => r.blob())
    setOpen(null); setTab('search')
    setStart({ kind: 'file', file: blob, url: URL.createObjectURL(blob), sourceAttractionId: p.attraction_id })
  }

  return (
    <div className="ig">
      <header className="ig-top">
        <b className="ig-logo">닮은꼴<i>.</i></b>
        <div className="ig-top-act">
          <button type="button" onClick={goSearch} aria-label="사진으로 찾기"><Svg d={Icon.photo} /></button>
          <a href="/#classic" className="ig-old" onClick={e => { e.preventDefault(); window.location.hash = 'classic'; window.location.reload() }}>예전 화면</a>
        </div>
      </header>

      {err && <p className="ig-err">{err}</p>}
      {!rows && !err && <p className="ig-wait">불러오는 중…</p>}

      {rows && tab === 'home' && <>
        <nav className="ig-stories" aria-label="분류">
          {STORIES.map(s => (
            <button key={s.id} type="button" aria-pressed={story === s.id} onClick={() => setStory(s.id)}>
              <span className="ring"><span className="in">{cover(s) && <img src={cover(s)} alt="" />}</span></span>
              <small>{s.label}</small>
            </button>
          ))}
        </nav>

        <button type="button" className="ig-cta" onClick={goSearch}>
          <Svg d={Icon.photo} /><span><b>가고 싶은 해외 사진이 있나요?</b><small>사진을 올리면 분위기가 닮은 국내 여행지를 찾아 드려요</small></span>
        </button>

        {story === 'all' && strip && (
          <section className="ig-strip">
            <div className="ig-strip-head"><b>{strip.title}</b><small>{strip.basis}</small></div>
            <ol>
              {strip.items.map((it, i) => (
                <li key={it.key}><button type="button" onClick={() => setOpen(it.key)}>
                  <span className="ph">{it.photo && <img src={it.photo.image_url} alt={it.photo.name} loading="lazy" />}<em>{i + 1}</em></span>
                  <b>{it.name}</b><small>{it.sido} · {it.value.toLocaleString()}{it.unit}</small>
                </button></li>
              ))}
            </ol>
          </section>
        )}

        <ul className="ig-feed">
          {feed.slice(0, shown).map(r => (
            <li key={r.key} className="post">
              <div className="post-head">
                <span className="av">{canCrop(r) ? <img src={r.photo!.image_url} alt="" /> : <i>{r.name.slice(0, 1)}</i>}</span>
                <span><b>{r.name}</b><small>{r.sido}</small></span>
              </div>
              <button type="button" className="post-ph" onClick={() => setOpen(r.key)} aria-label={`${r.name} 자세히 보기`}>
                <img src={r.photo!.image_url} alt={r.photo!.name} loading="lazy" />
              </button>
              <div className="post-act">
                <button type="button" aria-pressed={saved.includes(r.key)} onClick={() => toggle(r.key)} aria-label="저장"><Svg d={Icon.heart} fill={saved.includes(r.key)} /></button>
                <button type="button" onClick={() => setOpen(r.key)} aria-label="지도와 동네 보기"><Svg d={Icon.map} /></button>
                <button type="button" className="post-more" onClick={() => setOpen(r.key)}>자세히 보기</button>
              </div>
              <p className="post-cap"><b>{r.photo!.name}</b> {caption(r)}</p>
              <small className="post-credit">사진 한국관광공사 TourAPI · {r.photo!.license}</small>
            </li>
          ))}
        </ul>
        {shown < feed.length && <div ref={more} className="ig-wait">더 불러오는 중…</div>}
      </>}

      {rows && tab === 'explore' && (
        <div className="ig-grid">
          {rows.map(r => (
            <button key={r.key} type="button" onClick={() => setOpen(r.key)} aria-label={`${r.sido} ${r.name}`}>
              <img src={r.photo!.image_url} alt={r.photo!.name} loading="lazy" />
              <span>{r.name}</span>
            </button>
          ))}
        </div>
      )}

      {rows && tab === 'saved' && (
        saved.length === 0 ? <p className="ig-wait">하트를 누른 곳이 여기에 모여요.</p> : (
          <div className="ig-grid">
            {rows.filter(r => saved.includes(r.key)).map(r => (
              <button key={r.key} type="button" onClick={() => setOpen(r.key)} aria-label={`${r.sido} ${r.name}`}>
                <img src={r.photo!.image_url} alt={r.photo!.name} loading="lazy" /><span>{r.name}</span>
              </button>
            ))}
          </div>
        )
      )}

      <div hidden={tab !== 'search'}>
        <FeedSearch start={start} saved={saved} onToggleSave={toggle} onOpen={setOpen} />
      </div>

      <nav className="ig-tabs" aria-label="메뉴">
        <button type="button" aria-pressed={tab === 'home'} onClick={() => setTab('home')}><Svg d={Icon.home} fill={tab === 'home'} /><small>홈</small></button>
        <button type="button" aria-pressed={tab === 'explore'} onClick={() => setTab('explore')}><Svg d={Icon.search} /><small>탐색</small></button>
        <button type="button" aria-pressed={tab === 'search'} onClick={goSearch}><Svg d={Icon.plus} /><small>사진으로 찾기</small></button>
        <button type="button" aria-pressed={tab === 'saved'} onClick={() => setTab('saved')}><Svg d={Icon.bookmark} fill={tab === 'saved'} /><small>저장</small></button>
      </nav>

      {open && <RegionPage regionKey={open} onClose={() => setOpen(null)} onSearchPhoto={p => { searchPhoto(p).catch(() => {}) }} />}
    </div>
  )
}
